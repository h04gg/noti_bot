"""
IR Monitor — Theo dõi tin tức mới từ các trang IR và gửi Telegram
"""

from __future__ import annotations

import os
import json
import time
import importlib
import requests
from html import escape
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import SOURCES, CATEGORIES, RECENT_DAYS
from filters import filter_recent_items
from fetch_error_log import record_fetch_issues, run_daily_digest, now_vn_str
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

FETCH_RETRIES = 2
FETCH_RETRY_DELAY = 3  # giây


# ── Scraping ───────────────────────────────────────────────────────────────────
def fetch_source(
    source: dict, session: requests.Session
) -> tuple[list[dict] | None, str | None, int | None]:
    """Trả về (items, error, raw_count). items=None nghĩa là fetch thất bại sau retry."""
    sid = source["id"]
    scraper = SCRAPER_MAP.get(sid)
    if not scraper:
        msg = "Không có scraper"
        print(f"  ⚠️  [{sid}] {msg}")
        return None, msg, None

    print(f"  📡 [{sid}] Fetching...")
    last_error: Exception | None = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            items = scraper.fetch(source, session)
            raw_count = getattr(scraper, "LAST_RAW_COUNT", None)
            # Scraper chưa set LAST_RAW_COUNT: dùng số tin trước khi monitor lọc ngày
            if raw_count is None and items is not None:
                raw_count = len(items)
            if attempt > 1:
                print(f"  ✅ [{sid}] {len(items)} items (sau {attempt} lần thử)")
            else:
                print(f"  ✅ [{sid}] {len(items)} items")
            return items, None, raw_count
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
    return None, err, None


def fetch_all_sources() -> tuple[dict[str, list[dict] | None], dict[str, str], dict[str, int]]:
    """Fetch tất cả nguồn song song. Trả về (kết quả, lỗi, raw_count trước lọc ngày)."""
    results: dict[str, list[dict] | None] = {}
    errors: dict[str, str] = {}
    raw_counts: dict[str, int] = {}

    def _fetch_one(source: dict) -> tuple[str, list[dict] | None, str | None, int | None]:
        session = requests.Session()
        session.headers.update(HEADERS)
        sid = source["id"]
        items, error, raw_count = fetch_source(source, session)
        return sid, items, error, raw_count

    print(f"📡 Fetching {len(SOURCES)} nguồn song song (workers={FETCH_WORKERS})...\n")
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
        futures = [executor.submit(_fetch_one, source) for source in SOURCES]
        for future in as_completed(futures):
            sid, items, error, raw_count = future.result()
            results[sid] = items
            if error:
                errors[sid] = error
            if raw_count is not None:
                raw_counts[sid] = raw_count

    return results, errors, raw_counts


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


def _company_header(item: dict, total_new: int, part: str = "") -> str:
    if item.get("is_other"):
        header = f"📋 <b>Khác — {total_new} tin mới</b>"
    else:
        sector_emoji = item.get("sector_emoji") or "📈"
        sector = item.get("sector") or "Sàn"
        company_emoji = item.get("company_emoji") or "🏛️"
        company = item.get("company") or item.get("symbol") or "Unknown"
        symbol = item.get("symbol") or ""
        header = (
            f"{sector_emoji} <b>{sector}</b> · "
            f"{company_emoji} <b>{company} ({symbol}) — {total_new} tin mới</b>"
        )
    if part:
        header += f" <i>{part}</i>"
    return header


def _grouped_message_chunks(
    source: dict, new_items: list[dict], total_new: int, sample: dict
) -> list[str]:
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
        header = _company_header(
            sample,
            total_new,
            part=f"({i + 1}/{total_parts})" if total_parts > 1 else "",
        )
        msg = header + "\n" + "─" * 28 + "\n\n" + "\n".join(part_lines)
        if i == 0 and total_new > len(new_items):
            msg += f"\n\n<i>… và {total_new - len(new_items)} tin khác (xem tại link nguồn)</i>"
        msg += footer
        messages.append(msg)
    return messages


def _watchlist_order(source_id: str) -> dict:
    if source_id == "hnx":
        from hnx_watchlist import HNX_WATCHLIST

        return HNX_WATCHLIST
    from hose_watchlist import HOSE_WATCHLIST

    return HOSE_WATCHLIST


OTHER_GROUP_KEY = "_OTHER_"


