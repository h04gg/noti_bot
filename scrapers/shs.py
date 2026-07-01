"""Scraper: SHS (Saigon–Hanoi Securities) — API info-disclosure."""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from config import RECENT_DAYS
from filters import parse_item_date, recent_cutoff
from scrapers._common import date_from_iso, make_item

BASE = "https://www.shs.com.vn"
API_URL = f"{BASE}/api/shareholders/info-disclosure"
DISCLOSURE_CODES = ("DINHKY", "BATTHUONG", "KHAC")
_PDF_RE = re.compile(r'https?://[^\s"\'<>]+\.pdf', re.I)


def _doc_link(doc: dict) -> str:
    preview = (doc.get("PreviewUrl") or "").strip()
    if preview:
        return preview

    summary = doc.get("Summary") or ""
    if summary:
        soup = BeautifulSoup(summary, "html.parser")
        for a in soup.select('a[href*=".pdf"]'):
            return a["href"].strip()
        for a in soup.select("a[href]"):
            href = a["href"].strip()
            if href.startswith("http"):
                return href
        m = _PDF_RE.search(summary)
        if m:
            return m.group(0)

    slug = (doc.get("Slug") or "").strip()
    if slug:
        return f"{BASE}/cong-bo-thong-tin/{slug}"
    return ""


def _doc_date(doc: dict) -> str:
    # PublishedDate = ngày CBTT thực tế; publishedAt có thể cập nhật lại sau
    for key in ("PublishedDate", "createdAt", "publishedAt"):
        raw = doc.get(key)
        if raw:
            date = date_from_iso(str(raw))
            if date:
                return date
    return ""


def _fetch_code(
    session: requests.Session,
    api_url: str,
    code: str,
    page_size: int,
) -> list[dict]:
    items: list[dict] = []
    page = 1

    while True:
        try:
            resp = session.get(
                api_url,
                params={"code": code, "page": page, "pageSize": page_size},
                timeout=25,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            print(f"    SHS {code} page {page}: {e}")
            break

        docs = payload.get("data") or []
        if not docs:
            break

        page_items: list[dict] = []
        for doc in docs:
            title = (doc.get("Title") or "").strip()
            link = _doc_link(doc)
            if not title or not link:
                continue
            page_items.append(make_item(title, link, _doc_date(doc)))

        items.extend(page_items)

        pagination = (payload.get("meta") or {}).get("pagination") or {}
        total_pages = int(pagination.get("pageCount") or 1)
        if page >= total_pages:
            break

        dates = [parse_item_date(item.get("date", "")) for item in page_items]
        dates = [dt for dt in dates if dt is not None]
        if dates and min(dates) < recent_cutoff(RECENT_DAYS):
            break

        page += 1

    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    api_url = source.get("api_url", API_URL)
    codes = source.get("codes", DISCLOSURE_CODES)
    page_size = int(source.get("params", {}).get("pageSize", 10))

    session.headers.setdefault("Referer", source.get("source_page", f"{BASE}/cong-bo-thong-tin"))
    session.headers.setdefault("Origin", BASE)

    seen: set[str] = set()
    all_items: list[dict] = []
    for code in codes:
        for item in _fetch_code(session, api_url, code, page_size):
            if item["uid"] in seen:
                continue
            seen.add(item["uid"])
            all_items.append(item)

    return all_items
