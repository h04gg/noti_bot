"""Scraper: F88 — API nhà đầu tư (Next.js FE gọi apis.f88.vn)."""

from __future__ import annotations

from datetime import datetime

import requests

from filters import is_recent_item
from scrapers._common import make_item

API_URL = "https://apis.f88.vn/growth/f88vn/api/v1/Initial/InitPageInvestDocument"
# Các tab trên https://nhadautu.f88.vn/cong-bo-thong-tin
CATEGORIES = ("10115", "10108", "10122", "10123", "10118")


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


def _fetch_category(session: requests.Session, category_id: str, api_url: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    next_token = 0

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
            break

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
            item = make_item(title, link, date)
            if is_recent_item(item):
                items.append(item)

        if not payload.get("HasNextPage"):
            break
        next_token = payload.get("NextToken", next_token)
        if next_token == 0:
            break

    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    api_url = source.get("api_url", API_URL)
    session.headers.setdefault("Origin", "https://nhadautu.f88.vn")
    session.headers.setdefault("Referer", source.get("url", "https://nhadautu.f88.vn/cong-bo-thong-tin"))

    items: list[dict] = []
    seen: set[str] = set()
    for category_id in CATEGORIES:
        for item in _fetch_category(session, category_id, api_url):
            if item["link"] in seen:
                continue
            seen.add(item["link"])
            items.append(item)

    return items
