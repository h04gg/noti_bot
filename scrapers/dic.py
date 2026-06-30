"""
Scraper: DIG (DIC Corp) — HTML trang Công bố thông tin
URL: https://www.dic.vn/cong-bo-thong-tin
"""

from __future__ import annotations

import re
import hashlib
import requests
from bs4 import BeautifulSoup

from config import RECENT_DAYS
from filters import is_recent_item, newest_item_date, recent_cutoff

BASE = "https://www.dic.vn"
MAX_PAGES = 20


def fetch(source: dict, session: requests.Session) -> list[dict]:
    base_url = source.get("url", f"{BASE}/cong-bo-thong-tin")
    all_items: list[dict] = []

    for page in range(1, MAX_PAGES + 1):
        page_items = _fetch_page(session, base_url, page)
        if not page_items:
            break

        all_items.extend(item for item in page_items if is_recent_item(item))

        page_newest = newest_item_date(page_items)
        if page_newest and page_newest < recent_cutoff(RECENT_DAYS):
            break

    return all_items


def _fetch_page(session: requests.Session, base_url: str, page: int) -> list[dict]:
    params = {"page": page} if page > 1 else None
    try:
        resp = session.get(base_url, params=params, timeout=20)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
    except Exception as e:
        print(f"    DIC page {page}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    items: list[dict] = []
    seen_links: set[str] = set()

    for a in soup.select("div.item a.title[href*='cong-bo-thong-tin/']"):
        title = a.get_text(" ", strip=True).strip()
        href = a.get("href", "").strip()
        if not title or not href:
            continue

        link = href if href.startswith("http") else f"{BASE}/{href.lstrip('/')}"
        if link in seen_links:
            continue
        seen_links.add(link)

        date = _extract_date(a)
        uid = hashlib.md5(link.encode()).hexdigest()[:12]
        items.append({"uid": uid, "title": title, "link": link, "date": date})

    return items


def _extract_date(anchor) -> str:
    intro = anchor.find_parent(class_="intro")
    if not intro:
        return ""
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", intro.get_text(" ", strip=True))
    if not m:
        return ""
    parts = m.group(1).split("/")
    return f"{int(parts[0]):02d}/{int(parts[1]):02d}/{parts[2]}"
