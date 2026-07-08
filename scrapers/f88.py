"""Scraper: F88 — API nhà đầu tư (CBTT + Báo cáo tài chính)."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from scrapers._common import finalize_fetch, make_item

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0

BASE = "https://nhadautu.f88.vn"
API_URL = "https://apis.f88.vn/growth/f88vn/api/v1/Initial/InitPageInvestDocument"
BCTC_NEWS_API = "https://apis.f88.vn/growth/f88vn/api/v1/Initial/InitPageNewsSub"
CBTT_PAGE = f"{BASE}/cong-bo-thong-tin"
BCTC_PAGE = f"{BASE}/bao-cao-tai-chinh"

# Các tab trên https://nhadautu.f88.vn/cong-bo-thong-tin
CBTT_CATEGORIES = ("10115", "10108", "10122", "10123", "10118")

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(?P<payload>.*?)</script>',
    re.DOTALL,
)


def _date_from_ms(raw) -> str:
    if not raw:
        return ""
    try:
        ts = int(raw)
        if ts > 10_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts).strftime("%d/%m/%Y")
    except (TypeError, ValueError, OSError):
        return ""


def _parse_next_data(html: str) -> dict:
    match = _NEXT_DATA_RE.search(html or "")
    if not match:
        return {}
    try:
        return json.loads(match.group("payload"))
    except json.JSONDecodeError:
        return {}


def _fetch_category(session: requests.Session, category_id: str, api_url: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    next_token = 0
    first_request = True

    while True:
        try:
            resp = session.post(
                api_url,
                json={"CategoryId": category_id, "NextToken": next_token, "Lang": "vi"},
                timeout=25,
            )
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload.get("data"), dict):
                payload = payload["data"]
        except Exception as e:
            print(f"    F88 API cat {category_id}: {e}")
            if first_request and category_id == CBTT_CATEGORIES[0]:
                raise RuntimeError(f"F88 API cat {category_id}: {e}") from e
            break

        first_request = False
        for doc in payload.get("Items") or []:
            title = (doc.get("Title") or "").strip()
            if not title:
                continue

            files = doc.get("Files") or []
            link = ""
            if files:
                link = (files[0].get("FilePath") or files[0].get("FileName") or "").strip()
            if not link:
                continue
            if link in seen:
                continue
            seen.add(link)

            date = _date_from_ms(doc.get("CreatedDate"))
            items.append(make_item(title, link, date))

        if not payload.get("HasNextPage"):
            break
        next_token = payload.get("NextToken", next_token)
        if next_token == 0:
            break

    return items


def _news_entries_from_payload(payload: dict) -> list[dict]:
    """Gom tin BCTC từ __NEXT_DATA__ (news + featured)."""
    page_props = (payload.get("props") or {}).get("pageProps") or {}
    entries: list[dict] = []
    seen_slugs: set[str] = set()

    def _add(raw: dict | None) -> None:
        if not raw:
            return
        slug = (raw.get("SEOUrl") or "").strip()
        title = (raw.get("Title") or "").strip()
        if not slug or not title or slug in seen_slugs:
            return
        seen_slugs.add(slug)
        created = raw.get("ScheduleTime") or raw.get("CreatedDate")
        entries.append(
            {
                "title": title,
                "seo_url": slug,
                "date": _date_from_ms(created),
            }
        )

    for doc in page_props.get("news") or []:
        _add(doc)

    featured = page_props.get("featuredNews") or {}
    _add(featured.get("HotNews"))
    for doc in featured.get("TopNews") or []:
        _add(doc)

    return entries


def _fetch_bctc_news_list(session: requests.Session, bctc_page: str, bctc_api: str) -> list[dict]:
    entries: list[dict] = []
    seen_slugs: set[str] = set()

    def _merge(batch: list[dict]) -> None:
        for entry in batch:
            slug = entry["seo_url"]
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            entries.append(entry)

    resp = session.get(bctc_page, timeout=25)
    resp.raise_for_status()
    page_data = _parse_next_data(resp.text)
    page_props = (page_data.get("props") or {}).get("pageProps") or {}
    _merge(_news_entries_from_payload(page_data))

    cate_id = (
        page_props.get("cateId")
        or source_cate_id(page_props)
        or "10111"
    )
    api_resp = session.get(
        bctc_api,
        params={"CategoryId": str(cate_id), "Lang": "vi"},
        headers={"Referer": bctc_page},
        timeout=25,
    )
    if api_resp.status_code == 400:
        print(f"    F88 BCTC API: 400 với CategoryId={cate_id}, dùng SSR")
    else:
        api_resp.raise_for_status()
        for doc in api_resp.json().get("Items") or []:
            slug = (doc.get("SEOUrl") or "").strip()
            title = (doc.get("Title") or "").strip()
            if not slug or not title:
                continue
            _merge(
                [
                    {
                        "title": title,
                        "seo_url": slug,
                        "date": _date_from_ms(doc.get("ScheduleTime") or doc.get("CreatedDate")),
                    }
                ]
            )

    if not entries:
        raise RuntimeError("F88 BCTC: không lấy được danh sách tin")

    return entries


def source_cate_id(page_props: dict) -> str | None:
    category = page_props.get("category")
    if isinstance(category, dict):
        return str(category.get("Id") or category.get("id") or "") or None
    return None


def _parse_detail_pdfs(content_html: str, fallback_title: str, date: str) -> list[dict]:
    soup = BeautifulSoup(content_html or "", "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        link = (anchor.get("href") or "").strip()
        if not link or link in seen:
            continue
        low = link.lower()
        if ".pdf" not in low and "static.f88.vn" not in low:
            continue
        seen.add(link)

        pdf_title = anchor.get_text(" ", strip=True).strip() or fallback_title
        title = pdf_title if pdf_title != fallback_title else fallback_title
        items.append(make_item(title, link, date))

    if not items and fallback_title:
        # Tin không có PDF riêng — dùng URL bài viết
        pass

    return items


def _fetch_bctc_detail(session: requests.Session, entry: dict) -> list[dict]:
    slug = entry["seo_url"]
    resp = session.get(f"{BASE}/{slug}", timeout=25)
    resp.raise_for_status()

    detail = (
        (_parse_next_data(resp.text).get("props") or {}).get("pageProps") or {}
    ).get("dataNewsDetail") or {}

    content = detail.get("Content") or ""
    title = (detail.get("Title") or entry["title"]).strip()
    date = _date_from_ms(detail.get("ScheduleTime") or detail.get("CreatedDate"))
    if not date:
        date = entry.get("date", "")

    items = _parse_detail_pdfs(content, title, date)
    if items:
        return items

    if title:
        return [make_item(title, f"{BASE}/{slug}", date)]
    return []


def _fetch_bctc(session: requests.Session, bctc_page: str, bctc_api: str) -> list[dict]:
    items: list[dict] = []
    seen_uids: set[str] = set()

    for entry in _fetch_bctc_news_list(session, bctc_page, bctc_api):
        try:
            batch = _fetch_bctc_detail(session, entry)
        except Exception as e:
            print(f"    F88 BCTC detail {entry['seo_url']}: {e}")
            continue
        for item in batch:
            if item["uid"] in seen_uids:
                continue
            seen_uids.add(item["uid"])
            items.append(item)

    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    api_url = source.get("api_url", API_URL)
    cbtt_page = source.get("source_page", CBTT_PAGE)
    bctc_page = source.get("bctc_page", BCTC_PAGE)
    bctc_api = source.get("bctc_api_url", BCTC_NEWS_API)
    categories = tuple(source.get("categories", CBTT_CATEGORIES))

    session.headers.setdefault("Origin", BASE)
    session.headers.setdefault("Referer", cbtt_page)

    items: list[dict] = []
    seen: set[str] = set()

    for category_id in categories:
        for item in _fetch_category(session, category_id, api_url):
            if item["link"] in seen:
                continue
            seen.add(item["link"])
            items.append(item)

    cbtt_count = len(items)
    session.headers["Referer"] = bctc_page
    try:
        bctc_batch = _fetch_bctc(session, bctc_page, bctc_api)
    except RuntimeError as e:
        print(f"    {e} — bỏ qua BCTC lần này")
        bctc_batch = []
    for item in bctc_batch:
        if item["link"] in seen:
            continue
        seen.add(item["link"])
        items.append(item)

    print(f"    F88 CBTT: {cbtt_count}, BCTC: {len(items) - cbtt_count}")
    return finalize_fetch(_MOD, items)
