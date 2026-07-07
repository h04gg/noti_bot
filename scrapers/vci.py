"""Scraper: Vietcap (VCI) — Quan hệ cổ đông + Báo cáo tài chính."""

from __future__ import annotations

import sys

import requests
from bs4 import BeautifulSoup

from config import RECENT_DAYS
from filters import parse_item_date, recent_cutoff
from scrapers._common import extract_dmY, finalize_fetch, make_item, page_fetch_failed

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0
BASE = "https://www.vietcap.com.vn"
CBTT_PAGE = f"{BASE}/quan-he-co-dong/"
BCTC_PAGE = f"{BASE}/quan-he-co-dong/bao-cao-tai-chinh"

SKIP_SLUGS = {
    "thong-tin-co-dong",
    "bao-cao-tai-chinh",
    "bao-cao-thuong-nien",
    "chi-so-an-toan-tai-chinh",
    "cong-bo-thong-tin-khac",
}


def _parse_listing(soup: BeautifulSoup) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not href.startswith("/quan-he-co-dong/"):
            continue
        slug = href.replace("/quan-he-co-dong/", "").strip("/")
        if not slug or slug in SKIP_SLUGS or "?" in slug:
            continue
        title = anchor.get_text(strip=True)
        if len(title) < 20:
            continue
        link = BASE + href.split("?")[0]
        if link in seen:
            continue
        seen.add(link)
        row = anchor.find_parent(["div", "li", "article"])
        date = extract_dmY(row.get_text(" ", strip=True) if row else "")
        items.append(make_item(title, link, date))
    return items


def _fetch_section(
    session: requests.Session,
    page_url: str,
    label: str,
    *,
    max_pages: int = 20,
) -> list[dict]:
    """Phân trang đến khi trang cuối cũ hơn RECENT_DAYS — lọc ngày ở monitor."""
    all_items: list[dict] = []

    for page in range(1, max_pages + 1):
        params = {"page": page} if page > 1 else None
        try:
            resp = session.get(page_url, params=params, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            page_fetch_failed(page, e, f"VCI {label}")

        page_items = _parse_listing(BeautifulSoup(resp.content, "html.parser"))
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

    print(f"    VCI CBTT: {len(cbtt_items)}, BCTC: {len(bctc_items)}")
    return finalize_fetch(_MOD, merged)
