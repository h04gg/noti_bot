"""
IR Monitor — Theo dõi tin tức mới từ 5 trang IR và gửi Telegram
Tất cả 5 nguồn đều dùng JSON API / REST API — không cần Playwright.
"""

import os
import re
import json
import time
import requests
from datetime import datetime, timedelta

from config import SOURCES
import scrapers.phatdat as scraper_phatdat
import scrapers.vpbank as scraper_vpbank
import scrapers.gelex as scraper_gelex
import scrapers.eximbank as scraper_eximbank
import scrapers.vingroup as scraper_vingroup

# ── Cấu hình ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
STATE_FILE = "ir_state.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}

SCRAPER_MAP = {
    "phatdat": scraper_phatdat,
    "vpbank": scraper_vpbank,
    "gelex": scraper_gelex,
    "eximbank": scraper_eximbank,
    "vingroup": scraper_vingroup,
}

FETCH_RETRIES = 3
FETCH_RETRY_DELAY = 3  # giây
RECENT_DAYS = 14  # Chỉ theo dõi tin trong N ngày gần nhất


def parse_item_date(date_str: str) -> datetime | None:
    if not date_str or not str(date_str).strip():
        return None
    s = str(date_str).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s[:10], fmt)
        except ValueError:
            continue
    m = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", s)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None


def filter_recent_items(items: list[dict], days: int = RECENT_DAYS) -> list[dict]:
    cutoff = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    recent = []
    for item in items:
        dt = parse_item_date(item.get("date", ""))
        if dt is None or dt >= cutoff:
            recent.append(item)
    return recent


# ── Scraping ───────────────────────────────────────────────────────────────────
def fetch_source(source: dict, session: requests.Session) -> list[dict] | None:
    sid = source["id"]
    scraper = SCRAPER_MAP.get(sid)
    if not scraper:
        print(f"  ⚠️  [{sid}] Không có scraper")
        return []

    print(f"  📡 [{sid}] Fetching...")
    last_error: Exception | None = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            items = scraper.fetch(source, session)
            if attempt > 1:
                print(f"  ✅ [{sid}] {len(items)} items (sau {attempt} lần thử)")
            else:
                print(f"  ✅ [{sid}] {len(items)} items")
            return items
        except Exception as e:
            last_error = e
            if attempt < FETCH_RETRIES:
                print(
                    f"  ⚠️  [{sid}] Lỗi lần {attempt}/{FETCH_RETRIES}: {e}"
                    f" — thử lại sau {FETCH_RETRY_DELAY}s"
                )
                time.sleep(FETCH_RETRY_DELAY)
            else:
                print(f"  ❌ [{sid}] Lỗi sau {FETCH_RETRIES} lần: {e}")
    return None


# ── State management ───────────────────────────────────────────────────────────
def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            raw = json.load(f)
            return {k: set(v) for k, v in raw.get("sources", {}).items()}
    return {}


