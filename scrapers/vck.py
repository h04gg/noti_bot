"""Scraper: VPS Securities (VCK) — Next.js RSC (các tab Quan hệ cổ đông)."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime

from curl_cffi import requests as curl_requests

from config import RECENT_DAYS
from filters import filter_recent_items, newest_item_date, recent_cutoff
from scrapers._common import date_from_iso, finalize_fetch, make_item

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0

BASE = "https://www.vps.com.vn"
QHCD_BASE = f"{BASE}/quan-he-co-dong"

# Các tab trên https://www.vps.com.vn/quan-he-co-dong/
SECTIONS = (
    ("cong-bo-thong-tin", "CBTT"),
    ("bao-cao-cong-ty", "Báo cáo công ty"),
    ("dai-hoi-dong-co-dong", "ĐHĐCĐ"),
    ("ho-so-doanh-nghiep", "Hồ sơ DN"),
)

IMPERSONATE_PROFILES = ("chrome124", "chrome120", "safari17_0", "edge101")
VCK_TIMEOUT = 90
VCK_RETRIES = 4
VCK_RETRY_DELAY = 8

_POST_RE = re.compile(
    r'"publishedAt":"([^"]+)".*?"contents":\[\{"title":"((?:\\.|[^"\\])*)","slug":"([^"]+)"',
    re.S,
)
_TOTAL_RE = re.compile(r'"total":(\d+)')
_PAGE_SIZE_RE = re.compile(r'"pageSize":(\d+)')


def _proxy() -> dict[str, str] | None:
    raw = (os.environ.get("VCK_HTTP_PROXY") or os.environ.get("HTTP_PROXY") or "").strip()
    if not raw:
        return None
    return {"http": raw, "https": raw}


def _router_state_tree(segment: str) -> str:
    return (
        "%5B%22%22%2C%7B%22children%22%3A%5B%22(landing)%22%2C%7B%22children%22%3A%5B%22(pages)%22%2C%7B"
        f"%22children%22%3A%5B%22quan-he-co-dong%22%2C%7B%22children%22%3A%5B%22{segment}%22%2C%7B"
        "%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D"
        "%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
    )


def _rsc_headers(page_path: str) -> dict[str, str]:
    return {
        "Accept": "*/*",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "RSC": "1",
        "Next-Url": page_path,
        "Next-Router-State-Tree": _router_state_tree(page_path.rsplit("/", 1)[-1]),
        "Referer": f"{BASE}{page_path}",
    }


def _get_rsc_text(page_path: str, year: int, page: int, label: str) -> str:
    proxies = _proxy()
    params = {"year": year, "page": page}
    last_error: Exception | None = None

    for attempt in range(1, VCK_RETRIES + 1):
        profile = IMPERSONATE_PROFILES[(attempt - 1) % len(IMPERSONATE_PROFILES)]
        session = curl_requests.Session(impersonate=profile)
        try:
            session.get(
                f"{BASE}/quan-he-co-dong",
                timeout=VCK_TIMEOUT,
                proxies=proxies,
                headers={"Accept-Language": "vi-VN,vi;q=0.9"},
            )
            resp = session.get(
                f"{BASE}{page_path}",
                params=params,
                headers=_rsc_headers(page_path),
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
                    f"    VCK {label} {profile} page {page}: lỗi lần {attempt}/{VCK_RETRIES}: {e}"
                    f" — thử lại sau {VCK_RETRY_DELAY}s"
                )
                time.sleep(VCK_RETRY_DELAY)
        finally:
            session.close()

    raise RuntimeError(f"VCK {label} page {page}: {last_error}") from last_error


def _parse_rsc_page(text: str) -> tuple[list[dict], int]:
    items: list[dict] = []
    seen: set[str] = set()

    for match in _POST_RE.finditer(text):
        date = date_from_iso(match.group(1))
        try:
            title = json.loads(f'"{match.group(2)}"')
        except json.JSONDecodeError:
            title = match.group(2)
        slug = match.group(3).strip()
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


def _fetch_section(segment: str, label: str, year: int) -> list[dict]:
    page_path = f"/quan-he-co-dong/{segment}"
    all_items: list[dict] = []
    page = 1
    total_pages = 1

    while page <= total_pages:
        try:
            text = _get_rsc_text(page_path, year, page, label)
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

    return all_items


def fetch(source: dict, session) -> list[dict]:
    year = datetime.now().year
    sections = source.get("sections")
    if sections:
        section_list = [(s["path"], s.get("label", s["path"])) for s in sections]
    else:
        section_list = list(SECTIONS)

    merged: list[dict] = []
    seen_uids: set[str] = set()
    counts: list[str] = []

    for segment, label in section_list:
        try:
            batch = _fetch_section(segment, label, year)
        except RuntimeError as e:
            if segment == section_list[0][0]:
                raise
            print(f"    VCK {label}: {e}")
            continue
        counts.append(f"{label}: {len(batch)}")
        for item in batch:
            if item["uid"] in seen_uids:
                continue
            seen_uids.add(item["uid"])
            merged.append(item)

    if counts:
        print(f"    VCK {', '.join(counts)} (năm {year})")
    return finalize_fetch(_MOD, merged)
