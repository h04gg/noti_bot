"""Scraper: BVSC (Bảo Việt Securities) — CBTT API + BCTC HTML."""

from __future__ import annotations

import os
import time
from datetime import datetime

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from config import RECENT_DAYS
from filters import filter_recent_items, newest_item_date, recent_cutoff
from scrapers._common import make_item

BASE = "https://www.bvsc.com.vn"
API_URL = f"{BASE}/getPaginateCBTT_V2"
CBTT_PAGE = f"{BASE}/danhmuc/quan-he-nha-dau-tu/cong-bo-thong-tin/"
BCTC_PAGE = f"{BASE}/danhmuc/quan-he-nha-dau-tu/bao-cao-tai-chinh/"
IMPERSONATE_PROFILES = ("chrome124", "chrome120", "safari17_0", "edge101")
BVSC_TIMEOUT = 30
BVSC_RETRIES = 3
BVSC_RETRY_DELAY = 3


def _proxy() -> dict[str, str] | None:
    """Proxy VN/residential tùy chọn — set BVSC_HTTP_PROXY hoặc HTTP_PROXY trên GHA."""
    raw = (os.environ.get("BVSC_HTTP_PROXY") or os.environ.get("HTTP_PROXY") or "").strip()
    if not raw:
        return None
    return {"http": raw, "https": raw}


def _api_headers(source_page: str) -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        "Referer": source_page,
        "X-Requested-With": "XMLHttpRequest",
    }


def _html_headers(source_page: str) -> dict[str, str]:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        "Referer": source_page,
    }


def _with_retry(label: str, page: int, action):
    proxies = _proxy()
    last_error: Exception | None = None

    for attempt in range(1, BVSC_RETRIES + 1):
        profile = IMPERSONATE_PROFILES[(attempt - 1) % len(IMPERSONATE_PROFILES)]
        session = curl_requests.Session(impersonate=profile)
        try:
            return action(session, proxies)
        except Exception as e:
            last_error = e
            if attempt < BVSC_RETRIES:
                print(
                    f"    BVSC {profile} {label} page {page}:"
                    f" lỗi lần {attempt}/{BVSC_RETRIES}: {e}"
                    f" — thử lại sau {BVSC_RETRY_DELAY}s"
                )
                time.sleep(BVSC_RETRY_DELAY)
        finally:
            session.close()

    raise RuntimeError(f"BVSC {label} page {page}: {last_error}") from last_error


def _get_api_data(api_url: str, params: dict, page: int, source_page: str) -> dict:
    def _action(session: curl_requests.Session, proxies: dict[str, str] | None) -> dict:
        session.get(source_page, timeout=BVSC_TIMEOUT, proxies=proxies)
        resp = session.get(
            api_url,
            params=params,
            headers=_api_headers(source_page),
            timeout=BVSC_TIMEOUT,
            proxies=proxies,
        )
        if resp.status_code == 403:
            raise RuntimeError("HTTP 403 Forbidden")
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            msg = data.get("message") or data.get("error") or "success=false"
            raise RuntimeError(f"API {msg}")
        return data

    return _with_retry("CBTT", page, _action)


def _get_html(source_page: str) -> str:
    def _action(session: curl_requests.Session, proxies: dict[str, str] | None) -> str:
        resp = session.get(
            source_page,
            headers=_html_headers(source_page),
            timeout=BVSC_TIMEOUT,
            proxies=proxies,
        )
        if resp.status_code == 403:
            raise RuntimeError("HTTP 403 Forbidden")
        resp.raise_for_status()
        return resp.text

    return _with_retry("BCTC", 1, _action)


def fetch(source: dict, session) -> list[dict]:
    seen: set[str] = set()
    merged: list[dict] = []

    for item in _fetch_cbtt(source) + _fetch_bctc(source):
        if item["uid"] in seen:
            continue
        seen.add(item["uid"])
        merged.append(item)

    return filter_recent_items(merged)


def _fetch_cbtt(source: dict) -> list[dict]:
    api_url = source.get("api_url", API_URL)
    source_page = source.get("source_page", CBTT_PAGE)

    params = dict(source.get("params", {}))
    current_page = int(params.pop("currentPage", 1))
    params.setdefault("language", "vi")
    params["year"] = datetime.now().year

    all_items: list[dict] = []
    while True:
        params["currentPage"] = current_page
        page_items, total_pages = _fetch_cbtt_page(api_url, params, source_page)
        all_items.extend(page_items)

        if not page_items or current_page >= total_pages:
            break

        page_newest = newest_item_date(page_items)
        if page_newest and page_newest < recent_cutoff(RECENT_DAYS):
            break

        current_page += 1

    return all_items


def _fetch_cbtt_page(
    api_url: str, params: dict, source_page: str
) -> tuple[list[dict], int]:
    page = int(params.get("currentPage", 1))
    try:
        data = _get_api_data(api_url, params, page, source_page)
    except RuntimeError as e:
        print(f"    {e}")
        if page == 1:
            raise
        return [], 0

    blocks = data.get("data") or []
    if not blocks:
        return [], 0

    block = blocks[0]
    total_pages = int(block.get("totalPage", 1))
    items: list[dict] = []

    for doc in block.get("list") or []:
        title = (doc.get("tieu_de") or "").strip()
        link = (doc.get("link") or "").strip()
        if not title or not link:
            continue
        if not link.startswith("http"):
            link = BASE + link

        date = (doc.get("ngay") or "").strip()
        items.append(make_item(title, link, date))

    return items, total_pages


def _fetch_bctc(source: dict) -> list[dict]:
    bctc_page = source.get("bctc_page", BCTC_PAGE)
    year = str(datetime.now().year)
    try:
        html = _get_html(bctc_page)
    except RuntimeError as e:
        print(f"    {e}")
        raise

    return _parse_bctc_html(html, year)


def _parse_bctc_html(html: str, year: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []

    for child in soup.select(".news__nhadautu--list > .news__nhadautu--child"):
        heading = child.select_one(".news__nhadautu--heading h3")
        if not heading or heading.get_text(strip=True) != year:
            continue

        for detail in child.select(".news__nhadautu--detail"):
            title_el = detail.select_one("a.news__nhadautu__detail--title")
            link_el = detail.select_one('a[href*="danhsachbaiviet"]')
            date_el = detail.select_one("label[ngayhienthi]")
            title = title_el.get_text(" ", strip=True) if title_el else ""
            link = link_el["href"].strip() if link_el and link_el.get("href") else ""
            if not title or not link:
                continue
            if not link.startswith("http"):
                link = BASE + link
            date = date_el.get_text(strip=True) if date_el else ""
            items.append(make_item(title, link, date))

    return items
