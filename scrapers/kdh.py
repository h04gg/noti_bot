"""Scraper: Khang Điền (KDH) — WordPress AJAX CBTT + HTML Báo cáo & Cao bạch."""

from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from filters import parse_item_date
from scrapers._common import extract_dmY, finalize_fetch, format_dmY, make_item

_MOD = sys.modules[__name__]
BASE = "https://www.khangdien.com.vn"
CBTT_PAGE = f"{BASE}/co-dong/cong-bo-thong-tin"
BCCB_PAGE = f"{BASE}/co-dong/bao-cao-cao-bach"
AJAX_URL = f"{BASE}/wp-admin/admin-ajax.php"
IMPERSONATE_PROFILES = ("chrome124", "chrome120", "safari17_0", "edge101")
KDH_TIMEOUT = 60
KDH_RETRIES = 4
KDH_RETRY_DELAY = 6
HOME_URL = f"{BASE}/"
LAST_RAW_COUNT = 0


def _proxy() -> dict[str, str] | None:
    raw = (os.environ.get("KDH_HTTP_PROXY") or os.environ.get("HTTP_PROXY") or "").strip()
    if not raw:
        return None
    return {"http": raw, "https": raw}


def _is_blocked(status_code: int, html: str) -> bool:
    if status_code == 403:
        return True
    low = (html or "").lower()
    return "just a moment" in low or "challenge-platform" in low or "access denied" in low


def _get_html(url: str, referer: str, label: str) -> str:
    proxies = _proxy()
    last_error: Exception | None = None

    for attempt in range(1, KDH_RETRIES + 1):
        profile = IMPERSONATE_PROFILES[(attempt - 1) % len(IMPERSONATE_PROFILES)]
        session = curl_requests.Session(impersonate=profile)
        try:
            session.get(
                HOME_URL,
                headers={"Accept-Language": "vi-VN,vi;q=0.9"},
                timeout=KDH_TIMEOUT,
                proxies=proxies,
            )
            resp = session.get(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Referer": referer,
                },
                timeout=KDH_TIMEOUT,
                proxies=proxies,
            )
            if resp.status_code == 403:
                raise RuntimeError("HTTP 403 Forbidden")
            if _is_blocked(resp.status_code, resp.text):
                raise RuntimeError("HTTP 403 Forbidden / Cloudflare")
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            last_error = e
            if attempt < KDH_RETRIES:
                print(
                    f"    KDH {profile} {label}: lỗi lần {attempt}/{KDH_RETRIES}: {e}"
                    f" — thử lại sau {KDH_RETRY_DELAY}s"
                )
                time.sleep(KDH_RETRY_DELAY)
        finally:
            session.close()

    raise RuntimeError(f"KDH {label}: {last_error}") from last_error


def _post_ajax(data: dict, referer: str, label: str) -> str:
    proxies = _proxy()
    last_error: Exception | None = None

    for attempt in range(1, KDH_RETRIES + 1):
        profile = IMPERSONATE_PROFILES[(attempt - 1) % len(IMPERSONATE_PROFILES)]
        session = curl_requests.Session(impersonate=profile)
        try:
            session.get(HOME_URL, timeout=KDH_TIMEOUT, proxies=proxies)
            resp = session.post(
                AJAX_URL,
                data=data,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Referer": referer,
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=KDH_TIMEOUT,
                proxies=proxies,
            )
            if resp.status_code == 403:
                raise RuntimeError("HTTP 403 Forbidden")
            resp.raise_for_status()
            if len(resp.text.strip()) < 20:
                raise RuntimeError("AJAX trả về rỗng")
            return resp.text
        except Exception as e:
            last_error = e
            if attempt < KDH_RETRIES:
                print(
                    f"    KDH {profile} {label}: lỗi lần {attempt}/{KDH_RETRIES}: {e}"
                    f" — thử lại sau {KDH_RETRY_DELAY}s"
                )
                time.sleep(KDH_RETRY_DELAY)
        finally:
            session.close()

    raise RuntimeError(f"KDH {label}: {last_error}") from last_error


