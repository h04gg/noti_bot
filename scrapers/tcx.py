"""Scraper: Techcom Securities (TCX/TCBS)."""

from __future__ import annotations

import re
import requests
from bs4 import BeautifulSoup

from scrapers._common import extract_dmY, make_item, paginate_until_recent

BASE = "https://www.tcbs.com.vn"


def fetch(source: dict, session: requests.Session) -> list[dict]:
    page_url = source.get("url", f"{BASE}/nha-dau-tu/quan-he-nha-dau-tu/cong-bo-thong-tin/")

    def _page(page: int) -> list[dict]:
        params = {"page": page} if page > 1 else None
        try:
            resp = session.get(page_url, params=params, timeout=25, verify=False)
            resp.raise_for_status()
        except Exception as e:
            print(f"    TCX page {page}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items: list[dict] = []
        seen: set[str] = set()
        for h in soup.select("h2"):
            title = h.get_text(strip=True)
            if not title.startswith("CBTT"):
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

    return paginate_until_recent(_page, max_pages=1)