def _group_by_symbol(
    new_items: list[dict], *, source_id: str
) -> list[tuple[str, list[dict]]]:
    """Watchlist theo thứ tự sheet; phần còn lại gom mục Khác."""
    order = _watchlist_order(source_id)
    buckets: dict[str, list[dict]] = {}
    others: list[dict] = []

    for item in new_items:
        symbol = (item.get("symbol") or "").upper()
        if item.get("is_other") or symbol not in order:
            others.append(item)
            continue
        buckets.setdefault(symbol, []).append(item)

    ordered: list[tuple[str, list[dict]]] = []
    for symbol in order:
        if symbol in buckets:
            ordered.append((symbol, buckets.pop(symbol)))
    for symbol, items in buckets.items():
        ordered.append((symbol, items))
    if others:
        # Đánh dấu sample để header dùng mục Khác
        for it in others:
            it["is_other"] = True
        ordered.append((OTHER_GROUP_KEY, others))
    return ordered


def send_grouped_by_symbol(source: dict, new_items: list[dict]) -> bool:
    """Một tin nhắn / mã watchlist; tin ngoài list → 1 tin nhắn Khác."""
    ok = True
    groups = _group_by_symbol(new_items, source_id=source.get("id", ""))
    for gi, (symbol, items) in enumerate(groups):
        total = len(items)
        label = "Khác" if symbol == OTHER_GROUP_KEY else symbol
        if total > TELEGRAM_MAX_ITEMS:
            to_send = items[:TELEGRAM_MAX_ITEMS]
            print(f"    [{label}] chỉ gửi {len(to_send)}/{total} tin")
        else:
            to_send = items
        chunks = _grouped_message_chunks(source, to_send, total_new=total, sample=items[0])
        for i, msg in enumerate(chunks):
            if not send_telegram(msg):
                ok = False
            if i < len(chunks) - 1:
                time.sleep(0.5)
        if gi < len(groups) - 1:
            time.sleep(0.5)
    return ok


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
    if source.get("id") in ("hsx", "hnx"):
        return send_grouped_by_symbol(source, new_items)

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


def _suspect_empty_fetch(
    sid: str,
    items: list[dict] | None,
    known: dict[str, set[str]],
    raw_count: int | None = None,
) -> str | None:
    """Nguồn từng có tin nhưng lần này trả 0 — có thể bị chặn im lặng."""
    if items is None or items:
        return None
    if raw_count and raw_count > 0:
        return None
    if len(known.get(sid, set())) < 1:
        return None
    return "Trả về 0 tin (có thể bị chặn hoặc đổi cấu trúc trang)"


def record_fetch_issues_for_run(
    errors: dict[str, str],
    warnings: dict[str, str] | None = None,
    *,
    run_id: str | None = None,
) -> None:
    """Ghi lỗi vào log — báo cáo Telegram lúc 12:00 UTC+7."""
    try:
        n = record_fetch_issues(errors, warnings, run_id=run_id)
        if n:
            print(f"\n📝 Đã ghi {n} lỗi/cảnh báo vào log (báo cáo 12:00 UTC+7).")
    except Exception as e:
        print(f"  ❌ Không ghi được error log: {e}")


def daily_digest_main() -> None:
    print(f"\n{'='*55}")
    print(f"IR Monitor — Báo cáo lỗi hàng ngày — {now()}")
    print(f"{'='*55}\n")
    run_daily_digest(send_telegram)
    print(f"\nHoàn thành — {now()}")


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

    fetch_results, fetch_errors, fetch_raw_counts = fetch_all_sources()
    fetch_warnings: dict[str, str] = {}
    for source in SOURCES:
        sid = source["id"]
        if sid in fetch_errors:
            continue
        warn = _suspect_empty_fetch(
            sid, fetch_results.get(sid), known, fetch_raw_counts.get(sid)
        )
        if warn:
            fetch_warnings[sid] = warn
    record_fetch_issues_for_run(
        fetch_errors, fetch_warnings, run_id=now_vn_str()
    )

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
            f"(trong {RECENT_DAYS} ngày gần nhất)"
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

        # Gộp UID tin hiện tại (giữ UID cũ ngoài cửa sổ RECENT_DAYS)
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
        print("✅ Không có tin mới (lỗi đã ghi log — báo cáo 12:00 UTC+7).")
    else:
        print(f"\n✅ Đã gửi {total_new} tin mới.")

    print(f"\nHoàn thành — {now()}")


if __name__ == "__main__":
    import sys

    if "--daily-digest" in sys.argv:
        daily_digest_main()
    else:
        main()
