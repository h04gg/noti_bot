"""Scraper: LPBank (LPB) — API findAllInvestor."""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from config import RECENT_DAYS
from filters import parse_item_date, recent_cutoff
from scrapers._common import date_from_iso, make_item

BASE = "https://lpbank.com.vn"
API_URL = f"{BASE}/api/content-service/public/findAllInvestor"
CATEGORY = "CONG_BO_THONG_TIN"


def _extract_link(doc: dict) -> str:
    content = doc.get("content") or ""
    if content:
        soup = BeautifulSoup(content, "html.parser")
        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            if href.startswith("//"):
                return "https:" + href
            if href.startswith("http"):
                return href
            if href.startswith("/"):
                return BASE + href

    doc_id = doc.get("id")
    if doc_id is None:
        return ""
    return f"{BASE}/nha-dau-tu/cong-bo-thong-tin/{doc_id}"


def _doc_date(doc: dict) -> str:
    # Ưu tiên ngày CBTT, tránh dùng updatedDate để không báo lại tin cũ
    for key in ("startDate", "createdDate"):
        raw = doc.get(key)
        if raw:
            date = date_from_iso(str(raw))
            if date:
                return date
    return ""


def fetch(source: dict, session: requests.Session) -> list[dict]:
    page_url = source.get("source_page", f"{BASE}/nha-dau-tu/cong-bo-thong-tin")
    session.headers.setdefault("Origin", BASE)
    session.headers.setdefault("Referer", page_url)
    session.headers.setdefault("Accept", "application/json, text/plain, */*")
    session.headers.setdefault("Content-Type", "application/json")

    items: list[dict] = []
    seen_uids: set[str] = set()
    page = 0
    page_size = 20

    while True:
        try:
            resp = session.post(
                API_URL,
                json={
                    "title": None,
                    "category": CATEGORY,
                    "subCategory": None,
                    "year": "",
                    "otherYear": None,
                    "page": page,
                    "size": page_size,
                    "sortCustoms": [
                        {"sortAsc": False, "nullsFirst": False, "sortField": "updatedDate"},
                        {"sortAsc": False, "nullsFirst": False, "sortField": "startDate"},
                        {"sortAsc": False, "nullsFirst": False, "sortField": "postNow"},
                    ],
                },
                timeout=25,
            )
            resp.raise_for_status()
            data = resp.json().get("data") or {}
        except Exception as e:
            print(f"    LPB API page {page}: {e}")
            break

        docs = data.get("content") or []
        if not docs:
            break

        page_items: list[dict] = []
        for doc in docs:
            title = (doc.get("title") or "").strip()
            link = _extract_link(doc)
            if not title or not link:
                continue
            item = make_item(title, link, _doc_date(doc))
            if item["uid"] in seen_uids:
                continue
            seen_uids.add(item["uid"])
            page_items.append(item)

        items.extend(page_items)

        dates = [parse_item_date(item.get("date", "")) for item in page_items]
        dates = [dt for dt in dates if dt is not None]
        if dates and min(dates) < recent_cutoff(RECENT_DAYS):
            break

        if data.get("last", True):
            break
        page += 1

    return items
