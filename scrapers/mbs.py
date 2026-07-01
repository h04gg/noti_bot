"""Scraper: MB Securities (MBS) — HTML (Cloudflare → curl_cffi)."""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from scrapers._common import extract_dmY, make_item, paginate_until_recent

BASE = "https://www.mbs.com.vn"
PAGE_URL = f"{BASE}/cong-bo-thong-tin/"
IMPERSONATE = "chrome120"


def _page_url(base: str, page: int) -> str:
    if page <= 1:
        return base
    return f"{base.rstrip('/')}/page/{page}/"


def _parse_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()
    for block in soup.select("div.flex.flex-col.gap-4"):
        a = block.select_one("h3 a[href]")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        link = a["href"].strip()
        if not title or not link or link in seen:
            continue
        if not link.startswith("http"):
            link = BASE + link
        seen.add(link)

        date_el = block.select_one("p")
        date = extract_dmY(date_el.get_text(strip=True) if date_el else "") or extract_dmY(title)
        items.append(make_item(title, link, date))
    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    base_url = source.get("url", PAGE_URL)

    def _page(page: int) -> list[dict]:
        url = _page_url(base_url, page)
        try:
            resp = curl_requests.get(
                url,
                impersonate=IMPERSONATE,
                timeout=30,
                headers={"Accept-Language": "vi-VN,vi;q=0.9"},
            )
            if resp.status_code == 403:
                print("    MBS: bị chặn bot (403)")
                return []
            resp.raise_for_status()
        except Exception as e:
            print(f"    MBS page {page}: {e}")
            return []
        return _parse_html(resp.text)

    return paginate_until_recent(_page)
