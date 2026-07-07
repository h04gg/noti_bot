"""Scraper: Nam Long (NLG) — tab Công bố thông tin + Báo cáo tài chính."""

from __future__ import annotations

import re
import sys

from bs4 import BeautifulSoup

from filters import filter_recent_items
from scrapers._common import curl_get_text, extract_dmY, format_dmY, make_item

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0
BASE = "https://www.namlongvn.com"
PAGE_URL = f"{BASE}/quan-he-nha-dau-tu/"

_SECTIONS = (
    ("disclosure", "year-disclosure", "CBTT"),
    ("financial", "year-financial", "BCTC"),
)


def _parse_date(raw: str, link: str) -> str:
    date = extract_dmY(raw)
    if date:
        return date
    m = re.search(r"/(20\d{2})/(\d{2})/", link)
    if m:
        return format_dmY("01", m.group(2), m.group(1))
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", link)
    if m:
        return format_dmY(m.group(3), m.group(2), m.group(1))
    return ""


def _parse_section(soup: BeautifulSoup, section_id: str, list_class: str) -> list[dict]:
    section = soup.select_one(f"#{section_id}")
    if not section:
        return []

    items: list[dict] = []
    seen: set[str] = set()
    for doc in section.select(f".doc-list.{list_class} .doc-item"):
        title_a = doc.select_one(".doc-title a[href]")
        if not title_a:
            continue
        title = title_a.get_text(" ", strip=True)
        link = title_a["href"].strip()
        if not title or not link or link in seen:
            continue
        if not link.startswith("http"):
            link = BASE + link
        seen.add(link)

        dt_el = doc.select_one(".datetime-label")
        date = _parse_date(dt_el.get_text(strip=True) if dt_el else "", link)
        items.append(make_item(title, link, date))

    return items


def fetch(source: dict, session) -> list[dict]:
    url = source.get("url", PAGE_URL)
    try:
        html = curl_get_text(url, source_id="nlg", timeout=25)
    except Exception as e:
        print(f"    NLG HTML: {e}")
        raise

    soup = BeautifulSoup(html, "html.parser")
    merged: list[dict] = []
    seen_uids: set[str] = set()

    for section_id, list_class, label in _SECTIONS:
        section_items = _parse_section(soup, section_id, list_class)
        if not section_items and section_id == "disclosure":
            print(f"    NLG: không tìm thấy tab {label}")
            raise RuntimeError(f"NLG: không tìm thấy tab {label}")
        if not section_items:
            print(f"    NLG: không tìm thấy tab {label}")
            continue
        for item in section_items:
            if item["uid"] in seen_uids:
                continue
            seen_uids.add(item["uid"])
            merged.append(item)

    _MOD.LAST_RAW_COUNT = len(merged)
    return filter_recent_items(merged)
