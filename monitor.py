"""
IR Monitor — Theo dõi tin tức mới từ các trang IR và gửi Telegram
"""

from __future__ import annotations

import os
import json
import time
import re
import importlib
import requests
from html import escape
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import SOURCES, CATEGORIES, RECENT_DAYS
from filters import filter_recent_items
from scrapers._common import is_known_item

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

def _build_scraper_map() -> dict:
    mapping = {}
    for source in SOURCES:
        sid = source["id"]
        try:
            mapping[sid] = importlib.import_module(f"scrapers.{sid}")
        except ImportError as exc:
            print(f"⚠️  Thiếu scraper scrapers.{sid}: {exc}")
    return mapping


SCRAPER_MAP = _build_scraper_map()

FETCH_WORKERS = min(16, len(SOURCES))

FETCH_RETRIES = 3
FETCH_RETRY_DELAY = 3  # giây


# ── Scraping ───────────────────────────────────────────────────────────────────
def fetch_source(source: dict, session: requests.Session) -> tuple[list[dict] | None, str | None]:
    """Trả về (items, error). items=None nghĩa là fetch thất bại sau retry."""
    sid = source["id"]
    scraper = SCRAPER_MAP.get(sid)
    if not scraper:
        msg = "Không có scraper"
        print(f"  ⚠️  [{sid}] {msg}")
        return None, msg

    print(f"  📡 [{sid}] Fetching...")
    last_error: Exception | None = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            items = scraper.fetch(source, session)
            if attempt > 1:
                print(f"  ✅ [{sid}] {len(items)} items (sau {attempt} lần thử)")
            else:
                print(f"  ✅ [{sid}] {len(items)} items")
            return items, None
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
    err = str(last_error) if last_error else "Lỗi không xác định"
    return None, err


def fetch_all_sources() -> tuple[dict[str, list[dict] | None], dict[str, str]]:
    """Fetch tất cả nguồn song song. Trả về (kết quả, lỗi theo source id)."""
    results: dict[str, list[dict] | None] = {}
    errors: dict[str, str] = {}

    def _fetch_one(source: dict) -> tuple[str, list[dict] | None, str | None]:
        session = requests.Session()
        session.headers.update(HEADERS)
        sid = source["id"]
        items, error = fetch_source(source, session)
        return sid, items, error

    print(f"📡 Fetching {len(SOURCES)} nguồn song song (workers={FETCH_WORKERS})...\n")
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
        futures = [executor.submit(_fetch_one, source) for source in SOURCES]
        for future in as_completed(futures):
            sid, items, error = future.result()
            results[sid] = items
            if error:
                errors[sid] = error

    return results, errors


# ── State management ───────────────────────────────────────────────────────────
STATE_VERSION = 1


def load_state() -> tuple[dict[str, set[str]], set[str]]:
    """Trả về (known_uids, sids_có_trong_file) — dùng phân biệt nguồn mới thêm config."""
    if not os.path.exists(STATE_FILE):
        return {}, set()
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️  State file hỏng, bắt đầu lại: {e}")
        return {}, set()
    sources = raw.get("sources", {})
    known = {k: set(v) for k, v in sources.items()}
    return known, set(sources.keys())


def has_known_items(known: dict) -> bool:
    """True nếu đã từng lưu ít nhất 1 UID (đã qua lần kích hoạt)."""
    return any(known.get(source["id"]) for source in SOURCES)


def merge_uids(known: dict[str, set[str]], sid: str, items: list[dict]) -> None:
    if not items:
        return
    known.setdefault(sid, set()).update(item["uid"] for item in items)


def write_state(known: dict[str, set[str]]) -> None:
    """Ghi state ngay lập tức (atomic) — gọi sau mỗi nguồn để tránh mất UID."""
    data = {
        "version": STATE_VERSION,
        "updated_at": now(),
        "sources": {
            source["id"]: sorted(known.get(source["id"], set()))
            for source in SOURCES
        },
    }
    tmp = f"{STATE_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


# ── Telegram ───────────────────────────────────────────────────────────────────
TELEGRAM_MAX_LEN = 3800  # Giới hạn Telegram 4096 ký tự
TELEGRAM_MAX_ITEMS = 15  # Tối đa tin liệt kê khi có quá nhiều tin mới


