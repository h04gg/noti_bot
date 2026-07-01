"""Scraper: BVSC (Bảo Việt Securities) — JSON API getPaginateCBTT_V2."""

from __future__ import annotations

from datetime import datetime

import requests

from config import RECENT_DAYS
from filters import filter_recent_items, newest_item_date, recent_cutoff
from scrapers._common import make_item

BASE = "https://www.bvsc.com.vn"
API_URL = f"{BASE}/getPaginateCBTT_V2"


def _warmup(session: requests.Session, source: dict) -> None:
    source_page = source.get("source_page", f"{BASE}/quan-he-co-dong")
    session.headers.setdefault("Referer", source_page)
    session.headers.setdefault("X-Requested-With", "XMLHttpRequest")
    session.get(source_page, timeout=20)


def fetch(source: dict, session: requests.Session) -> list[dict]:
    api_url = source.get("api_url", API_URL)
    _warmup(session, source)

    params = dict(source.get("params", {}))
    page_size = int(params.get("pagesizes", 10))
    current_page = int(params.pop("currentPage", 1))
    params.setdefault("language", "vi")
    params["year"] = datetime.now().year

    all_items: list[dict] = []
    while True:
        params["currentPage"] = current_page
        page_items, total_pages = _fetch_page(session, api_url, params)
        all_items.extend(page_items)

        if not page_items or current_page >= total_pages:
            break

        page_newest = newest_item_date(page_items)
        if page_newest and page_newest < recent_cutoff(RECENT_DAYS):
            break

        current_page += 1

    return filter_recent_items(all_items)


def _fetch_page(
    session: requests.Session, api_url: str, params: dict
) -> tuple[list[dict], int]:
    try:
        resp = session.get(api_url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    BVSC page {params.get('currentPage', 1)}: {e}")
        return [], 0

    if not data.get("success"):
        print(f"    BVSC page {params.get('currentPage', 1)}: API success=false")
        return [], 0

    blocks = data.get("data") or []
    if not blocks:
        return [], 0

    block = blocks[0]
    total_pages = int(block.get("totalPage", 1))
    items: list[dict] = []

    for doc in block.get("list") or []:
        title = (doc.get("tieu_de") or "").strip()
        link = (doc.get("link") or "").strip()
        if not title or not link:
            continue
        if not link.startswith("http"):
            link = BASE + link

        date = (doc.get("ngay") or "").strip()
        items.append(make_item(title, link, date))

    return items, total_pages
