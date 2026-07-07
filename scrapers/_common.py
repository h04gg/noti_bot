"""Helper dùng chung cho các scraper."""

from __future__ import annotations

import hashlib
import os
import re
import time
import types
from datetime import datetime
from urllib.parse import unquote, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from config import RECENT_DAYS
from filters import filter_recent_items, is_recent_item, parse_item_date, recent_cutoff

IMPERSONATE_PROFILES = ("chrome124", "chrome120", "safari17_0", "edge101")
CURL_RETRIES = 3
CURL_RETRY_DELAY = 3


class ScraperBlockedError(RuntimeError):
    """Trang 1 bị chặn (403/Cloudflare) — monitor sẽ báo Telegram."""


def normalize_link(link: str) -> str:
    """Chuẩn hóa URL để UID ổn định khi site đổi http/https hoặc thêm /."""
    link = (link or "").strip()
    if not link:
        return ""
    parsed = urlparse(link)
    scheme = parsed.scheme.lower()
    if scheme in ("http", "https"):
        scheme = "https"
    netloc = parsed.netloc.lower()
    path = unquote(parsed.path.rstrip("/")) or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def item_uid(link: str) -> str:
    return hashlib.md5(normalize_link(link).encode()).hexdigest()[:12]


def item_uid_legacy(link: str) -> str:
    """UID cũ (trước khi normalize) — dùng khi đọc state đã lưu."""
    return hashlib.md5((link or "").strip().encode()).hexdigest()[:12]


def is_known_item(item: dict, known_uids: set[str]) -> bool:
    if item["uid"] in known_uids:
        return True
    legacy = item_uid_legacy(item.get("link", ""))
    return legacy in known_uids and legacy != item["uid"]


def make_item(title: str, link: str, date: str) -> dict:
    link = link.strip()
    return {
        "uid": item_uid(link),
        "title": title.strip(),
        "link": link,
        "date": date,
    }


def format_dmY(day: str | int, month: str | int, year: str | int) -> str:
    return f"{int(day):02d}/{int(month):02d}/{year}"


def extract_dmY(text: str) -> str:
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text or "")
    if m:
        return format_dmY(m.group(1), m.group(2), m.group(3))
    return ""


def date_from_iso(raw: str) -> str:
    if not raw:
        return ""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except ValueError:
        return extract_dmY(raw) or raw[:10]


def proxy_for(source_id: str) -> dict[str, str] | None:
    """Proxy tùy chọn — {SID}_HTTP_PROXY hoặc HTTP_PROXY (GHA datacenter)."""
    env_key = f"{source_id.upper()}_HTTP_PROXY"
    raw = (os.environ.get(env_key) or os.environ.get("HTTP_PROXY") or "").strip()
    if not raw:
        return None
    return {"http": raw, "https": raw}


def page_fetch_failed(page: int, exc: Exception, label: str) -> None:
    """Trang 1 lỗi → raise để monitor retry; trang sau chỉ dừng phân trang."""
    print(f"    {label} page {page}: {exc}")
    if page == 1:
        raise RuntimeError(f"{label} page {page}: {exc}") from exc


def finalize_fetch(
    scraper_module: types.ModuleType,
    raw_items: list[dict],
    *,
    filter_recent: bool = False,
) -> list[dict]:
    """Ghi LAST_RAW_COUNT (trước lọc ngày) để monitor không báo nhầm trên GHA."""
    scraper_module.LAST_RAW_COUNT = len(raw_items)
    if filter_recent:
        return filter_recent_items(raw_items)
    return raw_items


def curl_get_text(
    url: str,
    *,
    source_id: str = "",
    headers: dict | None = None,
    timeout: int = 30,
    verify: bool = True,
) -> str:
    """GET qua curl_cffi + retry — dùng khi requests bị chặn trên GHA."""
    from curl_cffi import requests as curl_requests

    proxies = proxy_for(source_id) if source_id else None
    last_error: Exception | None = None
    for attempt in range(1, CURL_RETRIES + 1):
        profile = IMPERSONATE_PROFILES[(attempt - 1) % len(IMPERSONATE_PROFILES)]
        session = curl_requests.Session(impersonate=profile)
        try:
            resp = session.get(
                url,
                headers=headers,
                timeout=timeout,
                proxies=proxies,
                verify=verify,
            )
            if resp.status_code == 403:
                raise RuntimeError("HTTP 403 Forbidden")
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            last_error = e
            if attempt < CURL_RETRIES:
                print(
                    f"    curl {source_id or url[:40]} {profile} "
                    f"lần {attempt}/{CURL_RETRIES}: {e}"
                    f" — thử lại sau {CURL_RETRY_DELAY}s"
                )
                time.sleep(CURL_RETRY_DELAY)
        finally:
            session.close()
    raise RuntimeError(f"curl GET thất bại: {last_error}") from last_error


def fetch_html(session: requests.Session, url: str, **kwargs) -> BeautifulSoup | None:
    try:
        resp = session.get(url, timeout=kwargs.pop("timeout", 20), **kwargs)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"    HTML {url}: {e}")
        return None


def paginate_until_recent(
    fetch_page,
    *,
    max_pages: int = 20,
    scraper_module: types.ModuleType | None = None,
) -> list[dict]:
    """fetch_page(page) -> list[dict]; dừng khi trang không còn tin trong RECENT_DAYS."""
    all_items: list[dict] = []
    raw_count = 0
    for page in range(1, max_pages + 1):
        page_items = fetch_page(page)
        if not page_items:
            break
        raw_count += len(page_items)
        all_items.extend(item for item in page_items if is_recent_item(item))

        dates = [parse_item_date(item.get("date", "")) for item in page_items]
        dates = [dt for dt in dates if dt is not None]
        if dates and min(dates) < recent_cutoff(RECENT_DAYS):
            break
    if scraper_module is not None:
        scraper_module.LAST_RAW_COUNT = raw_count
    return all_items
