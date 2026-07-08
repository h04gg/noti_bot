"""Scraper: Sunshine Group (KSF) — IR JSON API (CBTT + BCTC)."""

from __future__ import annotations

import html
import os
import sys
import time
from datetime import datetime

from curl_cffi import requests as curl_requests

from filters import parse_item_date
from scrapers._common import date_from_iso, finalize_fetch, make_item

_MOD = sys.modules[__name__]

IR_BASE = "https://ir.sunshinegroup.vn"
CBTT_API = f"{IR_BASE}/wp-json/api/v1/thong-tin-co-dong/cong-bo-thong-tin"
BCTC_API = f"{IR_BASE}/wp-json/api/v1/thong-tin-co-dong/bao-cao-tai-chinh"
CBTT_PAGE = "https://sunshinegroup.vn/cong-bo-thong-tin/"
BCTC_PAGE = "https://sunshinegroup.vn/bao-cao-tai-chinh/"
IMPERSONATE_PROFILES = ("chrome124", "chrome120", "safari17_0", "edge101")
KSF_TIMEOUT = 45
KSF_RETRIES = 3
KSF_RETRY_DELAY = 5
LAST_RAW_COUNT = 0


def _proxy() -> dict[str, str] | None:
    raw = (os.environ.get("KSF_HTTP_PROXY") or os.environ.get("HTTP_PROXY") or "").strip()
    if not raw:
        return None
    return {"http": raw, "https": raw}


def _api_headers(referer: str) -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": referer,
    }


def _get_api_payload(api_url: str, referer: str, label: str) -> dict:
    proxies = _proxy()
    last_error: Exception | None = None

    for attempt in range(1, KSF_RETRIES + 1):
        profile = IMPERSONATE_PROFILES[(attempt - 1) % len(IMPERSONATE_PROFILES)]
        session = curl_requests.Session(impersonate=profile)
        try:
            resp = session.get(
                api_url,
                headers=_api_headers(referer),
                timeout=KSF_TIMEOUT,
                proxies=proxies,
            )
            if resp.status_code == 403:
                raise RuntimeError("HTTP 403 Forbidden")
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict) or "data" not in payload:
                raise RuntimeError("API payload không hợp lệ")
            return payload
        except Exception as e:
            last_error = e
            if attempt < KSF_RETRIES:
                print(
                    f"    KSF {profile} {label}: lỗi lần {attempt}/{KSF_RETRIES}: {e}"
                    f" — thử lại sau {KSF_RETRY_DELAY}s"
                )
                time.sleep(KSF_RETRY_DELAY)
        finally:
            session.close()

    raise RuntimeError(f"KSF {label}: {last_error}") from last_error


def _doc_link(acf: dict) -> str:
    if acf.get("not_show_link"):
        return ""
    if acf.get("link_option") == "file pdf" and acf.get("list_file"):
        files = acf.get("list_file") or []
        if files:
            return (files[0].get("file") or "").strip()
    link = (acf.get("link") or "").strip()
    if link and link not in {"#", ""}:
        return link
    return ""


def _is_current_year(date_str: str, year: int) -> bool:
    dt = parse_item_date(date_from_iso(date_str))
    if dt is None:
        return True
    return dt.year >= year - 1


def _parse_docs(payload: dict, year: int) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()

    for doc in payload.get("data") or []:
        acf = doc.get("acf") or {}
        if acf.get("display_none"):
            continue

        raw_date = doc.get("date", "")
        if not _is_current_year(raw_date, year):
            continue

        title = html.unescape((doc.get("name") or "").strip())
        if not title:
            continue

        link = _doc_link(acf)
        if not link:
            continue

        date = date_from_iso(raw_date)
        item = make_item(title, link, date)
        if item["uid"] in seen:
            continue
        seen.add(item["uid"])
        items.append(item)

    return items


def _fetch_feed(api_url: str, referer: str, label: str, year: int) -> list[dict]:
    payload = _get_api_payload(api_url, referer, label)
    docs = payload.get("data") or []
    if not docs:
        raise RuntimeError(f"KSF {label}: API trả về 0 bản ghi")
    return _parse_docs(payload, year)


def fetch(source: dict, session) -> list[dict]:
    year = datetime.now().year
    cbtt_api = source.get("api_url", CBTT_API)
    bctc_api = source.get("bctc_api_url", BCTC_API)
    cbtt_page = source.get("source_page", CBTT_PAGE)
    bctc_page = source.get("bctc_page", BCTC_PAGE)

    merged: list[dict] = []
    seen: set[str] = set()

    cbtt_items = _fetch_feed(cbtt_api, cbtt_page, "CBTT", year)
    for item in cbtt_items:
        if item["uid"] not in seen:
            seen.add(item["uid"])
            merged.append(item)

    bctc_items = _fetch_feed(bctc_api, bctc_page, "BCTC", year)
    for item in bctc_items:
        if item["uid"] not in seen:
            seen.add(item["uid"])
            merged.append(item)

    print(f"    KSF CBTT: {len(cbtt_items)}, BCTC: {len(bctc_items)} (năm {year})")
    return finalize_fetch(_MOD, merged)
