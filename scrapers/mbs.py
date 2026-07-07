"""Scraper: MB Securities (MBS) — HTML CBTT + Báo cáo tài chính (Cloudflare → curl_cffi)."""

from __future__ import annotations

import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from filters import filter_recent_items, newest_item_date, parse_item_date, recent_cutoff
from scrapers._common import (
    ScraperBlockedError,
    extract_dmY,
    make_item,
)

BASE = "https://www.mbs.com.vn"
CBTT_PAGE = f"{BASE}/cong-bo-thong-tin/"
BCTC_PAGE = f"{BASE}/bao-cao-tai-chinh/"
IMPERSONATE_PROFILES = ("chrome124", "chrome120", "safari17_0")
FETCH_RETRIES = 3
RETRY_DELAY = 3
MAX_PAGES = 20
LAST_RAW_COUNT = 0


def _page_url(base: str, page: int) -> str:
    if page <= 1:
        return base
    return f"{base.rstrip('/')}/page/{page}/"


def _is_blocked(status_code: int, html: str) -> bool:
    if status_code == 403:
        return True
    low = (html or "").lower()
    return "just a moment" in low or "challenge-platform" in low


def _fetch_page(url: str, label: str, page: int) -> str:
    last_error: Exception | None = None
    for attempt in range(1, FETCH_RETRIES + 1):
        profile = IMPERSONATE_PROFILES[(attempt - 1) % len(IMPERSONATE_PROFILES)]
        try:
            resp = curl_requests.get(
                url,
                impersonate=profile,
                timeout=30,
                headers={"Accept-Language": "vi-VN,vi;q=0.9"},
            )
            if _is_blocked(resp.status_code, resp.text):
                raise ScraperBlockedError(f"HTTP {resp.status_code} (Cloudflare chặn)")
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            last_error = e
            if attempt < FETCH_RETRIES:
                print(
                    f"    MBS {profile} {label} page {page}: lỗi lần {attempt}/{FETCH_RETRIES}: {e}"
                    f" — thử lại sau {RETRY_DELAY}s"
                )
                time.sleep(RETRY_DELAY)
    raise ScraperBlockedError(str(last_error) if last_error else f"MBS {label} fetch thất bại")


def _parse_html(html: str, year: int) -> list[dict]:
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
        dt = parse_item_date(date)
        if dt is None or dt.year != year:
            continue

        items.append(make_item(title, link, date))

    return items


def _fetch_section(base_url: str, label: str, year: int) -> list[dict]:
    all_items: list[dict] = []

    for page in range(1, MAX_PAGES + 1):
        url = _page_url(base_url, page)
        try:
            html = _fetch_page(url, label, page)
        except ScraperBlockedError as e:
            print(f"    MBS {label} page {page}: {e}")
            if page == 1:
                raise
            break
        except Exception as e:
            print(f"    MBS {label} page {page}: {e}")
            if page == 1:
                raise RuntimeError(str(e)) from e
            break

        page_items = _parse_html(html, year)
        if not page_items:
            break

        all_items.extend(page_items)

        page_newest = newest_item_date(page_items)
        if page_newest and page_newest < recent_cutoff():
            break

        dates = [parse_item_date(item.get("date", "")) for item in page_items]
        dates = [dt for dt in dates if dt is not None]
        if dates and min(dates).year < year:
            break

    return all_items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    global LAST_RAW_COUNT

    year = datetime.now().year
    cbtt_page = source.get("url", CBTT_PAGE)
    bctc_page = source.get("bctc_page", BCTC_PAGE)

    merged: list[dict] = []
    seen: set[str] = set()

    cbtt_items = _fetch_section(cbtt_page, "CBTT", year)
    for item in cbtt_items:
        if item["uid"] not in seen:
            seen.add(item["uid"])
            merged.append(item)

    try:
        bctc_items = _fetch_section(bctc_page, "BCTC", year)
    except (ScraperBlockedError, RuntimeError) as e:
        print(f"    {e} — bỏ qua BCTC lần này")
        bctc_items = []

    for item in bctc_items:
        if item["uid"] not in seen:
            seen.add(item["uid"])
            merged.append(item)

    LAST_RAW_COUNT = len(merged)
    return filter_recent_items(merged)
