"""Scraper: Vinhomes (VHM) — Công bố thông tin (Cloudflare → curl_cffi)."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from scrapers._common import format_dmY, make_item, paginate_until_recent

PAGE_URL = "https://vinhomes.vn/vi/cong-bo-thong-tin"
IMPERSONATE = "chrome120"


def _parse_date(raw: str) -> str:
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", raw or "")
    if m:
        return format_dmY(m.group(1), m.group(2), m.group(3))
    return ""


def _parse_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()
    for row in soup.select(".views-row .node-teaser-cong-bo-thong-tin"):
        a = row.select_one("a[href]")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        link = a["href"].strip()
        if not title or not link or link in seen:
            continue
        seen.add(link)
        dt_el = row.select_one(".date-create")
        date = _parse_date(dt_el.get_text(strip=True) if dt_el else "")
        items.append(make_item(title, link, date))
    return items


def fetch(source: dict, session) -> list[dict]:
    base_url = source.get("url", PAGE_URL)

    def _page(page: int) -> list[dict]:
        # Drupal views: trang đầu là ?page=0 (URL gốc không trả danh sách)
        page_index = page - 1
        url = f"{base_url.rstrip('/')}?page={page_index}"
        try:
            resp = curl_requests.get(url, impersonate=IMPERSONATE, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print(f"    VHM page {page}: {e}")
            return []
        return _parse_html(resp.text)

    return paginate_until_recent(_page)
