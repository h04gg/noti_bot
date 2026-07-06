"""
Ghi lỗi fetch theo từng lần chạy bot — tổng hợp gửi Telegram 12:00 (UTC+7) mỗi ngày.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from config import CATEGORIES, SOURCES

ERROR_LOG_FILE = "ir_error_log.json"
LOG_VERSION = 1
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def now_vn() -> datetime:
    return datetime.now(VN_TZ)


def now_vn_str() -> str:
    return now_vn().strftime("%Y-%m-%d %H:%M:%S")


def short_reason(err: str) -> str:
    """Rút gọn exception — dùng cho log và Telegram."""
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
    if "trả về 0 tin" in low:
        return "Trả về 0 tin (có thể bị chặn)"
    return s[:120] + ("…" if len(s) > 120 else "")


def _empty_log() -> dict:
    return {"version": LOG_VERSION, "last_digest_at": None, "entries": []}


def load_error_log() -> dict:
    if not os.path.exists(ERROR_LOG_FILE):
        return _empty_log()
    try:
        with open(ERROR_LOG_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️  Error log hỏng, bắt đầu lại: {e}")
        return _empty_log()
    raw.setdefault("entries", [])
    raw.setdefault("last_digest_at", None)
    return raw


def write_error_log(data: dict) -> None:
    data["version"] = LOG_VERSION
    tmp = f"{ERROR_LOG_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ERROR_LOG_FILE)


def record_fetch_issues(
    errors: dict[str, str],
    warnings: dict[str, str] | None = None,
    *,
    run_id: str | None = None,
) -> int:
    """Ghi lỗi/cảnh báo lần chạy hiện tại. Trả về số entry đã thêm."""
    warnings = warnings or {}
    if not errors and not warnings:
        return 0

    log = load_error_log()
    rid = run_id or now_vn_str()
    added = 0

    for sid, err in errors.items():
        log["entries"].append(
            {
                "run_id": rid,
                "at": rid,
                "sid": sid,
                "reason": short_reason(err),
                "kind": "error",
            }
        )
        added += 1

    for sid, warn in warnings.items():
        if sid in errors:
            continue
        log["entries"].append(
            {
                "run_id": rid,
                "at": rid,
                "sid": sid,
                "reason": short_reason(warn),
                "kind": "warning",
            }
        )
        added += 1

    write_error_log(log)
    return added


def _format_period(last_digest_at: str | None, until: datetime) -> str:
    if last_digest_at:
        try:
            start = datetime.fromisoformat(last_digest_at)
            if start.tzinfo is None:
                start = start.replace(tzinfo=VN_TZ)
            start_s = start.astimezone(VN_TZ).strftime("%d/%m %H:%M")
        except ValueError:
            start_s = last_digest_at[:16]
    else:
        start_s = "(đầu)"
    end_s = until.strftime("%d/%m %H:%M")
    return f"{start_s} → {end_s}"


def build_daily_digest_message(log: dict | None = None) -> str | None:
    """Tổng hợp entries chưa báo cáo. None nếu không có lỗi."""
    log = log or load_error_log()
    entries = log.get("entries") or []
    if not entries:
        return None

    source_by_id = {s["id"]: s for s in SOURCES}
    by_sid: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        by_sid[entry["sid"]].append(entry)

    run_times = {e.get("run_id") or e["at"] for e in entries}
    total_hits = len(entries)
    total_runs = len(run_times)

    until = now_vn()
    period = _format_period(log.get("last_digest_at"), until)
    date_label = until.strftime("%d/%m/%Y")

    lines = [
        f"📊 IR Monitor — Báo cáo lỗi {date_label}",
        f"Kỳ: {period} (12:00 UTC+7)",
        f"Tổng {total_hits} lần gọi lỗi/cảnh báo ({total_runs} lần chạy bot)",
        "-" * 28,
        "",
    ]

    by_cat: dict[str, list[str]] = defaultdict(list)
    for sid, sid_entries in sorted(by_sid.items(), key=lambda x: -len(x[1])):
        source = source_by_id.get(sid)
        if not source:
            continue
        cat_id = source.get("category", "other")
        reasons = Counter(e["reason"] for e in sid_entries)
        kind_tag = ""
        if all(e["kind"] == "warning" for e in sid_entries):
            kind_tag = " [cảnh báo]"
        reason_lines = [f"    · {r} ×{n}" for r, n in reasons.most_common()]
        block = (
            f"  {source['emoji']} {source['name']}: {len(sid_entries)} lần{kind_tag}\n"
            + "\n".join(reason_lines)
        )
        by_cat[cat_id].append(block)

    for cat_id, cat in CATEGORIES.items():
        if cat_id not in by_cat:
            continue
        lines.append(f"{cat['emoji']} {cat['name']}")
        lines.extend(by_cat[cat_id])
        lines.append("")

    lines.append("Sẽ thử lại ở các lần chạy tiếp theo.")
    return "\n".join(lines).strip()


def clear_digest_entries(log: dict | None = None) -> None:
    log = log or load_error_log()
    log["entries"] = []
    log["last_digest_at"] = now_vn().isoformat(timespec="seconds")
    write_error_log(log)


def run_daily_digest(send_fn) -> bool:
    """Gửi báo cáo tổng hợp và xóa entries đã báo. Trả về True nếu đã gửi."""
    log = load_error_log()
    msg = build_daily_digest_message(log)
    if not msg:
        print("📊 Không có lỗi tích lũy — bỏ qua báo cáo.")
        return False

    print(f"\n📊 Gửi báo cáo lỗi hàng ngày ({len(log.get('entries', []))} entry)...")
    if len(msg) > 3800:
        msg = msg[:3780] + "\n…"
    ok = send_fn(msg, html=False)
    if ok:
        clear_digest_entries(log)
    return ok