def save_state(all_items: dict, previous: dict) -> None:
    sources: dict[str, list[str]] = {}
    for source in SOURCES:
        sid = source["id"]
        items = all_items.get(sid)
        if items is not None:
            sources[sid] = [item["uid"] for item in items]
        else:
            sources[sid] = list(previous.get(sid, set()))

    data = {
        "updated_at": now(),
        "sources": sources,
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Telegram ───────────────────────────────────────────────────────────────────
TELEGRAM_MAX_LEN = 3800  # Giới hạn Telegram 4096 ký tự
TELEGRAM_MAX_ITEMS = 15  # Tối đa tin liệt kê khi có quá nhiều tin mới


def send_telegram(message: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.ok:
            print("  ✅ Đã gửi Telegram.")
            return True
        print(f"  ❌ Lỗi Telegram: {resp.status_code} {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"  ❌ Telegram exception: {e}")
        return False


def _format_item_line(item: dict) -> str:
    date_str = f" <i>({item['date']})</i>" if item.get("date") else ""
    return f"📄 <a href=\"{item['link']}\">{item['title']}</a>{date_str}"


def _message_chunks(source: dict, new_items: list[dict], total_new: int) -> list[str]:
    footer = f"\n\n🔗 <a href=\"{source['source_page']}\">Xem tất cả →</a>"
    lines = [_format_item_line(item) for item in new_items]
    batches: list[list[str]] = []
    batch: list[str] = []

    for line in lines:
        if batch and len("\n".join(batch + [line])) > TELEGRAM_MAX_LEN - 300:
            batches.append(batch)
            batch = [line]
        else:
            batch.append(line)
    if batch:
        batches.append(batch)

    messages = []
    total_parts = len(batches)
    for i, part_lines in enumerate(batches):
        header = f"{source['emoji']} <b>{source['name']} — {total_new} tin mới</b>"
        if total_parts > 1:
            header += f" <i>({i + 1}/{total_parts})</i>"
        msg = header + "\n" + "─" * 28 + "\n\n" + "\n".join(part_lines)
        if i == 0 and total_new > len(new_items):
            msg += f"\n\n<i>… và {total_new - len(new_items)} tin khác (xem tại link nguồn)</i>"
        msg += footer
        messages.append(msg)
    return messages


def send_new_items(source: dict, new_items: list[dict]) -> bool:
    total = len(new_items)
    if total > TELEGRAM_MAX_ITEMS:
        to_send = new_items[:TELEGRAM_MAX_ITEMS]
        print(f"    (chỉ gửi {len(to_send)}/{total} tin — tránh vượt giới hạn Telegram)")
    else:
        to_send = new_items

    chunks = _message_chunks(source, to_send, total_new=total)
    ok = True
    for i, msg in enumerate(chunks):
        if not send_telegram(msg):
            ok = False
        if i < len(chunks) - 1:
            time.sleep(0.5)
    return ok


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print(f"IR Monitor — {now()}")
    print(f"{'='*55}\n")

    session = requests.Session()
    session.headers.update(HEADERS)

    known = load_state()
    is_first_run = not bool(known)
    if is_first_run:
        print("🆕 Lần đầu chạy — lưu state, chưa gửi thông báo.\n")

    current_all: dict[str, list[dict]] = {}
    total_new = 0

    for source in SOURCES:
        sid = source["id"]
        items = fetch_source(source, session)
        if items is None:
            print(f"  ⏭️  [{sid}] Giữ state cũ, bỏ qua lần này.\n")
            continue

        raw_count = len(items)
        items = filter_recent_items(items)
        if raw_count > len(items):
            print(
                f"  📅 [{sid}] Giữ {len(items)}/{raw_count} tin "
                f"(trong {RECENT_DAYS} ngày gần nhất)"
            )

        current_all[sid] = items

        if not items or is_first_run:
            print()
            continue

        known_uids = known.get(sid, set())
        new_items = [item for item in items if item["uid"] not in known_uids]
        if new_items:
            total_new += len(new_items)
            print(f"  🔔 {len(new_items)} tin mới! Gửi Telegram...")
            send_new_items(source, new_items)
            time.sleep(1)

        print()

    save_state(current_all, known)

    if is_first_run:
        summary = "\n".join(
            f"  {s['emoji']} {s['name']}: {len(current_all.get(s['id'], []))} tin"
            for s in SOURCES
        )
        send_telegram(
            "✅ <b>IR Monitor đã kích hoạt!</b>\n\n"
            f"Theo dõi {len(SOURCES)} nguồn:\n{summary}\n\n"
            "Sẽ thông báo khi có tin mới. 🚀"
        )
    elif total_new == 0:
        print("✅ Không có tin mới.")
    else:
        print(f"\n✅ Đã gửi {total_new} tin mới.")

    print(f"\nHoàn thành — {now()}")


if __name__ == "__main__":
    main()
