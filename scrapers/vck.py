"""Scraper: VPS Securities (VCK) — Next.js RSC flight data."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime

from curl_cffi import requests as curl_requests

from config import RECENT_DAYS
from filters import filter_recent_items, newest_item_date, recent_cutoff
from scrapers._common import date_from_iso, make_item

BASE = "https://www.vps.com.vn"
PAGE_PATH = "/quan-he-co-dong/cong-bo-thong-tin"
PAGE_URL = f"{BASE}{PAGE_PATH}"
# State tree cố định cho route cong-bo-thong-tin (__PAGE__)
ROUTER_STATE_TREE = (
    "%5B%22%22%2C%7B%22children%22%3A%5B%22(landing)%22%2C%7B%22children%22%3A%5B%22(pages)%22%2C%7B"
    "%22children%22%3A%5B%22quan-he-co-dong%22%2C%7B%22children%22%3A%5B%22cong-bo-thong-tin%22%2C%7B"
    "%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D"
    "%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
)
IMPERSONATE_PROFILES = ("chrome124", "chrome120", "safari17_0", "edge101")
VCK_TIMEOUT = 45
VCK_RETRIES = 3
VCK_RETRY_DELAY = 5

_POST_RE = re.compile(
    r'"publishedAt":"([^"]+)".*?"contents":\[\{"title":"((?:\\.|[^"\\])*)","slug":"([^"]+)"',
    re.S,
)
_TOTAL_RE = re.compile(r'"total":(\d+)')
_PAGE_SIZE_RE = re.compile(r'"pageSize":(\d+)')
LAST_RAW_COUNT = 0


def _proxy() -> dict[str, str] | None:
    raw = (os.environ.get("VCK_HTTP_PROXY") or os.environ.get("HTTP_PROXY") or "").strip()
    if not raw:
        return None
    return {"http": raw, "https": raw}


def _rsc_headers() -> dict[str, str]:
    return {
        "Accept": "*/*",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "RSC": "1",
        "Next-Url": PAGE_PATH,
        "Next-Router-State-Tree": ROUTER_STATE_TREE,
        "Referer": PAGE_URL,
    }


def _get_rsc_text(year: int, page: int) -> str:
    proxies = _proxy()
    params = {"year": year, "page": page}
    last_error: Exception | None = None

    for attempt in range(1, VCK_RETRIES + 1):
        profile = IMPERSONATE_PROFILES[(attempt - 1) % len(IMPERSONATE_PROFILES)]
        session = curl_requests.Session(impersonate=profile)
        try:
            resp = session.get(
                PAGE_URL,
                params=params,
                headers=_rsc_headers(),
                timeout=VCK_TIMEOUT,
                proxies=proxies,
            )
            if resp.status_code == 403:
                raise RuntimeError("HTTP 403 Forbidden")
            resp.raise_for_status()
            if "publishedAt" not in resp.text and "mainDataPost" not in resp.text:
                raise RuntimeError("RSC payload không hợp lệ")
            return resp.text
        except Exception as e:
            last_error = e
            if attempt < VCK_RETRIES:
                print(
                    f"    VCK {profile} page {page}: lỗi lần {attempt}/{VCK_RETRIES}: {e}"
                    f" — thử lại sau {VCK_RETRY_DELAY}s"
                )
                time.sleep(VCK_RETRY_DELAY)
        finally:
            session.close()

    raise RuntimeError(f"VCK page {page}: {last_error}") from last_error


def _parse_rsc_page(text: str) -> tuple[list[dict], int]:
    items: list[dict] = []
    seen: set[str] = set()

    for m in _POST_RE.finditer(text):
        date = date_from_iso(m.group(1))
        try:
            title = json.loads(f'"{m.group(2)}"')
        except json.JSONDecodeError:
            title = m.group(2)
        slug = m.group(3).strip()
        if not slug or not slug.startswith("vps-"):
            continue
        link = f"{BASE}/bai-viet/{slug}"
        if link in seen:
            continue
        seen.add(link)
        items.append(make_item(title, link, date))

    total_m = _TOTAL_RE.search(text)
    size_m = _PAGE_SIZE_RE.search(text)
    total = int(total_m.group(1)) if total_m else len(items)
    page_size = int(size_m.group(1)) if size_m else max(len(items), 1)
    total_pages = max(1, (total + page_size - 1) // page_size)

    return items, total_pages


def fetch(source: dict, session) -> list[dict]:
    global LAST_RAW_COUNT
    year = datetime.now().year
    all_items: list[dict] = []
    page = 1
    total_pages = 1

    while page <= total_pages:
        try:
            text = _get_rsc_text(year, page)
        except RuntimeError as e:
            print(f"    {e}")
            if page == 1:
                raise
            break

        page_items, total_pages = _parse_rsc_page(text)
        if not page_items:
            break

        all_items.extend(page_items)

        page_newest = newest_item_date(page_items)
        if page_newest and page_newest < recent_cutoff(RECENT_DAYS):
            break

        page += 1

    LAST_RAW_COUNT = len(all_items)
    return filter_recent_items(all_items)
