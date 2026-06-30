"""Scraper: Novaland (NVL) — bảng PDF Công bố thông tin."""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from scrapers._common import extract_dmY, make_item, paginate_until_recent

BASE = "https://www.novaland.com.vn"


def fetch(source: dict, session: requests.Session) -> list[dict]:
    page_url = source.get("url", f"{BASE}/quan-he-dau-tu/cong-bo-thong-tin/thong-bao")

    def _page(page: int) -> list[dict]:
        params = {"page": page} if page > 1 else None
        try:
            resp = session.get(page_url, params=params, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f"    NVL page {page}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items: list[dict] = []
        seen: set[str] = set()
        for tr in soup.select("table tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            a = tds[0].find("a", href=True)
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            link = a["href"].strip()
            if not link.startswith("http"):
                link = BASE + link
            if link in seen:
                continue
            seen.add(link)
            date = extract_dmY(tds[1].get_text(strip=True))
            items.append(make_item(title, link, date))
        return items

    return paginate_until_recent(_page)
