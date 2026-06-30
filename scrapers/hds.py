"""Scraper: HD Securities (HDS) — WordPress."""

from __future__ import annotations

import re
import requests
from bs4 import BeautifulSoup

from scrapers._common import extract_dmY, format_dmY, make_item, paginate_until_recent

BASE = "https://hdbs.vn"


def fetch(source: dict, session: requests.Session) -> list[dict]:
    base_url = source.get("url", f"{BASE}/quan-he-co-dong/cong-bo-thong-tin/")

    def _page(page: int) -> list[dict]:
        url = base_url if page == 1 else f"{base_url}page/{page}/"
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f"    HDS page {page}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items: list[dict] = []
        seen: set[str] = set()
        for a in soup.select("h4 a[href], article h4 a[href]"):
            title = a.get_text(strip=True)
            link = a["href"].strip()
            if not title or not link or link in seen:
                continue
            seen.add(link)
            date = _extract_date(a, title)
            items.append(make_item(title, link, date))
        return items

    return paginate_until_recent(_page)


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
