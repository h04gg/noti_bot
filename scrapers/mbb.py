"""Scraper: MB Bank (MBB) — API GetListMessage + GetListFinance."""

from __future__ import annotations

import re
import sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from scrapers._common import date_from_iso, finalize_fetch, make_item

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0

BASE = "https://www.mbbank.com.vn"


def _investor_url(template: str, year: int) -> str:
    tpl = template or f"{BASE}/Investor/thong-bao-nha-dau-tu/{{year}}/0//0"
    if "{year}" in tpl:
        return tpl.format(year=year)
    return re.sub(r"/\d{4}/", f"/{year}/", tpl, count=1)


def _csrf_headers(session: requests.Session, page_url: str, *, refresh: bool = False) -> dict[str, str]:
    if refresh:
        session.cookies.clear()
    resp = session.get(page_url, timeout=40, verify=False)
    resp.raise_for_status()
    token_el = BeautifulSoup(resp.text, "html.parser").find(
        "input", {"name": "__RequestVerificationToken"}
    )
    if not token_el:
        raise RuntimeError("MBB: không lấy được CSRF token")
    return {
        "MB-XSRF-Token-FormOnline": token_el["value"],
        "Referer": page_url,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }


def _fetch_messages(session: requests.Session, source: dict, year: int) -> list[dict]:
    page_url = _investor_url(
        source.get("url", f"{BASE}/Investor/thong-bao-nha-dau-tu/{{year}}/0//0"),
        year,
    )
    headers = _csrf_headers(session, page_url)

    items: list[dict] = []
    seen: set[str] = set()
    page = 1
    while page <= 5:
        try:
            api_resp = session.get(
                f"{BASE}/api/GetListMessage/{page}/{year}",
                headers=headers,
                timeout=30,
                verify=False,
            )
            if api_resp.status_code == 403 and page > 1:
                headers = _csrf_headers(session, page_url, refresh=True)
                api_resp = session.get(
                    f"{BASE}/api/GetListMessage/{page}/{year}",
                    headers=headers,
                    timeout=30,
                    verify=False,
                )
            api_resp.raise_for_status()
            data = api_resp.json()
        except Exception as e:
            print(f"    MBB CBTT API page {page}: {e}")
            if page == 1:
                raise RuntimeError(f"MBB CBTT API page {page}: {e}") from e
            break

        batch = (data.get("topNews") or []) + (data.get("otherNews") or [])
        if not batch:
            break

        for doc in batch:
            title = (doc.get("title") or "").strip()
            alias = (doc.get("alias") or "").strip()
            catalias = (doc.get("catalias") or "thong-bao").strip()
            doc_id = doc.get("id")
            if not title or not alias or not doc_id:
                continue
            link = f"{BASE}/chi-tiet-thong-bao/{catalias}/{alias}/{doc_id}"
            if link in seen:
                continue
            seen.add(link)
            date = date_from_iso(doc.get("last_save_date", ""))
            items.append(make_item(title, link, date))

        page_info = (data.get("currentPageinfo") or [{}])[0]
        if page >= int(page_info.get("totalPage") or page):
            break
        page += 1

    return items


def _fetch_finance(session: requests.Session, source: dict, year: int) -> list[dict]:
    bctc_tpl = source.get(
        "bctc_url",
        f"{BASE}/Investor/bao-cao-tai-chinh/{{year}}/0//0",
    )
    page_url = _investor_url(bctc_tpl, year)
    headers = _csrf_headers(session, page_url)
    cata_id = int(source.get("bctc_cata_id", 0))

    items: list[dict] = []
    seen: set[str] = set()
    page = 1
    while page <= 5:
        try:
            api_resp = session.get(
                f"{BASE}/api/GetListFinance/{cata_id}/{page}/{year}",
                headers=headers,
                timeout=20,
                verify=False,
            )
            api_resp.raise_for_status()
            data = api_resp.json()
        except Exception as e:
            print(f"    MBB BCTC API page {page} ({year}): {e}")
            if page == 1:
                raise RuntimeError(f"MBB BCTC API ({year}): {e}") from e
            break

        batch = data.get("lst") or []
        if not batch:
            break

        for doc in batch:
            title = (doc.get("title") or "").strip()
            file_path = (doc.get("file_path") or "").strip()
            if not title or not file_path:
                continue
            link = file_path if file_path.startswith("http") else f"{BASE}{file_path}"
            if link in seen:
                continue
            seen.add(link)
            date = date_from_iso(doc.get("last_Save_Date") or doc.get("last_save_date") or "")
            items.append(make_item(title, link, date))

        if len(batch) < 20:
            break
        page += 1

    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    year = datetime.now().year
    merged: list[dict] = []
    seen_uids: set[str] = set()

    cbtt_items: list[dict] = []
    for fetch_year in (year, year - 1):
        try:
            batch = _fetch_messages(session, source, fetch_year)
            if batch:
                cbtt_items = batch
                break
        except RuntimeError as e:
            if fetch_year == year:
                print(f"    {e}")
            if fetch_year == year - 1:
                raise

    for item in cbtt_items:
        if item["uid"] in seen_uids:
            continue
        seen_uids.add(item["uid"])
        merged.append(item)

    bctc_items: list[dict] = []
    for fetch_year in (year, year - 1):
        try:
            bctc_items.extend(_fetch_finance(session, source, fetch_year))
        except RuntimeError as e:
            if fetch_year == year:
                raise
            print(f"    {e}")

    for item in bctc_items:
        if item["uid"] in seen_uids:
            continue
        seen_uids.add(item["uid"])
        merged.append(item)

    print(f"    MBB CBTT: {len(cbtt_items)}, BCTC: {len(bctc_items)} (năm {year})")
    return finalize_fetch(_MOD, merged)
