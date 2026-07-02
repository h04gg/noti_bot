"""Scraper: ACB — API front/v1/posts (Công bố thông tin nhà đầu tư)."""

from __future__ import annotations

from datetime import datetime

import requests

from config import RECENT_DAYS
from filters import parse_item_date, recent_cutoff
from scrapers._common import date_from_iso, make_item

BASE = "https://acb.com.vn"
API_URL = f"{BASE}/api/front/v1/posts"
TAGS_URL = f"{BASE}/api/front/v1/tags"
PAGE_URL = f"{BASE}/nha-dau-tu"


def _doc_link(doc: dict) -> str:
    featured = doc.get("featured_image") or {}
    path = (featured.get("path") or "").strip()
    if path:
        return path if path.startswith("http") else f"{BASE}/{path.lstrip('/')}"

    seo_paths = (doc.get("_seoPaths") or {}).get("paths") or {}
    vi_path = (seo_paths.get("vi") or "").strip()
    if vi_path:
        return f"{BASE}/{vi_path.lstrip('/')}"
    return ""


def _doc_date(doc: dict) -> str:
    return date_from_iso(doc.get("created_at") or "")


def _resolve_session_tag(session: requests.Session, year: int) -> int | None:
    """Tag năm trên ACB (title = '2026', …) — lấy từ /api/front/v1/tags."""
    try:
        resp = session.get(TAGS_URL, params={"limit": 100}, timeout=20)
        resp.raise_for_status()
        tags = resp.json().get("data") or []
    except Exception as e:
        print(f"    ACB tags API: {e}")
        return None

    year_label = str(year)
    for tag in tags:
        if str(tag.get("title", "")).strip() == year_label:
            return int(tag["id"])
    print(f"    ACB: chưa có tag năm {year_label}, bỏ lọc session_tags")
    return None


def _search_params(source: dict, page: int, session_tag: int | None) -> dict:
    cfg = source.get("params", {})
    params = {
        "search[categories.category_id:in]": str(cfg.get("category_id", 656)),
        "search[is_active:in]": "1",
        "page": page,
        "limit": int(cfg.get("limit", 20)),
    }
    if session_tag is not None:
        params["search[session_tags::tags:in]"] = str(session_tag)
    return params


def fetch(source: dict, session: requests.Session) -> list[dict]:
    api_url = source.get("api_url", API_URL)
    page_url = source.get("source_page", PAGE_URL)

    session.headers.setdefault("Accept", "application/json")
    session.headers.setdefault("Referer", page_url)
    session.headers.setdefault("X-Requested-Store", "default")
    session.headers.setdefault("X-Requested-With", "XMLHttpRequest")

    session_tag = _resolve_session_tag(session, datetime.now().year)
    items: list[dict] = []
    seen_uids: set[str] = set()
    page = 1

    while page <= 20:
        try:
            resp = session.get(
                api_url,
                params=_search_params(source, page, session_tag),
                timeout=25,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            print(f"    ACB page {page}: {e}")
            break

        docs = payload.get("data") or []
        if not docs:
            break

        page_items: list[dict] = []
        for doc in docs:
            title = (doc.get("title") or "").strip()
            link = _doc_link(doc)
            if not title or not link:
                continue
            item = make_item(title, link, _doc_date(doc))
            if item["uid"] in seen_uids:
                continue
            seen_uids.add(item["uid"])
            page_items.append(item)

        items.extend(page_items)

        dates = [parse_item_date(item.get("date", "")) for item in page_items]
        dates = [dt for dt in dates if dt is not None]
        if dates and min(dates) < recent_cutoff(RECENT_DAYS):
            break

        meta = payload.get("meta") or {}
        if page >= int(meta.get("last_page") or page):
            break
        page += 1

    return items
