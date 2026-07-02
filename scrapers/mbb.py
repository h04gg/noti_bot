"""Scraper: MB Bank (MBB) — API GetListMessage."""

from __future__ import annotations

import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from scrapers._common import date_from_iso, make_item

BASE = "https://www.mbbank.com.vn"


def _page_url(source: dict, year: int) -> str:
    """URL trang investor — thay /YYYY/ trong config bằng năm hiện tại."""
    template = source.get(
        "url",
        f"{BASE}/Investor/thong-bao-nha-dau-tu/{{year}}/0//0",
    )
    if "{year}" in template:
        return template.format(year=year)
    return re.sub(r"/Investor/thong-bao-nha-dau-tu/\d{4}/", f"/Investor/thong-bao-nha-dau-tu/{year}/", template)


def fetch(source: dict, session: requests.Session) -> list[dict]:
    year = datetime.now().year
    page_url = _page_url(source, year)

    try:
        resp = session.get(page_url, timeout=25, verify=False)
        resp.raise_for_status()
    except Exception as e:
        print(f"    MBB HTML: {e}")
        return []

    token_el = BeautifulSoup(resp.text, "html.parser").find(
        "input", {"name": "__RequestVerificationToken"}
    )
    if not token_el:
        print("    MBB: không lấy được CSRF token")
        return []

    headers = {
        "MB-XSRF-Token-FormOnline": token_el["value"],
        "Referer": page_url,
        "X-Requested-With": "XMLHttpRequest",
    }

    items: list[dict] = []
    seen: set[str] = set()
    page = 1
    while page <= 5:
        try:
            api_resp = session.get(
                f"{BASE}/api/GetListMessage/{page}/{year}",
                headers=headers,
                timeout=20,
                verify=False,
            )
            api_resp.raise_for_status()
            data = api_resp.json()
        except Exception as e:
            print(f"    MBB API page {page}: {e}")
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
