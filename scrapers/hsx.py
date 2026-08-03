"""Scraper: HSX — API tin tổ chức niêm yết (securitiesType/1)."""

from __future__ import annotations

import re
import sys
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from hose_watchlist import get_company
from scrapers._common import finalize_fetch, format_dmY, item_uid, make_item, page_fetch_failed

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0

API_URL = "https://api.hsx.vn/n/api/v1/1/news/securitiesType/1"
DETAIL_URL = "https://www.hsx.vn/vi/tin-tuc/{slug}/{id}"
SOURCE_PAGE = "https://www.hsx.vn/vi/tin-tuc"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PAGE_SIZE = 100
MAX_PAGES = 50
_TITLE_TICKER_RE = re.compile(r"^([A-Z0-9]{2,10})\s*:\s*(.+)$", re.DOTALL)

_VI_MAP = str.maketrans(
    {
        "à": "a",
        "á": "a",
        "ả": "a",
        "ã": "a",
        "ạ": "a",
        "ă": "a",
        "ằ": "a",
        "ắ": "a",
        "ẳ": "a",
        "ẵ": "a",
        "ặ": "a",
        "â": "a",
        "ầ": "a",
        "ấ": "a",
        "ẩ": "a",
        "ẫ": "a",
        "ậ": "a",
        "è": "e",
        "é": "e",
        "ẻ": "e",
        "ẽ": "e",
        "ẹ": "e",
        "ê": "e",
        "ề": "e",
        "ế": "e",
        "ể": "e",
        "ễ": "e",
        "ệ": "e",
        "ì": "i",
        "í": "i",
        "ỉ": "i",
        "ĩ": "i",
        "ị": "i",
        "ò": "o",
        "ó": "o",
        "ỏ": "o",
        "õ": "o",
        "ọ": "o",
        "ô": "o",
        "ồ": "o",
        "ố": "o",
        "ổ": "o",
        "ỗ": "o",
        "ộ": "o",
        "ơ": "o",
        "ờ": "o",
        "ớ": "o",
        "ở": "o",
        "ỡ": "o",
        "ợ": "o",
        "ù": "u",
        "ú": "u",
        "ủ": "u",
        "ũ": "u",
        "ụ": "u",
        "ư": "u",
        "ừ": "u",
        "ứ": "u",
        "ử": "u",
        "ữ": "u",
        "ự": "u",
        "ỳ": "y",
        "ý": "y",
        "ỷ": "y",
        "ỹ": "y",
        "ỵ": "y",
        "đ": "d",
    }
)


def _date_range() -> tuple[str, str]:
    """HSX: chỉ lấy tin từ hôm qua đến hôm nay."""
    today = datetime.now(VN_TZ).date()
    start = today - timedelta(days=1)
    return start.isoformat(), today.isoformat()


def _doc_date(posted: int | float | None) -> str:
    if not posted:
        return ""
    try:
        dt = datetime.fromtimestamp(int(posted), tz=VN_TZ)
    except (OverflowError, OSError, ValueError, TypeError):
        return ""
    return format_dmY(dt.day, dt.month, dt.year)


def _slugify(title: str) -> str:
    s = (title or "").strip().lower().translate(_VI_MAP)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "tin-tuc"


def _doc_link(doc: dict, title: str) -> str:
    link = (doc.get("link") or "").strip()
    if link.startswith("http"):
        return link
    news_id = doc.get("id")
    if news_id is None:
        return ""
    return DETAIL_URL.format(slug=_slugify(title), id=news_id)


def _extract_ticker(doc: dict, title: str) -> tuple[str, str]:
    """Trả (ticker, headline). Ticker ưu tiên field API `code`, fallback prefix tiêu đề."""
    code = (doc.get("code") or "").strip().upper()
    m = _TITLE_TICKER_RE.match(title or "")
    if m:
        prefix = m.group(1).upper()
        headline = m.group(2).strip()
        return (code or prefix), headline
    return code, (title or "").strip()


def _enrich_items(items: list[dict]) -> list[dict]:
    """Gắn meta watchlist; tin ngoài list → mục Khác (giữ mã trong tiêu đề)."""
    for item in items:
        ticker = (item.get("symbol") or "").upper()
        item["symbol"] = ticker
        company = get_company(ticker)
        if company:
            item["company"] = company["name"]
            item["sector"] = company["sector"]
            item["sector_emoji"] = company["sector_emoji"]
            item["company_emoji"] = company["emoji"]
            item["is_other"] = False
        else:
            item["company"] = ticker or "Khác"
            item["sector"] = "Khác"
            item["sector_emoji"] = "📋"
            item["company_emoji"] = "📄"
            item["is_other"] = True
            if ticker and not item["title"].upper().startswith(f"{ticker}:"):
                item["title"] = f"{ticker}: {item['title']}"
    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    api_url = source.get("api_url", API_URL)
    page_size = int(source.get("params", {}).get("pageSize", PAGE_SIZE))
    start_date, end_date = _date_range()
    referer = source.get("source_page", SOURCE_PAGE)

    all_items: list[dict] = []
    seen: set[str] = set()
    page = 1
    total_pages = 1

    while page <= max(total_pages, 1) and page <= MAX_PAGES:
        try:
            resp = session.get(
                api_url,
                params={
                    "pageIndex": page,
                    "pageSize": page_size,
                    "startDate": start_date,
                    "endDate": end_date,
                },
                timeout=30,
                headers={
                    "Accept": "application/json",
                    "Accept-Language": "vi-VN,vi;q=0.9",
                    "Referer": referer,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            page_fetch_failed(page, e, "HSX")
            break

        if not payload.get("success", True):
            raise RuntimeError(f"HSX API: {payload.get('message') or 'success=false'}")

        block = payload.get("data") or {}
        docs = block.get("list") or []
        paging = block.get("paging") or {}
        total_pages = int(paging.get("totalPages") or 1)

        if not docs:
            break

        added = 0
        for doc in docs:
            raw_title = (doc.get("title") or "").strip()
            ticker, headline = _extract_ticker(doc, raw_title)
            title = headline or raw_title
            link = _doc_link(doc, raw_title)
            news_id = doc.get("id")
            if not title or not link or news_id is None:
                continue
            item = make_item(title, link, _doc_date(doc.get("postedDate")))
            # UID theo id tin — không đổi khi sửa format URL
            item["uid"] = item_uid(f"hsx-news:{news_id}")
            item["symbol"] = ticker
            if item["uid"] in seen:
                continue
            seen.add(item["uid"])
            all_items.append(item)
            added += 1

        print(f"    HSX page {page}/{total_pages}: +{added} (start={start_date}, end={end_date})")

        if page >= total_pages:
            break
        page += 1

    if not all_items:
        raise RuntimeError("HSX: không lấy được tin (API rỗng hoặc lỗi)")

    enriched = _enrich_items(all_items)
    watched = sum(1 for it in enriched if not it.get("is_other"))
    print(
        f"    HSX tổng: {len(enriched)} tin ({start_date} → {end_date}); "
        f"watchlist: {watched}, khác: {len(enriched) - watched}"
    )
    return finalize_fetch(_MOD, enriched)
