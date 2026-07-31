"""Scraper: DIG (DIC Corp) — HTML CBTT + Báo cáo tài chính."""

from __future__ import annotations

import re
import sys
import time
from datetime import datetime

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from config import RECENT_DAYS
from filters import newest_item_date, parse_item_date, recent_cutoff
from scrapers._common import finalize_fetch, make_item

_MOD = sys.modules[__name__]
BASE = "https://www.dic.vn"
CBTT_PAGE = f"{BASE}/cong-bo-thong-tin"
BCTC_PAGE = f"{BASE}/bao-cao-tai-chinh"
IMPERSONATE_PROFILES = ("chrome124", "chrome120", "safari17_0", "edge101")
DIC_TIMEOUT = 60
DIC_RETRIES = 2
DIC_RETRY_DELAY = 6
MAX_PAGES = 30
LAST_RAW_COUNT = 0



def _is_blocked(status_code: int, html: str) -> bool:
    if status_code == 403:
        return True
    low = (html or "").lower()
    return "just a moment" in low or "challenge-platform" in low or "access denied" in low


def _warmup_session(session: curl_requests.Session) -> None:
    session.get(
        BASE,
        headers={"Accept-Language": "vi-VN,vi;q=0.9"},
        timeout=DIC_TIMEOUT,
    )


def _open_session(profile: str) -> curl_requests.Session:
    session = curl_requests.Session(impersonate=profile)
    _warmup_session(session)
    return session


def _get_html(
    session: curl_requests.Session,
    url: str,
    page: int,
    referer: str,
) -> str:
    params = {"page": page} if page > 1 else None
    resp = session.get(
        url,
        params=params,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": referer,
        },
        timeout=DIC_TIMEOUT,
    )
    if _is_blocked(resp.status_code, resp.text):
        raise RuntimeError("HTTP 403 Forbidden / Cloudflare")
    resp.raise_for_status()
    return resp.text


def _article_anchors(soup: BeautifulSoup, path_key: str) -> list:
    anchors = soup.select(f'div.intro a.title[href*="{path_key}"]')
    if anchors:
        return anchors
    return [
        a
        for a in soup.select("div.item a.title")
        if path_key in (a.get("href") or "")
    ]


def _page_has_articles(html: str, path_key: str) -> bool:
    if _is_blocked(200, html):
        return False
    return bool(_article_anchors(BeautifulSoup(html, "html.parser"), path_key))


def _extract_date(anchor) -> str:
    intro = anchor.find_parent(class_="intro")
    if intro:
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", intro.get_text(" ", strip=True))
        if m:
            return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"

    for sib in anchor.next_siblings:
        if getattr(sib, "name", None) == "span":
            m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", sib.get_text(" ", strip=True))
            if m:
                return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"
    return ""


def _parse_page(html: str, path_key: str, min_year: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for a in _article_anchors(soup, path_key):
        href = (a.get("href") or "").strip()
        title = a.get_text(" ", strip=True).strip()
        if not title:
            continue

        link = href if href.startswith("http") else f"{BASE}/{href.lstrip('/')}"
        if link in seen:
            continue
        seen.add(link)

        date = _extract_date(a)
        dt = parse_item_date(date)
        if dt is not None and dt.year < min_year:
            continue

        items.append(make_item(title, link, date))

    return items


def _fetch_section(
    page_url: str, path_key: str, referer: str, label: str, min_year: int
) -> list[dict]:
    all_items: list[dict] = []
    session: curl_requests.Session | None = None

    try:
        for page in range(1, MAX_PAGES + 1):
            html: str | None = None
            last_error: Exception | None = None

            for attempt in range(1, DIC_RETRIES + 1):
                profile = IMPERSONATE_PROFILES[(attempt - 1) % len(IMPERSONATE_PROFILES)]
                try:
                    if session is None:
                        session = _open_session(profile)
                    html = _get_html(session, page_url, page, referer)
                    break
                except Exception as e:
                    last_error = e
                    if session is not None:
                        session.close()
                        session = None
                    if attempt < DIC_RETRIES:
                        print(
                            f"    DIC {profile} {label} page {page}: lỗi lần {attempt}/{DIC_RETRIES}: {e}"
                            f" — thử lại sau {DIC_RETRY_DELAY}s"
                        )
                        time.sleep(DIC_RETRY_DELAY)

            if html is None:
                if page == 1:
                    raise RuntimeError(f"DIC {label} page {page}: {last_error}") from last_error
                break

            if page == 1 and not _page_has_articles(html, path_key):
                raise RuntimeError(f"DIC {label} page 1: HTML không hợp lệ (có thể bị chặn)")

            page_items = _parse_page(html, path_key, min_year)
            if not page_items:
                if page == 1:
                    raise RuntimeError(
                        f"DIC {label} page 1: không parse được tin (có thể bị chặn)"
                    )
                break

            all_items.extend(page_items)

            page_newest = newest_item_date(page_items)
            if page_newest and page_newest < recent_cutoff(RECENT_DAYS):
                break

            dates = [parse_item_date(item.get("date", "")) for item in page_items]
            dates = [dt for dt in dates if dt is not None]
            if dates and min(dates).year < min_year:
                break
    finally:
        if session is not None:
            session.close()

    return all_items


def fetch(source: dict, session) -> list[dict]:
    year = datetime.now().year
    min_year = year - 1
    cbtt_page = source.get("url", CBTT_PAGE)
    bctc_page = source.get("bctc_page", BCTC_PAGE)

    merged: list[dict] = []
    seen: set[str] = set()

    cbtt_items = _fetch_section(
        cbtt_page, "cong-bo-thong-tin/", cbtt_page, "CBTT", min_year
    )
    for item in cbtt_items:
        if item["uid"] not in seen:
            seen.add(item["uid"])
            merged.append(item)

    try:
        bctc_items = _fetch_section(
            bctc_page, "bao-cao-tai-chinh/", bctc_page, "BCTC", min_year
        )
    except RuntimeError as e:
        print(f"    {e} — bỏ qua BCTC lần này")
        bctc_items = []

    for item in bctc_items:
        if item["uid"] not in seen:
            seen.add(item["uid"])
            merged.append(item)

    print(f"    DIC CBTT: {len(cbtt_items)}, BCTC: {len(bctc_items)}")
    return finalize_fetch(_MOD, merged)
