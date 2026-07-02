"""Helper dùng chung cho các scraper."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import unquote, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from config import RECENT_DAYS
from filters import is_recent_item, parse_item_date, recent_cutoff


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
) -> list[dict]:
    """fetch_page(page) -> list[dict]; dừng khi trang không còn tin trong RECENT_DAYS."""
    all_items: list[dict] = []
    for page in range(1, max_pages + 1):
        page_items = fetch_page(page)
        if not page_items:
            break
        all_items.extend(item for item in page_items if is_recent_item(item))

        dates = [parse_item_date(item.get("date", "")) for item in page_items]
        dates = [dt for dt in dates if dt is not None]
        if dates and min(dates) < recent_cutoff(RECENT_DAYS):
            break
    return all_items
