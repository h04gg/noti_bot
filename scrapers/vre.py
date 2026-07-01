"""Scraper: Vincom Retail (VRE) — Công bố thông tin."""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from scrapers._common import extract_dmY, make_item, paginate_until_recent

BASE = "https://ir.vincom.com.vn"
PAGE_URL = f"{BASE}/cong-bo-thong-tin/cong-bo-thong-tin-vi/"


def _page_url(base: str, page: int) -> str:
    if page <= 1:
        return base
    return f"{base.rstrip('/')}/page/{page}/"


def fetch(source: dict, session: requests.Session) -> list[dict]:
    base_url = source.get("url", PAGE_URL)

    def _page(page: int) -> list[dict]:
        try:
            resp = session.get(_page_url(base_url, page), timeout=25)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
        except Exception as e:
            print(f"    VRE page {page}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items: list[dict] = []
        seen: set[str] = set()
        for col in soup.select(".post-list-resource .column.post"):
            a = col.select_one("h6 a[href]")
            if not a:
                continue
            link = a["href"].strip()
            if not link or link in seen:
                continue
            if not link.startswith("http"):
                link = BASE + link
            seen.add(link)

            title = (a.get("title") or a.get_text(" ", strip=True)).strip()
            if not title:
                continue

            time_el = col.select_one("time.entry-date")
            date = extract_dmY(time_el.get_text(" ", strip=True) if time_el else "")
            items.append(make_item(title, link, date))
        return items

    return paginate_until_recent(_page)
