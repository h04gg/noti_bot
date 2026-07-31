"""Scraper: HSX — API tin tổ chức niêm yết (securitiesType/1)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from config import RECENT_DAYS
from scrapers._common import finalize_fetch, format_dmY, make_item, page_fetch_failed

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0

API_URL = "https://api.hsx.vn/n/api/v1/1/news/securitiesType/1"
DETAIL_URL = "https://www.hsx.vn/Modules/Cms/Web/NewsDetail?id={id}"
SOURCE_PAGE = "https://www.hsx.vn/"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PAGE_SIZE = 100
MAX_PAGES = 50


def _date_range(days: int = RECENT_DAYS) -> tuple[str, str]:
    today = datetime.now(VN_TZ).date()
    start = today - timedelta(days=days)
    return start.isoformat(), today.isoformat()


def _doc_date(posted: int | float | None) -> str:
    if not posted:
        return ""
    try:
        dt = datetime.fromtimestamp(int(posted), tz=VN_TZ)
    except (OverflowError, OSError, ValueError, TypeError):
        return ""
    return format_dmY(dt.day, dt.month, dt.year)


def _doc_link(doc: dict) -> str:
    link = (doc.get("link") or "").strip()
    if link.startswith("http"):
        return link
    news_id = doc.get("id")
    if news_id is None:
        return ""
    return DETAIL_URL.format(id=news_id)


def fetch(source: dict, session: requests.Session) -> list[dict]:
    api_url = source.get("api_url", API_URL)
    page_size = int(source.get("params", {}).get("pageSize", PAGE_SIZE))
    start_date, end_date = _date_range()
    referer = source.get("source_page", SOURCE_PAGE)

    all_items: list[dict] = []
    seen: set[str] = set()
    page = 1
    total_pages = 1

    while page <= max(total_pages, 1) and page <= MAX_PAGES:
        try:
            resp = session.get(
                api_url,
                params={
                    "pageIndex": page,
                    "pageSize": page_size,
                    "startDate": start_date,
                    "endDate": end_date,
                },
                timeout=30,
                headers={
                    "Accept": "application/json",
                    "Accept-Language": "vi-VN,vi;q=0.9",
                    "Referer": referer,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            page_fetch_failed(page, e, "HSX")
            break

        if not payload.get("success", True):
            raise RuntimeError(f"HSX API: {payload.get('message') or 'success=false'}")

        block = payload.get("data") or {}
        docs = block.get("list") or []
        paging = block.get("paging") or {}
        total_pages = int(paging.get("totalPages") or 1)

        if not docs:
            break

        added = 0
        for doc in docs:
            title = (doc.get("title") or "").strip()
            link = _doc_link(doc)
            if not title or not link:
                continue
            item = make_item(title, link, _doc_date(doc.get("postedDate")))
            if item["uid"] in seen:
                continue
            seen.add(item["uid"])
            all_items.append(item)
            added += 1

        print(f"    HSX page {page}/{total_pages}: +{added} (start={start_date}, end={end_date})")

        if page >= total_pages:
            break
        page += 1

    if not all_items:
        raise RuntimeError("HSX: không lấy được tin (API rỗng hoặc lỗi)")

    print(f"    HSX tổng: {len(all_items)} tin ({start_date} → {end_date})")
    return finalize_fetch(_MOD, all_items)