def send_telegram(message: str, *, html: bool = True) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }
    if html:
        payload["parse_mode"] = "HTML"
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.ok:
            print("  ✅ Đã gửi Telegram.")
            return True
        print(f"  ❌ Lỗi Telegram: {resp.status_code} {resp.text[:200]}")
        if html:
            print("  ↪️  Thử lại không dùng HTML...")
            return send_telegram(message, html=False)
        return False
    except Exception as e:
        print(f"  ❌ Telegram exception: {e}")
        return False


def _get_category(source: dict) -> dict:
    return CATEGORIES.get(source.get("category", "other"), CATEGORIES["other"])


def _source_header(source: dict, total_new: int, part: str = "") -> str:
    cat = _get_category(source)
    header = (
        f"{cat['emoji']} <b>{cat['name']}</b> · "
        f"{source['emoji']} <b>{source['name']} — {total_new} tin mới</b>"
    )
    if part:
        header += f" <i>{part}</i>"
    return header


def _activation_summary(current_all: dict) -> str:
    blocks = []
    for cat_id, cat in CATEGORIES.items():
        sources_in_cat = [s for s in SOURCES if s.get("category", "other") == cat_id]
        if not sources_in_cat:
            continue
        lines = [f"{cat['emoji']} <b>{cat['name']}</b>"]
        for s in sources_in_cat:
            count = len(current_all.get(s["id"], []))
            lines.append(f"  {s['emoji']} {s['name']}: {count} tin")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


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
        header = _source_header(source, total_new, part=f"({i + 1}/{total_parts})" if total_parts > 1 else "")
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


def _short_fetch_error(err: str) -> str:
    """Rút gọn exception dài — tránh vỡ HTML Telegram."""
    s = re.sub(r"<[^>]+>", "", str(err)).strip()
    low = s.lower()
    if "connecttimeouterror" in low or "timed out" in low:
        return "Kết nối timeout"
    if "403" in s or "forbidden" in low:
        return "HTTP 403 Forbidden"
    if "max retries exceeded" in low:
        return "Kết nối thất bại (max retries)"
    if "cloudflare" in low:
        return "Cloudflare chặn truy cập"
    return s[:120] + ("…" if len(s) > 120 else "")


def _format_fetch_errors(errors: dict[str, str]) -> list[str]:
    """Nhóm lỗi fetch theo category (plain text)."""
    by_cat: dict[str, list[str]] = {}
    source_by_id = {s["id"]: s for s in SOURCES}

    for sid, err in errors.items():
        source = source_by_id.get(sid)
        if not source:
            continue
        cat_id = source.get("category", "other")
        line = f"  {source['emoji']} {source['name']}: {_short_fetch_error(err)}"
        by_cat.setdefault(cat_id, []).append(line)

    blocks: list[str] = []
    for category_key, cat in CATEGORIES.items():
        if category_key not in by_cat:
            continue
        lines = [f"{cat['emoji']} {cat['name']}"]
        lines.extend(by_cat[category_key])
        blocks.append("\n".join(lines))
    return blocks


def send_fetch_errors(errors: dict[str, str], warnings: dict[str, str] | None = None) -> bool:
    warnings = warnings or {}
    issues: dict[str, str] = dict(errors)
    for sid, msg in warnings.items():
        if sid not in issues:
            issues[sid] = msg
    if not issues:
        return True

    blocks = _format_fetch_errors(issues)
    if not blocks:
        return True

    title_bits: list[str] = []
    if errors:
        title_bits.append(f"{len(errors)} lỗi")
    if warnings:
        title_bits.append(f"{len(warnings)} cảnh báo")
    title = "⚠️ IR Monitor — " + ", ".join(title_bits)

    # Plain text — tránh parse HTML vỡ vì ký tự < > trong exception
    msg = "\n".join(
        [
            title,
            now(),
            "-" * 28,
            "",
            *blocks,
            "",
            "State nguồn lỗi được giữ nguyên — sẽ thử lại lần chạy sau.",
        ]
    )

    if len(msg) > TELEGRAM_MAX_LEN:
        msg = msg[: TELEGRAM_MAX_LEN - 3] + "…"

    print(f"\n⚠️  {len(issues)} nguồn có vấn đề — gửi Telegram...")
    return send_telegram(msg, html=False)


