"""Scraper: HSX — API tin tổ chức niêm yết (securitiesType/1)."""

from __future__ import annotations

import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from curl_cffi import requests as curl_requests

from hose_watchlist import get_company
from scrapers._common import (
    CURL_RETRIES,
    CURL_RETRY_DELAY,
    IMPERSONATE_PROFILES,
    finalize_fetch,
    format_dmY,
    item_uid,
    make_item,
    page_fetch_failed,
)

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


def _api_get_json(
    api_url: str,
    *,
    params: dict,
    headers: dict,
) -> dict:
    """GET JSON — ưu tiên curl_cffi (GHA thường bị HSX chặn requests thường)."""
    last_error: Exception | None = None
    for attempt in range(1, CURL_RETRIES + 1):
        profile = IMPERSONATE_PROFILES[(attempt - 1) % len(IMPERSONATE_PROFILES)]
        session = curl_requests.Session(impersonate=profile)
        try:
            resp = session.get(
                api_url,
                params=params,
                headers=headers,
                timeout=30,
            )
            status = resp.status_code
            text = resp.text or ""
            if status == 403:
                raise RuntimeError("HTTP 403 Forbidden (có thể chặn IP GHA)")
            if status >= 400:
                raise RuntimeError(f"HTTP {status}: {text[:180]}")
            try:
                payload = resp.json()
            except Exception as e:
                raise RuntimeError(
                    f"HSX JSON không hợp lệ (HTTP {status}): {text[:180]}"
                ) from e
            return payload
        except Exception as e:
            last_error = e
            if attempt < CURL_RETRIES:
                print(
                    f"    HSX curl {profile} lần {attempt}/{CURL_RETRIES}: {e}"
                    f" — thử lại sau {CURL_RETRY_DELAY}s"
                )
                time.sleep(CURL_RETRY_DELAY)
        finally:
            session.close()

    # Fallback requests thường (môi trường local)
    try:
        resp = requests.get(api_url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"HSX API thất bại: {last_error or e}") from e


def fetch(source: dict, session: requests.Session) -> list[dict]:
    api_url = source.get("api_url", API_URL)
    page_size = int(source.get("params", {}).get("pageSize", PAGE_SIZE))
    start_date, end_date = _date_range()
    referer = source.get("source_page", SOURCE_PAGE)
    headers = {
        "Accept": "application/json",
        "Accept-Language": "vi-VN,vi;q=0.9",
        "Referer": referer,
        "Origin": "https://www.hsx.vn",
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
    }

    all_items: list[dict] = []
    seen: set[str] = set()
    page = 1
    total_pages = 1
    last_page_error: Exception | None = None

    while page <= max(total_pages, 1) and page <= MAX_PAGES:
        try:
            payload = _api_get_json(
                api_url,
                params={
                    "pageIndex": page,
                    "pageSize": page_size,
                    "startDate": start_date,
                    "endDate": end_date,
                },
                headers=headers,
            )
        except Exception as e:
            last_page_error = e
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
        if last_page_error:
            raise RuntimeError(f"HSX: {last_page_error}") from last_page_error
        # Cửa sổ hôm qua→hôm nay có thể thật sự trống — không coi là lỗi cứng
        print(f"    HSX: 0 tin trong cửa sổ {start_date} → {end_date}")
        return finalize_fetch(_MOD, [])

    enriched = _enrich_items(all_items)
    watched = sum(1 for it in enriched if not it.get("is_other"))
    print(
        f"    HSX tổng: {len(enriched)} tin ({start_date} → {end_date}); "
        f"watchlist: {watched}, khác: {len(enriched) - watched}"
    )
    return finalize_fetch(_MOD, enriched)
