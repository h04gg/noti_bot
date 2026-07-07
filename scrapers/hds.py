"""Scraper: HD Securities (HDS) — WordPress (CBTT + Báo cáo tài chính)."""

from __future__ import annotations

import re
import sys

import requests
from bs4 import BeautifulSoup

from config import RECENT_DAYS
from filters import parse_item_date, recent_cutoff
from scrapers._common import (
    extract_dmY,
    finalize_fetch,
    format_dmY,
    make_item,
    page_fetch_failed,
)

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0
BASE = "https://hdbs.vn"
CBTT_PAGE = f"{BASE}/quan-he-co-dong/cong-bo-thong-tin/"
BCTC_PAGE = f"{BASE}/quan-he-co-dong/bao-cao-tai-chinh/"


def _extract_date(anchor, title: str) -> str:
    m = re.search(r"ngày\s+(\d{1,2}/\d{1,2}/\d{4})", title, re.I)
    if m:
        return extract_dmY(m.group(1))
    parent = anchor.find_parent("article") or anchor.parent
    if parent:
        m2 = re.search(r"Tháng\s+(\d{1,2})\s+(\d{1,2}),\s+(\d{4})", parent.get_text(" ", strip=True))
        if m2:
            return format_dmY(m2.group(2), m2.group(1), m2.group(3))
    return extract_dmY(title)


def _parse_listing(soup: BeautifulSoup) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for anchor in soup.select("h4 a[href], article h4 a[href]"):
        title = anchor.get_text(strip=True)
        link = anchor["href"].strip()
        if not title or not link or link in seen:
            continue
        seen.add(link)
        date = _extract_date(anchor, title)
        items.append(make_item(title, link, date))
    return items


def _fetch_section(
    session: requests.Session,
    base_url: str,
    label: str,
    *,
    max_pages: int = 20,
) -> list[dict]:
    all_items: list[dict] = []

    for page in range(1, max_pages + 1):
        url = base_url if page == 1 else f"{base_url.rstrip('/')}/page/{page}/"
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            page_fetch_failed(page, e, f"HDS {label}")

        page_items = _parse_listing(BeautifulSoup(resp.text, "html.parser"))
        if not page_items:
            break

        all_items.extend(page_items)

        dates = [parse_item_date(item.get("date", "")) for item in page_items]
        dates = [dt for dt in dates if dt is not None]
        if dates and min(dates) < recent_cutoff(RECENT_DAYS):
            break

    return all_items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    cbtt_page = source.get("url", CBTT_PAGE)
    bctc_page = source.get("bctc_page", BCTC_PAGE)

    merged: list[dict] = []
    seen_uids: set[str] = set()

    cbtt_items = _fetch_section(session, cbtt_page, "CBTT")
    for item in cbtt_items:
        if item["uid"] in seen_uids:
            continue
        seen_uids.add(item["uid"])
        merged.append(item)

    bctc_items = _fetch_section(session, bctc_page, "BCTC")
    for item in bctc_items:
        if item["uid"] in seen_uids:
            continue
        seen_uids.add(item["uid"])
        merged.append(item)

    print(f"    HDS CBTT: {len(cbtt_items)}, BCTC: {len(bctc_items)}")
    return finalize_fetch(_MOD, merged)
