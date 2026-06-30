"""Scraper: SSI Securities."""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from scrapers._common import extract_dmY, make_item, paginate_until_recent

BASE = "https://www.ssi.com.vn"


def fetch(source: dict, session: requests.Session) -> list[dict]:
    page_url = source.get("url", f"{BASE}/quan-he-nha-dau-tu/cong-bo-thong-tin")

    def _page(page: int) -> list[dict]:
        params = {"page": page} if page > 1 else None
        try:
            resp = session.get(page_url, params=params, timeout=25, verify=False)
            resp.raise_for_status()
        except Exception as e:
            print(f"    SSI page {page}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items: list[dict] = []
        seen: set[str] = set()
        for block in soup.select(".chart__content__item"):
            a = block.select_one("a.titlePost[href]")
            if not a:
                continue
            title = a.get_text(strip=True)
            link = a["href"].strip()
            if not title or link in seen:
                continue
            seen.add(link)
            time_el = block.select_one(".chart__content__item__time span")
            date = extract_dmY(time_el.get_text(strip=True) if time_el else "")
            items.append(make_item(title, link, date))
        return items

    return paginate_until_recent(_page)
