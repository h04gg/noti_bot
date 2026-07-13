"""Scraper: VIX Securities — HTML Công bố thông tin + Báo cáo tài chính."""

from __future__ import annotations

import os
import re
import sys
import time

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from config import RECENT_DAYS
from filters import parse_item_date, recent_cutoff
from scrapers._common import (
    IMPERSONATE_PROFILES,
    extract_dmY,
    finalize_fetch,
    make_item,
    page_fetch_failed,
)

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0
BASE = "https://vixs.vn"
HOME_URL = f"{BASE}/"
PAGE_PATH = "/qhcd/cong-bo-thong-tin"
BCTC_PATH = "/bao-cao"
DEFAULT_PARAMS = {"num": 20, "y": -1}
VIX_TIMEOUT = 60
VIX_RETRIES = 4
VIX_RETRY_DELAY = 5
_FILENAME_DATE_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})")


def _proxy() -> dict[str, str] | None:
    raw = (os.environ.get("VIX_HTTP_PROXY") or os.environ.get("HTTP_PROXY") or "").strip()
    if not raw:
        return None
    return {"http": raw, "https": raw}


def _is_blocked(status_code: int, html: str) -> bool:
    if status_code == 403:
        return True
    low = (html or "").lower()
    return "just a moment" in low or "challenge-platform" in low or "access denied" in low


def _page_url(base_path: str, params: dict, page: int) -> str:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    if page <= 1:
        return f"{BASE}{base_path}?{query}"
    return f"{BASE}{base_path}/page/{page}?{query}"


def _curl_get(url: str, referer: str, label: str) -> str:
    proxies = _proxy()
    last_error: Exception | None = None

    for attempt in range(1, VIX_RETRIES + 1):
        profile = IMPERSONATE_PROFILES[(attempt - 1) % len(IMPERSONATE_PROFILES)]
        session = curl_requests.Session(impersonate=profile)
        try:
            session.get(
                HOME_URL,
                headers={"Accept-Language": "vi-VN,vi;q=0.9"},
                timeout=VIX_TIMEOUT,
                proxies=proxies,
            )
            resp = session.get(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Referer": referer,
                },
                timeout=VIX_TIMEOUT,
                proxies=proxies,
            )
            if _is_blocked(resp.status_code, resp.text):
                raise RuntimeError("HTTP 403 Forbidden / Cloudflare")
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            last_error = e
            if attempt < VIX_RETRIES:
                print(
                    f"    VIX {profile} {label}: lỗi lần {attempt}/{VIX_RETRIES}: {e}"
                    f" — thử lại sau {VIX_RETRY_DELAY}s"
                )
                time.sleep(VIX_RETRY_DELAY)
        finally:
            session.close()

    raise RuntimeError(f"VIX {label}: {last_error}") from last_error


def _parse_cbtt_html(html: str) -> list[dict]:
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


def _date_from_pdf(link: str, context: str) -> str:
    date = extract_dmY(context)
    if date:
        return date
    m = _FILENAME_DATE_RE.search(os.path.basename(link))
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    return ""


def _parse_bctc_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for a in soup.select('a[href*=".pdf"]'):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        link = href if href.startswith("http") else BASE + href
        if link in seen:
            continue
        seen.add(link)

        title = a.get_text(" ", strip=True) or os.path.basename(link)
        if title.lower() in {"pdf", "tải về", "download"}:
            row = a.find_parent("tr")
            if row:
                cells = [c.get_text(" ", strip=True) for c in row.select("td, th")]
                title = next((c for c in cells if len(c) > 8 and "pdf" not in c.lower()), title)
        parent = a.find_parent("td")
        date = _date_from_pdf(link, parent.get_text(" ", strip=True) if parent else "")
        items.append(make_item(title, link, date))

    return items


def _fetch_cbtt(source: dict) -> list[dict]:
    path = source.get("path", PAGE_PATH)
    params = dict(source.get("params", DEFAULT_PARAMS))
    referer = source.get("source_page", f"{BASE}{path}")
    all_items: list[dict] = []

    for page in range(1, 21):
        url = _page_url(path, params, page)
        try:
            html = _curl_get(url, referer, f"CBTT page {page}")
        except RuntimeError as e:
            page_fetch_failed(page, e, "VIX CBTT")

        if page == 1 and ".bic-report__title" not in html and "tbody" not in html:
            page_fetch_failed(page, RuntimeError("HTML không hợp lệ (có thể bị chặn)"), "VIX CBTT")

        page_items = _parse_cbtt_html(html)
        if not page_items:
            break
        all_items.extend(page_items)
        dates = [parse_item_date(item.get("date", "")) for item in page_items]
        dates = [dt for dt in dates if dt is not None]
        if dates and min(dates) < recent_cutoff(RECENT_DAYS):
            break

    return all_items


def _fetch_bctc(bctc_path: str) -> list[dict]:
    url = f"{BASE}{bctc_path}"
    referer = f"{BASE}{bctc_path}"
    try:
        html = _curl_get(url, referer, "BCTC")
    except RuntimeError as e:
        print(f"    VIX BCTC: {e}")
        raise RuntimeError(f"VIX BCTC: {e}") from e
    return _parse_bctc_html(html)


def fetch(source: dict, session) -> list[dict]:
    bctc_path = source.get("bctc_path", BCTC_PATH)

    cbtt_items = _fetch_cbtt(source)
    try:
        bctc_items = _fetch_bctc(bctc_path)
    except RuntimeError:
        if not cbtt_items:
            raise
        bctc_items = []

    merged: list[dict] = []
    seen_uids: set[str] = set()
    for item in cbtt_items + bctc_items:
        if item["uid"] in seen_uids:
            continue
        seen_uids.add(item["uid"])
        merged.append(item)

    print(f"    VIX CBTT: {len(cbtt_items)}, BCTC: {len(bctc_items)}")
    return finalize_fetch(_MOD, merged)
