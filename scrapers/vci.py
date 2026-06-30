"""Scraper: Vietcap (VCI) — danh sách tin Quan hệ cổ đông."""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from scrapers._common import extract_dmY, make_item, paginate_until_recent

BASE = "https://www.vietcap.com.vn"
SKIP_SLUGS = {
    "thong-tin-co-dong",
    "bao-cao-tai-chinh",
    "bao-cao-thuong-nien",
    "chi-so-an-toan-tai-chinh",
    "cong-bo-thong-tin-khac",
}


def fetch(source: dict, session: requests.Session) -> list[dict]:
    page_url = source.get("url", f"{BASE}/quan-he-co-dong/")

    def _page(page: int) -> list[dict]:
        params = {"page": page} if page > 1 else None
        try:
            resp = session.get(page_url, params=params, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f"    VCI page {page}: {e}")
            return []

        soup = BeautifulSoup(resp.content, "html.parser")
        items: list[dict] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("/quan-he-co-dong/"):
                continue
            slug = href.replace("/quan-he-co-dong/", "").strip("/")
            if not slug or slug in SKIP_SLUGS:
                continue
            title = a.get_text(strip=True)
            if len(title) < 20:
                continue
            link = BASE + href
            if link in seen:
                continue
            seen.add(link)
            row = a.find_parent(["div", "li", "article"])
            date = extract_dmY(row.get_text(" ", strip=True) if row else "")
            items.append(make_item(title, link, date))
        return items

    return paginate_until_recent(_page)
