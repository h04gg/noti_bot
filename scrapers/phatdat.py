"""
Scraper: Phát Đạt — AJAX /ajax/reports/filter
Tab Công bố thông tin: https://www.phatdat.com.vn/quan-he-nha-dau-tu#investor-2
"""

from __future__ import annotations

import sys

import requests
from bs4 import BeautifulSoup

from config import RECENT_DAYS
from filters import parse_item_date, recent_cutoff
from scrapers._common import finalize_fetch, make_item

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0

BASE = "https://www.phatdat.com.vn"
API_URL = f"{BASE}/ajax/reports/filter"
SOURCE_PAGE = f"{BASE}/quan-he-nha-dau-tu#investor-2"

# Các sub-tab trong #investor-2 (category_id trên trang)
CATEGORIES = (
    (5, "Thông báo cổ đông"),
    (2, "Báo cáo tài chính"),
    (29, "Báo cáo quản trị"),
    (3, "Báo cáo thường niên"),
    (39, "Bản tin IR"),
    (1, "ĐHĐCĐ"),
    (11, "Điều lệ & Quy chế"),
)


def _abs_link(link: str) -> str:
    link = (link or "").strip()
    if not link:
        return ""
    if link.startswith("http"):
        return link
    return BASE + link if link.startswith("/") else f"{BASE}/{link}"


def _parse_table_items(soup: BeautifulSoup) -> list[dict]:
    items: list[dict] = []
    for a in soup.select("a.recruitment-link"):
        title = a.get_text(" ", strip=True).strip()
        link = _abs_link(a.get("href", ""))
        if not title or not link:
            continue

        date = ""
        date_div = a.find_next("div", class_="date")
        if date_div:
            date = date_div.get_text(strip=True)
        if not date:
            tr = a.find_parent("tr")
            if tr:
                tds = tr.find_all("td")
                if len(tds) >= 3:
                    date = tds[2].get_text(strip=True)

        items.append(make_item(title, link, date))
    return items


def _parse_card_items(soup: BeautifulSoup) -> list[dict]:
    """Báo cáo thường niên, Bản tin IR — layout dạng card."""
    items: list[dict] = []
    for block in soup.select("div.item"):
        title_a = block.select_one("div.title a[href]")
        if not title_a:
            continue
        title = title_a.get_text(" ", strip=True).strip()
        link = _abs_link(title_a.get("href", ""))
        if not title or not link:
            continue

        date_el = block.select_one("div.date")
        date = date_el.get_text(strip=True) if date_el else ""
        items.append(make_item(title, link, date))
    return items


def _parse_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    items = _parse_table_items(soup)
    if not items:
        items = _parse_card_items(soup)
    return items


def _fetch_category(
    session: requests.Session,
    api_url: str,
    category_id: int,
    base_params: dict,
) -> list[dict]:
    items: list[dict] = []
    page = 1

    while page <= 80:
        params = {**base_params, "category_id": category_id, "page": page}
        resp = session.get(api_url, params=params, timeout=25)
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        page_items = _parse_html(data.get("html", ""))
        if not page_items:
            break

        items.extend(page_items)

        dates = [parse_item_date(item.get("date", "")) for item in page_items]
        dates = [dt for dt in dates if dt is not None]
        if dates and min(dates) < recent_cutoff(RECENT_DAYS):
            break

        last_page = int(data.get("lastPage") or page)
        if page >= last_page:
            break
        page += 1

    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    api_url = source.get("url", API_URL)
    page_url = source.get("source_page", SOURCE_PAGE)
    base_params = dict(source.get("params", {}))
    base_params.pop("category_id", None)

    session.headers.setdefault("Referer", page_url.split("#")[0])
    session.headers.setdefault("X-Requested-With", "XMLHttpRequest")

    categories = source.get("categories")
    if categories:
        cat_list = [(int(c["id"]), c.get("name", "")) for c in categories]
    else:
        cat_list = list(CATEGORIES)

    merged: list[dict] = []
    seen_uids: set[str] = set()

    for i, (category_id, label) in enumerate(cat_list):
        try:
            batch = _fetch_category(session, api_url, category_id, base_params)
        except Exception as e:
            print(f"    Phatdat {label or category_id}: {e}")
            if i == 0:
                raise RuntimeError(f"Phatdat {label or category_id}: {e}") from e
            continue

        for item in batch:
            if item["uid"] in seen_uids:
                continue
            seen_uids.add(item["uid"])
            merged.append(item)

    return finalize_fetch(_MOD, merged)
