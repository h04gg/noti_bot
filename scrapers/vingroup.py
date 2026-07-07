"""
Scraper: Vingroup — HTML SSR (requests + BeautifulSoup)
Hai mục: Công bố thông tin + Đại hội đồng cổ đông.
"""

from __future__ import annotations

import sys

import requests
from bs4 import BeautifulSoup

from scrapers._common import finalize_fetch, make_item

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0
BASE = "https://vingroup.net"


def _parse_page(soup: BeautifulSoup) -> list[dict]:
    items: list[dict] = []
    for a in soup.select("a[href*='ircdn.vingroup.net'], a[href*='/bai-viet/']"):
        title = a.get_text(" ", strip=True).strip()
        if not title:
            continue
        link = a.get("href", "").strip()
        if not link.startswith("http"):
            link = BASE + link

        date = ""
        parent = a.parent
        if parent:
            em = parent.find("em") or parent.find("i")
            if em:
                date = em.get_text(strip=True)

        items.append(make_item(title, link, date))
    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    urls = source.get("urls") or [source["url"]]
    params = source.get("params", {})
    seen_uids: set[str] = set()
    all_items: list[dict] = []

    for i, url in enumerate(urls):
        try:
            resp = session.get(url, params=params, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f"    Vingroup {url}: {e}")
            if i == 0:
                raise RuntimeError(f"Vingroup: {e}") from e
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in _parse_page(soup):
            if item["uid"] in seen_uids:
                continue
            seen_uids.add(item["uid"])
            all_items.append(item)

    return finalize_fetch(_MOD, all_items)
