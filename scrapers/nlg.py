"""Scraper: Nam Long (NLG) — mục Công bố thông tin (Quan hệ nhà đầu tư)."""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from scrapers._common import extract_dmY, format_dmY, make_item

BASE = "https://www.namlongvn.com"
PAGE_URL = f"{BASE}/quan-he-nha-dau-tu/"


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


def fetch(source: dict, session: requests.Session) -> list[dict]:
    url = source.get("url", PAGE_URL)
    resp = session.get(url, timeout=25)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    disclosure = soup.select_one("#disclosure")
    if not disclosure:
        print("    NLG: không tìm thấy tab Công bố thông tin")
        return []

    seen: set[str] = set()
    items: list[dict] = []
    for doc in disclosure.select(".doc-list.year-disclosure .doc-item"):
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
