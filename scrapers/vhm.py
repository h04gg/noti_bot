"""Scraper: Vinhomes (VHM) — Công bố thông tin (Cloudflare → curl_cffi)."""

from __future__ import annotations

import re
import sys
import time

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from scrapers._common import IMPERSONATE_PROFILES, format_dmY, make_item, paginate_until_recent

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0
PAGE_URL = "https://vinhomes.vn/vi/cong-bo-thong-tin"
HOME_URL = "https://vinhomes.vn/vi"
FETCH_RETRIES = 2
RETRY_DELAY = 5



def _is_cloudflare_block(status_code: int, html: str) -> bool:
    if status_code == 403:
        return True
    low = (html or "").lower()
    return "just a moment" in low or "challenge-platform" in low


def _parse_date(raw: str) -> str:
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", raw or "")
    if m:
        return format_dmY(m.group(1), m.group(2), m.group(3))
    return ""


def _parse_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()
    for row in soup.select(".views-row .node-teaser-cong-bo-thong-tin"):
        a = row.select_one("a[href]")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        link = a["href"].strip()
        if not title or not link or link in seen:
            continue
        seen.add(link)
        dt_el = row.select_one(".date-create")
        date = _parse_date(dt_el.get_text(strip=True) if dt_el else "")
        items.append(make_item(title, link, date))
    return items


def _warm_session(session: curl_requests.Session) -> None:
    """Lấy cookie Cloudflare từ trang chủ trước khi vào CBTT."""
    try:
        session.get(HOME_URL, timeout=25)
    except Exception as e:
        print(f"    VHM warmup: {e}")


def _fetch_url(url: str) -> tuple[int, str]:
    """GET với session + retry nhiều browser profile."""
    last_error: Exception | None = None

    for attempt in range(1, FETCH_RETRIES + 1):
        profile = IMPERSONATE_PROFILES[(attempt - 1) % len(IMPERSONATE_PROFILES)]
        session = curl_requests.Session(impersonate=profile)
        try:
            _warm_session(session)
            resp = session.get(url, timeout=45)
            if _is_cloudflare_block(resp.status_code, resp.text):
                raise RuntimeError(f"HTTP {resp.status_code} (Cloudflare chặn)")
            resp.raise_for_status()
            return resp.status_code, resp.text
        except Exception as e:
            last_error = e
            if attempt < FETCH_RETRIES:
                print(
                    f"    VHM {profile} lần {attempt}/{FETCH_RETRIES}: {e}"
                    f" — thử lại sau {RETRY_DELAY}s"
                )
                time.sleep(RETRY_DELAY)
        finally:
            session.close()

    raise RuntimeError(f"VHM fetch thất bại: {last_error}") from last_error


def fetch(source: dict, session) -> list[dict]:
    base_url = source.get("url", PAGE_URL)
    blocked_on_first_page = False

    def _page(page: int) -> list[dict]:
        nonlocal blocked_on_first_page
        page_index = page - 1
        url = f"{base_url.rstrip('/')}?page={page_index}"
        try:
            _, html = _fetch_url(url)
        except Exception as e:
            print(f"    VHM page {page}: {e}")
            if page == 1:
                blocked_on_first_page = True
                raise RuntimeError(str(e)) from e
            return []
        return _parse_html(html)

    try:
        return paginate_until_recent(_page, scraper_module=_MOD)
    except RuntimeError:
        if blocked_on_first_page:
            raise
        return []