def _year_term_id(page_html: str, years: list[int]) -> tuple[str, int]:
    soup = BeautifulSoup(page_html, "html.parser")
    options = {
        opt.get_text(strip=True): (opt.get("value") or "").strip()
        for opt in soup.select("#chonnamdexem option")
    }
    for year in years:
        value = options.get(str(year), "")
        if value and value.isdigit():
            return value, year
    available = [k for k, v in options.items() if k.isdigit() and v.isdigit()]
    raise RuntimeError(
        f"Không tìm thấy năm {years[0]} trên trang CBTT"
        + (f" (có: {', '.join(available[:5])})" if available else " (dropdown rỗng)")
    )


def _parse_pdf_links(html: str, year: int | None = None) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for a in soup.select('a[href*=".pdf"]'):
        link = (a.get("href") or "").strip()
        if not link or link in seen:
            continue
        if not link.startswith("http"):
            link = BASE + link
        seen.add(link)

        title = a.get_text(" ", strip=True)
        if not title or len(title) < 5:
            continue

        date = ""
        parent = a.parent
        for _ in range(5):
            if not parent:
                break
            date = extract_dmY(parent.get_text(" ", strip=True))
            if date:
                break
            parent = parent.parent
        if not date:
            m = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", link)
            if m:
                date = format_dmY(m.group(3), m.group(2), m.group(1))

        if year is not None:
            dt = parse_item_date(date)
            if dt is not None and dt.year < year - 1:
                continue

        items.append(make_item(title, link, date))

    return items


def _discover_bccb_pages(main_html: str, bccb_page: str) -> list[str]:
    soup = BeautifulSoup(main_html, "html.parser")
    pages = {bccb_page.rstrip("/")}
    prefix = bccb_page.rstrip("/") + "/"
    for a in soup.select('a.viewmore[href], a[href*="bao-cao-cao-bach/"]'):
        href = (a.get("href") or "").strip()
        if not href.startswith("http"):
            href = BASE + href
        if href.rstrip("/") == bccb_page.rstrip("/"):
            continue
        if prefix in href:
            pages.add(href.rstrip("/"))
    return sorted(pages)


def _fetch_cbtt(cbtt_page: str, year: int) -> list[dict]:
    page_html = _get_html(cbtt_page, cbtt_page, "CBTT page")
    if "#chonnamdexem" not in page_html:
        raise RuntimeError("KDH CBTT: không thấy dropdown năm (có thể bị chặn)")
    year_id, picked_year = _year_term_id(page_html, [year, year - 1])
    ajax_html = _post_ajax(
        {"action": "vts_ajax_show_data", "nam": year_id},
        cbtt_page,
        f"CBTT AJAX {picked_year}",
    )
    return _parse_pdf_links(ajax_html)


def _fetch_bccb(bccb_page: str, year: int) -> list[dict]:
    main_html = _get_html(bccb_page, bccb_page, "BCCB page")
    pages = _discover_bccb_pages(main_html, bccb_page)
    merged: list[dict] = []
    seen: set[str] = set()

    for page_url in pages:
        html = main_html if page_url.rstrip("/") == bccb_page.rstrip("/") else _get_html(
            page_url, bccb_page, f"BCCB {page_url.rsplit('/', 1)[-1]}"
        )
        for item in _parse_pdf_links(html, year=year):
            if item["uid"] in seen:
                continue
            seen.add(item["uid"])
            merged.append(item)

    return merged


def fetch(source: dict, session) -> list[dict]:
    year = datetime.now().year
    cbtt_page = source.get("url", CBTT_PAGE)
    bccb_page = source.get("bccb_page", BCCB_PAGE)

    merged: list[dict] = []
    seen: set[str] = set()

    cbtt_items = _fetch_cbtt(cbtt_page, year)
    for item in cbtt_items:
        if item["uid"] not in seen:
            seen.add(item["uid"])
            merged.append(item)

    try:
        bccb_items = _fetch_bccb(bccb_page, year)
    except RuntimeError as e:
        print(f"    {e} — bỏ qua BCCB lần này")
        bccb_items = []

    for item in bccb_items:
        if item["uid"] not in seen:
            seen.add(item["uid"])
            merged.append(item)

    print(f"    KDH CBTT: {len(cbtt_items)}, BCCB: {len(bccb_items)}")
    return finalize_fetch(_MOD, merged)
