"""Scraper: VIX Securities — HTML bảng Công bố thông tin."""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from scrapers._common import extract_dmY, make_item, paginate_until_recent

BASE = "https://vixs.vn"
PAGE_PATH = "/qhcd/cong-bo-thong-tin"
DEFAULT_PARAMS = {"num": 20, "y": -1}


def _page_url(base_path: str, params: dict, page: int) -> str:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    if page <= 1:
        return f"{BASE}{base_path}?{query}"
    return f"{BASE}{base_path}/page/{page}?{query}"


def _parse_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()
    for tr in soup.select("tbody tr"):
        title_a = tr.select_one(".bic-report__title a[href]")
        if not title_a:
            continue
        title = title_a.get_text(" ", strip=True)
        link = title_a["href"].strip()
        if not title or not link or link in seen:
            continue
        if not link.startswith("http"):
            link = BASE + link
        seen.add(link)

        date_el = tr.select_one(".bic-report__date")
        date = extract_dmY(date_el.get_text(strip=True) if date_el else "")
        items.append(make_item(title, link, date))
    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    path = source.get("path", PAGE_PATH)
    params = dict(source.get("params", DEFAULT_PARAMS))

    def _page(page: int) -> list[dict]:
        url = _page_url(path, params, page)
        try:
            resp = session.get(url, timeout=25)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
        except Exception as e:
            print(f"    VIX page {page}: {e}")
            return []
        return _parse_html(resp.text)

    return paginate_until_recent(_page)
