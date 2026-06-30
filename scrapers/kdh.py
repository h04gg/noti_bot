"""Scraper: Khang Điền (KDH) — PDF từ trang Công bố thông tin."""

from __future__ import annotations

import re
import requests
from bs4 import BeautifulSoup

from scrapers._common import extract_dmY, format_dmY, make_item, paginate_until_recent

BASE = "https://www.khangdien.com.vn"


def fetch(source: dict, session: requests.Session) -> list[dict]:
    page_url = source.get("url", f"{BASE}/co-dong/cong-bo-thong-tin")

    def _page(page: int) -> list[dict]:
        params = {"page": page} if page > 1 else None
        try:
            resp = session.get(page_url, params=params, timeout=20)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
        except Exception as e:
            print(f"    KDH page {page}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items: list[dict] = []
        seen: set[str] = set()

        for a in soup.select('a[href*=".pdf"]'):
            link = a.get("href", "").strip()
            if not link or link in seen:
                continue
            if not link.startswith("http"):
                link = BASE + link
            seen.add(link)

            title = a.get_text(" ", strip=True)
            if not title or len(title) < 5:
                continue

            date = ""
            parent = a.parent
            for _ in range(4):
                if not parent:
                    break
                date = extract_dmY(parent.get_text(" ", strip=True))
                if date:
                    break
                parent = parent.parent
            if not date:
                dm = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", link)
                if dm:
                    date = format_dmY(dm.group(3), dm.group(2), dm.group(1))

            items.append(make_item(title, link, date))
        return items

    return paginate_until_recent(_page)
