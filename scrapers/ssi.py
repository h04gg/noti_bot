"""Scraper: SSI Securities."""

from __future__ import annotations

import re
import sys

import requests
from bs4 import BeautifulSoup

from config import RECENT_DAYS
from filters import parse_item_date, recent_cutoff
from scrapers._common import extract_dmY, finalize_fetch, make_item, page_fetch_failed

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0
BASE = "https://www.ssi.com.vn"
_FILENAME_DATE_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})")


def _parse_listing(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()
    for block in soup.select(".chart__content__item"):
        a = block.select_one("a.titlePost[href]")
        title = ""
        link = ""
        if a:
            title = a.get_text(strip=True)
            link = a["href"].strip()
        else:
            desc = block.select_one(".chart__content__item__desc")
            dl = block.select_one(".chart__content__item__time a[href], a[download][href]")
            if desc and dl:
                title = desc.get_text(" ", strip=True)
                link = dl["href"].strip()
        if not title or not link or link in seen:
            continue
        if not link.startswith("http"):
            link = BASE + link
        seen.add(link)
        time_el = block.select_one(".chart__content__item__time span")
        date = extract_dmY(time_el.get_text(strip=True) if time_el else "")
        if not date:
            m = _FILENAME_DATE_RE.search(link)
            if m:
                date = f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
        if not date:
            date = extract_dmY(title)
        items.append(make_item(title, link, date))
    return items


def _fetch_section(session: requests.Session, page_url: str, label: str) -> list[dict]:
    all_items: list[dict] = []
    for page in range(1, 21):
        params = {"page": page} if page > 1 else None
        try:
            resp = session.get(page_url, params=params, timeout=25, verify=False)
            resp.raise_for_status()
        except Exception as e:
            page_fetch_failed(page, e, f"SSI {label}")
        page_items = _parse_listing(resp.text)
        if not page_items:
            break
        all_items.extend(page_items)
        dates = [parse_item_date(item.get("date", "")) for item in page_items]
        dates = [dt for dt in dates if dt is not None]
        if dates and min(dates) < recent_cutoff(RECENT_DAYS):
            break
    return all_items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    cbtt_page = source.get("url", f"{BASE}/quan-he-nha-dau-tu/cong-bo-thong-tin")
    bctc_page = source.get("bctc_page", f"{BASE}/quan-he-nha-dau-tu/bao-cao-tai-chinh")

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

    print(f"    SSI CBTT: {len(cbtt_items)}, BCTC: {len(bctc_items)}")
    return finalize_fetch(_MOD, merged)
