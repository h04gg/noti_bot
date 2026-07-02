"""Scraper: MB Securities (MBS) — HTML (Cloudflare → curl_cffi)."""

from __future__ import annotations

import time

import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from scrapers._common import (
    ScraperBlockedError,
    extract_dmY,
    make_item,
    paginate_until_recent,
)

BASE = "https://www.mbs.com.vn"
PAGE_URL = f"{BASE}/cong-bo-thong-tin/"
IMPERSONATE_PROFILES = ("chrome124", "chrome120", "safari17_0")
FETCH_RETRIES = 3
RETRY_DELAY = 3


def _page_url(base: str, page: int) -> str:
    if page <= 1:
        return base
    return f"{base.rstrip('/')}/page/{page}/"


def _is_blocked(status_code: int, html: str) -> bool:
    if status_code == 403:
        return True
    low = (html or "").lower()
    return "just a moment" in low or "challenge-platform" in low


def _parse_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()
    for block in soup.select("div.flex.flex-col.gap-4"):
        a = block.select_one("h3 a[href]")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        link = a["href"].strip()
        if not title or not link or link in seen:
            continue
        if not link.startswith("http"):
            link = BASE + link
        seen.add(link)

        date_el = block.select_one("p")
        date = extract_dmY(date_el.get_text(strip=True) if date_el else "") or extract_dmY(title)
        items.append(make_item(title, link, date))
    return items


def _fetch_page(url: str) -> str:
    last_error: Exception | None = None
    for attempt in range(1, FETCH_RETRIES + 1):
        profile = IMPERSONATE_PROFILES[(attempt - 1) % len(IMPERSONATE_PROFILES)]
        try:
            resp = curl_requests.get(
                url,
                impersonate=profile,
                timeout=30,
                headers={"Accept-Language": "vi-VN,vi;q=0.9"},
            )
            if _is_blocked(resp.status_code, resp.text):
                raise ScraperBlockedError(f"HTTP {resp.status_code} (Cloudflare chặn)")
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            last_error = e
            if attempt < FETCH_RETRIES:
                print(
                    f"    MBS {profile} lần {attempt}/{FETCH_RETRIES}: {e}"
                    f" — thử lại sau {RETRY_DELAY}s"
                )
                time.sleep(RETRY_DELAY)
    raise ScraperBlockedError(str(last_error) if last_error else "MBS fetch thất bại")


def fetch(source: dict, session: requests.Session) -> list[dict]:
    base_url = source.get("url", PAGE_URL)

    def _page(page: int) -> list[dict]:
        url = _page_url(base_url, page)
        try:
            html = _fetch_page(url)
        except ScraperBlockedError as e:
            print(f"    MBS page {page}: {e}")
            if page == 1:
                raise
            return []
        except Exception as e:
            print(f"    MBS page {page}: {e}")
            if page == 1:
                raise RuntimeError(str(e)) from e
            return []
        return _parse_html(html)

    return paginate_until_recent(_page)
