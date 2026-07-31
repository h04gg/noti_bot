"""Scraper: Techcom Securities (TCX/TCBS)."""

from __future__ import annotations

import sys

import requests
from bs4 import BeautifulSoup

from config import RECENT_DAYS
from filters import parse_item_date, recent_cutoff
from scrapers._common import extract_dmY, finalize_fetch, make_item, page_fetch_failed

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0
BASE = "https://www.tcbs.com.vn"


def _parse_page(html: str, *, cbtt_only: bool = True) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()
    for h in soup.select("h2"):
        title = h.get_text(strip=True)
        if cbtt_only and not title.startswith("CBTT"):
            continue
        if len(title) < 10:
            continue
        a = h.find("a", href=True) or h.find_parent("a", href=True)
        if not a:
            continue
        link = a["href"].strip()
        if not link.startswith("http"):
            link = BASE + link
        if link in seen:
            continue
        seen.add(link)
        parent = h.parent
        date = extract_dmY(parent.get_text(" ", strip=True) if parent else "")
        if not date:
            date = extract_dmY(title)
        items.append(make_item(title, link, date))
    return items


def _fetch_pages(
    session: requests.Session,
    page_url: str,
    label: str,
    *,
    cbtt_only: bool = True,
    max_pages: int = 20,
) -> list[dict]:
    all_items: list[dict] = []
    for page in range(1, max_pages + 1):
        params = {"page": page} if page > 1 else None
        try:
            resp = session.get(page_url, params=params, timeout=25, verify=False)
            resp.raise_for_status()
        except Exception as e:
            page_fetch_failed(page, e, f"TCX {label}")
        page_items = _parse_page(resp.text, cbtt_only=cbtt_only)
        if not page_items:
            break
        all_items.extend(page_items)
        dates = [parse_item_date(item.get("date", "")) for item in page_items]
        dates = [dt for dt in dates if dt is not None]
        if dates and min(dates) < recent_cutoff(RECENT_DAYS):
            break
    return all_items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    feeds = source.get("feeds") or [
        {
            "url": source.get(
                "url",
                f"{BASE}/nha-dau-tu/quan-he-nha-dau-tu/cong-bo-thong-tin/",
            ),
            "label": "CBTT",
            "cbtt_only": True,
        }
    ]

    merged: list[dict] = []
    seen_uids: set[str] = set()
    counts: list[str] = []

    for i, feed in enumerate(feeds):
        page_url = feed["url"]
        label = feed.get("label", "feed")
        batch = _fetch_pages(
            session,
            page_url,
            label,
            cbtt_only=bool(feed.get("cbtt_only", False)),
            max_pages=int(feed.get("max_pages", 20)),
        )
        if not batch and i == 0:
            raise RuntimeError(f"TCX {label}: không lấy được tin")
        counts.append(f"{label}: {len(batch)}")
        for item in batch:
            if item["uid"] in seen_uids:
                continue
            seen_uids.add(item["uid"])
            merged.append(item)

    if counts:
        print(f"    TCX {', '.join(counts)}")
    return finalize_fetch(_MOD, merged)
