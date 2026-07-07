"""Scraper: VIX Securities — HTML Công bố thông tin + Báo cáo tài chính."""

from __future__ import annotations

import os
import re
import sys

import requests
from bs4 import BeautifulSoup

from config import RECENT_DAYS
from filters import parse_item_date, recent_cutoff
from scrapers._common import extract_dmY, finalize_fetch, make_item, page_fetch_failed

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0
BASE = "https://vixs.vn"
PAGE_PATH = "/qhcd/cong-bo-thong-tin"
BCTC_PATH = "/bao-cao"
DEFAULT_PARAMS = {"num": 20, "y": -1}
_FILENAME_DATE_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})")


def _page_url(base_path: str, params: dict, page: int) -> str:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    if page <= 1:
        return f"{BASE}{base_path}?{query}"
    return f"{BASE}{base_path}/page/{page}?{query}"


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


def _fetch_cbtt(source: dict, session: requests.Session) -> list[dict]:
    path = source.get("path", PAGE_PATH)
    params = dict(source.get("params", DEFAULT_PARAMS))
    all_items: list[dict] = []

    for page in range(1, 21):
        url = _page_url(path, params, page)
        try:
            resp = session.get(url, timeout=25)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
        except Exception as e:
            page_fetch_failed(page, e, "VIX CBTT")
        page_items = _parse_cbtt_html(resp.text)
        if not page_items:
            break
        all_items.extend(page_items)
        dates = [parse_item_date(item.get("date", "")) for item in page_items]
        dates = [dt for dt in dates if dt is not None]
        if dates and min(dates) < recent_cutoff(RECENT_DAYS):
            break

    return all_items


def _fetch_bctc(session: requests.Session, bctc_path: str) -> list[dict]:
    url = f"{BASE}{bctc_path}"
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
    except Exception as e:
        print(f"    VIX BCTC: {e}")
        raise RuntimeError(f"VIX BCTC: {e}") from e
    return _parse_bctc_html(resp.text)


def fetch(source: dict, session: requests.Session) -> list[dict]:
    bctc_path = source.get("bctc_path", BCTC_PATH)

    cbtt_items = _fetch_cbtt(source, session)
    try:
        bctc_items = _fetch_bctc(session, bctc_path)
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