def _suspect_empty_fetch(sid: str, items: list[dict] | None, known: dict[str, set[str]]) -> str | None:
    """Nguồn từng có tin nhưng lần này trả 0 — có thể bị chặn im lặng."""
    if items is None or items:
        return None
    if len(known.get(sid, set())) < 1:
        return None
    return "Trả về 0 tin (có thể bị chặn hoặc đổi cấu trúc trang)"


def notify_fetch_errors(
    errors: dict[str, str],
    warnings: dict[str, str] | None = None,
) -> None:
    """Báo lỗi/cảnh báo fetch ngay sau khi quét xong."""
    if not errors and not warnings:
        return
    try:
        send_fetch_errors(errors, warnings)
    except Exception as e:
        print(f"  ❌ Không gửi được Telegram lỗi fetch: {e}")


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print(f"IR Monitor — {now()}")
    print(f"{'='*55}\n")

    known, initial_sids = load_state()
    is_first_run = not has_known_items(known)
    if is_first_run:
        print("🆕 Lần đầu / state trống — lưu baseline, chưa gửi tin cũ.\n")

    current_all: dict[str, list[dict]] = {}
    total_new = 0

    fetch_results, fetch_errors = fetch_all_sources()
    fetch_warnings: dict[str, str] = {}
    for source in SOURCES:
        sid = source["id"]
        if sid in fetch_errors:
            continue
        warn = _suspect_empty_fetch(sid, fetch_results.get(sid), known)
        if warn:
            fetch_warnings[sid] = warn
    notify_fetch_errors(fetch_errors, fetch_warnings)

    for source in SOURCES:
        sid = source["id"]
        items = fetch_results.get(sid)
        if items is None:
            print(f"  ⏭️  [{sid}] Giữ state cũ, bỏ qua lần này.\n")
            continue

        raw_count = len(items)
        items = filter_recent_items(items)
        print(
            f"  📅 [{sid}] {len(items)}/{raw_count} tin "
            f"(trong {RECENT_DAYS} ngày / 2 tuần gần nhất)"
        )

        current_all[sid] = items

        # Nguồn mới thêm vào config (chưa có trong file state) — baseline, không gửi tin cũ
        if sid not in initial_sids and has_known_items(known) and not is_first_run:
            merge_uids(known, sid, items)
            write_state(known)
            print(f"  🆕 [{sid}] Nguồn mới — baseline {len(items)} tin, chưa gửi.\n")
            continue

        if is_first_run:
            print()
            continue

        known_uids = known.get(sid, set())
        new_items = [item for item in items if not is_known_item(item, known_uids)]
        if new_items:
            total_new += len(new_items)
            # Lưu UID trước Telegram — tránh lặp nếu crash sau khi gửi
            merge_uids(known, sid, new_items)
            write_state(known)
            print(f"  🔔 [{sid}] {len(new_items)} tin mới! Gửi Telegram...")
            send_new_items(source, new_items)
            time.sleep(1)

        # Gộp UID tin hiện tại (giữ UID cũ ngoài cửa sổ 14 ngày)
        merge_uids(known, sid, items)
        write_state(known)
        print()

    if is_first_run:
        for source in SOURCES:
            sid = source["id"]
            if sid in current_all:
                merge_uids(known, sid, current_all[sid])
        write_state(known)

    if is_first_run:
        summary = _activation_summary(current_all)
        send_telegram(
            "✅ <b>IR Monitor đã kích hoạt!</b>\n\n"
            f"Theo dõi {len(SOURCES)} nguồn (tin {RECENT_DAYS} ngày gần nhất):\n\n{summary}\n\n"
            "Sẽ thông báo khi có tin mới. 🚀"
        )
    elif total_new == 0 and not fetch_errors and not fetch_warnings:
        print("✅ Không có tin mới.")
    elif total_new == 0:
        print("✅ Không có tin mới (có nguồn lỗi/cảnh báo — đã thông báo Telegram).")
    else:
        print(f"\n✅ Đã gửi {total_new} tin mới.")

    print(f"\nHoàn thành — {now()}")


if __name__ == "__main__":
    main()
