"""
Lọc tin theo khoảng thời gian — áp dụng cho mọi nguồn (kể cả nguồn mới).
Mỗi scraper cần trả về field `date` (dd/mm/yyyy hoặc yyyy-mm-dd).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from config import RECENT_DAYS


def recent_cutoff(days: int = RECENT_DAYS) -> datetime:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)


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


def is_recent_item(item: dict, days: int = RECENT_DAYS) -> bool:
    dt = parse_item_date(item.get("date", ""))
    return dt is not None and dt >= recent_cutoff(days)


def filter_recent_items(items: list[dict], days: int = RECENT_DAYS) -> list[dict]:
    return [item for item in items if is_recent_item(item, days)]


def newest_item_date(items: list[dict]) -> datetime | None:
    dates = [parse_item_date(item.get("date", "")) for item in items]
    dates = [dt for dt in dates if dt is not None]
    return max(dates) if dates else None
