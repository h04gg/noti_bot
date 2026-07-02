"""Scraper: Sacombank (STB) — AEM JSON shareholdernotice."""

from __future__ import annotations

from datetime import datetime

import requests

from scrapers._common import date_from_iso, make_item

BASE = "https://www.sacombank.com.vn"
API_URL = (
    f"{BASE}/trang-chu/nha-dau-tu/cong-bo-thong-tin/_jcr_content/root/container/"
    "container/shareholdernotice.sacom.shnotice.json"
)
PAGE_URL = f"{BASE}/trang-chu/nha-dau-tu/cong-bo-thong-tin.html"


def _abs_link(path: str) -> str:
    path = (path or "").strip()
    if not path:
        return ""
    if path.startswith("http"):
        return path
    return BASE + path


def _doc_date(doc: dict) -> str:
    date = (doc.get("dateFormat") or "").strip()
    if date:
        return date
    return date_from_iso(doc.get("date") or "")


def _iter_docs(docs: list[dict]):
    for doc in docs:
        yield doc
        for child in doc.get("children") or []:
            yield child


def _fetch_year(session: requests.Session, year: int) -> list[dict]:
    try:
        resp = session.get(API_URL, params={"year": str(year)}, timeout=25)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        print(f"    Sacombank {year}: {e}")
        return []

    if payload.get("statusCode") != 200:
        print(f"    Sacombank {year}: statusCode={payload.get('statusCode')}")
        return []

    items: list[dict] = []
    for doc in _iter_docs(payload.get("data") or []):
        title = (doc.get("title") or "").strip()
        link = _abs_link(doc.get("downloadPath") or "")
        if not title or not link:
            continue
        items.append(make_item(title, link, _doc_date(doc)))

    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    page_url = source.get("source_page", PAGE_URL)
    session.headers.setdefault("Accept", "application/json, text/plain, */*")
    session.headers.setdefault("Referer", page_url)

    current_year = datetime.now().year
    seen_uids: set[str] = set()
    all_items: list[dict] = []

    for year in (current_year, current_year - 1):
        for item in _fetch_year(session, year):
            if item["uid"] in seen_uids:
                continue
            seen_uids.add(item["uid"])
            all_items.append(item)

    return all_items
