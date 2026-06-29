"""
IR Monitor — Theo dõi tin tức mới từ 5 trang IR và gửi Telegram
Tất cả 5 nguồn đều dùng JSON API / REST API — không cần Playwright.
"""

import os
import json
import time
import requests
from datetime import datetime

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


# ── Scraping ───────────────────────────────────────────────────────────────────
def fetch_source(source: dict, session: requests.Session) -> list[dict]:
    sid = source["id"]
    scraper = SCRAPER_MAP.get(sid)
    if not scraper:
        print(f"  ⚠️  [{sid}] Không có scraper")
        return []

    print(f"  📡 [{sid}] Fetching...")
    try:
        items = scraper.fetch(source, session)
        print(f"  ✅ [{sid}] {len(items)} items")
        return items
    except Exception as e:
        print(f"  ❌ [{sid}] Lỗi: {e}")
        return []


# ── State management ───────────────────────────────────────────────────────────
def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            raw = json.load(f)
            return {k: set(v) for k, v in raw.get("sources", {}).items()}
    return {}


def save_state(all_items: dict) -> None:
    data = {
        "updated_at": now(),
        "sources": {
            sid: [item["uid"] for item in items]
            for sid, items in all_items.items()
        },
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Telegram ───────────────────────────────────────────────────────────────────
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


def format_message(source: dict, new_items: list[dict]) -> str:
    lines = [
        f"{source['emoji']} <b>{source['name']} — {len(new_items)} tin mới</b>",
        "─" * 28,
        "",
    ]
    for item in new_items:
        date_str = f" <i>({item['date']})</i>" if item.get("date") else ""
        lines.append(f"📄 <a href=\"{item['link']}\">{item['title']}</a>{date_str}")
    lines += ["", f"🔗 <a href=\"{source['source_page']}\">Xem tất cả →</a>"]
    return "\n".join(lines)


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
        current_all[sid] = items

        if not items or is_first_run:
            print()
            continue

        known_uids = known.get(sid, set())
        new_items = [item for item in items if item["uid"] not in known_uids]
        if new_items:
            total_new += len(new_items)
            print(f"  🔔 {len(new_items)} tin mới! Gửi Telegram...")
            send_telegram(format_message(source, new_items))
            time.sleep(1)

        print()

    save_state(current_all)

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
