"""Scraper: DIG (DIC Corp) — HTML CBTT + Báo cáo tài chính."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from config import RECENT_DAYS
from filters import filter_recent_items, newest_item_date, parse_item_date, recent_cutoff
from scrapers._common import make_item

BASE = "https://www.dic.vn"
CBTT_PAGE = f"{BASE}/cong-bo-thong-tin"
BCTC_PAGE = f"{BASE}/bao-cao-tai-chinh"
IMPERSONATE_PROFILES = ("chrome124", "chrome120", "safari17_0", "edge101")
DIC_TIMEOUT = 45
DIC_RETRIES = 3
DIC_RETRY_DELAY = 5
MAX_PAGES = 30
LAST_RAW_COUNT = 0


def _proxy() -> dict[str, str] | None:
    raw = (os.environ.get("DIC_HTTP_PROXY") or os.environ.get("HTTP_PROXY") or "").strip()
    if not raw:
        return None
    return {"http": raw, "https": raw}


def _get_html(url: str, page: int, referer: str, label: str) -> str:
    proxies = _proxy()
    params = {"page": page} if page > 1 else None
    last_error: Exception | None = None

    for attempt in range(1, DIC_RETRIES + 1):
        profile = IMPERSONATE_PROFILES[(attempt - 1) % len(IMPERSONATE_PROFILES)]
        session = curl_requests.Session(impersonate=profile)
        try:
            resp = session.get(
                url,
                params=params,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Referer": referer,
                },
                timeout=DIC_TIMEOUT,
                proxies=proxies,
            )
            if resp.status_code == 403:
                raise RuntimeError("HTTP 403 Forbidden")
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            last_error = e
            if attempt < DIC_RETRIES:
                print(
                    f"    DIC {profile} {label} page {page}: lỗi lần {attempt}/{DIC_RETRIES}: {e}"
                    f" — thử lại sau {DIC_RETRY_DELAY}s"
                )
                time.sleep(DIC_RETRY_DELAY)
        finally:
            session.close()

    raise RuntimeError(f"DIC {label} page {page}: {last_error}") from last_error


def _extract_date(anchor) -> str:
    intro = anchor.find_parent(class_="intro")
    if not intro:
        return ""
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", intro.get_text(" ", strip=True))
    if not m:
        return ""
    return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"


def _parse_page(html: str, path_key: str, year: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for a in soup.select("div.item a.title"):
        href = (a.get("href") or "").strip()
        if path_key not in href:
            continue

        title = a.get_text(" ", strip=True).strip()
        if not title:
            continue

        link = href if href.startswith("http") else f"{BASE}/{href.lstrip('/')}"
        if link in seen:
            continue
        seen.add(link)

        date = _extract_date(a)
        dt = parse_item_date(date)
        if dt is None or dt.year != year:
            continue

        items.append(make_item(title, link, date))

    return items


def _fetch_section(
    page_url: str, path_key: str, referer: str, label: str, year: int
) -> list[dict]:
    all_items: list[dict] = []

    for page in range(1, MAX_PAGES + 1):
        try:
            html = _get_html(page_url, page, referer, label)
        except RuntimeError as e:
            print(f"    {e}")
            if page == 1:
                raise
            break

        page_items = _parse_page(html, path_key, year)
        if not page_items:
            break

        all_items.extend(page_items)

        page_newest = newest_item_date(page_items)
        if page_newest and page_newest < recent_cutoff(RECENT_DAYS):
            break

        dates = [parse_item_date(item.get("date", "")) for item in page_items]
        dates = [dt for dt in dates if dt is not None]
        if dates and min(dates).year < year:
            break

    return all_items


def fetch(source: dict, session) -> list[dict]:
    global LAST_RAW_COUNT

    year = datetime.now().year
    cbtt_page = source.get("url", CBTT_PAGE)
    bctc_page = source.get("bctc_page", BCTC_PAGE)

    merged: list[dict] = []
    seen: set[str] = set()

    cbtt_items = _fetch_section(
        cbtt_page, "cong-bo-thong-tin/", cbtt_page, "CBTT", year
    )
    for item in cbtt_items:
        if item["uid"] not in seen:
            seen.add(item["uid"])
            merged.append(item)

    try:
        bctc_items = _fetch_section(
            bctc_page, "bao-cao-tai-chinh/", bctc_page, "BCTC", year
        )
    except RuntimeError as e:
        print(f"    {e} — bỏ qua BCTC lần này")
        bctc_items = []

    for item in bctc_items:
        if item["uid"] not in seen:
            seen.add(item["uid"])
            merged.append(item)

    LAST_RAW_COUNT = len(merged)
    return filter_recent_items(merged)
