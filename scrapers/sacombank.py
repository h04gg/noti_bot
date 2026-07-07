"""Scraper: Sacombank (STB) — AEM JSON shareholdernotice + financial reports."""

from __future__ import annotations

import sys
from datetime import datetime

import requests

from scrapers._common import date_from_iso, extract_dmY, finalize_fetch, make_item

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0

BASE = "https://www.sacombank.com.vn"
NOTICE_API_URL = (
    f"{BASE}/trang-chu/nha-dau-tu/cong-bo-thong-tin/_jcr_content/root/container/"
    "container/shareholdernotice.sacom.shnotice.json"
)
FINANCIAL_API_URL = (
    f"{BASE}/trang-chu/nha-dau-tu/bao-cao/_jcr_content/root/container/container/"
    "reportlisting.sacom.reportlisting.financial.json"
)
NOTICE_PAGE_URL = f"{BASE}/trang-chu/nha-dau-tu/cong-bo-thong-tin.html"


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


def _fetch_notice_year(session: requests.Session, api_url: str, year: int, *, critical: bool = False) -> list[dict]:
    try:
        resp = session.get(api_url, params={"year": str(year)}, timeout=25)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        print(f"    Sacombank CBTT {year}: {e}")
        if critical:
            raise RuntimeError(f"Sacombank CBTT {year}: {e}") from e
        return []

    if payload.get("statusCode") != 200:
        msg = f"statusCode={payload.get('statusCode')}"
        print(f"    Sacombank CBTT {year}: {msg}")
        if critical:
            raise RuntimeError(f"Sacombank CBTT {year}: {msg}")
        return []

    items: list[dict] = []
    for doc in _iter_docs(payload.get("data") or []):
        title = (doc.get("title") or "").strip()
        link = _abs_link(doc.get("downloadPath") or "")
        if not title or not link:
            continue
        items.append(make_item(title, link, _doc_date(doc)))

    return items


def _fetch_financial_year(session: requests.Session, api_url: str, year: int, *, critical: bool = False) -> list[dict]:
    try:
        resp = session.get(api_url, params={"year": str(year)}, timeout=25)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        print(f"    Sacombank BCTC {year}: {e}")
        if critical:
            raise RuntimeError(f"Sacombank BCTC {year}: {e}") from e
        return []

    if payload.get("statusCode") != 200:
        msg = f"statusCode={payload.get('statusCode')}"
        print(f"    Sacombank BCTC {year}: {msg}")
        if critical:
            raise RuntimeError(f"Sacombank BCTC {year}: {msg}")
        return []

    items: list[dict] = []
    for group in payload.get("data") or []:
        quarter = (group.get("title") or "").strip()
        for doc in group.get("documents") or []:
            title = (doc.get("reportTitle") or "").strip()
            link = _abs_link(doc.get("urlFinancialReportStatements") or "")
            if not title or not link:
                continue
            date = extract_dmY(f"{quarter} {payload.get('date', year)} {title}")
            items.append(make_item(title, link, date))

    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    notice_api = source.get("api_url", NOTICE_API_URL)
    financial_api = source.get("financial_api_url", FINANCIAL_API_URL)
    page_url = source.get("source_page", NOTICE_PAGE_URL)
    session.headers.setdefault("Accept", "application/json, text/plain, */*")
    session.headers.setdefault("Referer", page_url)

    current_year = datetime.now().year
    seen_uids: set[str] = set()
    cbtt_items: list[dict] = []
    bctc_items: list[dict] = []

    for year in (current_year, current_year - 1):
        cbtt_items.extend(_fetch_notice_year(session, notice_api, year, critical=(year == current_year)))
        bctc_items.extend(_fetch_financial_year(session, financial_api, year, critical=False))

    all_items: list[dict] = []
    for item in cbtt_items + bctc_items:
        if item["uid"] in seen_uids:
            continue
        seen_uids.add(item["uid"])
        all_items.append(item)

    print(f"    Sacombank CBTT: {len(cbtt_items)}, BCTC: {len(bctc_items)}")
    return finalize_fetch(_MOD, all_items)
