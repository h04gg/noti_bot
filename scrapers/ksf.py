"""Scraper: Sunshine Group (KSF) — API IR."""

from __future__ import annotations

import requests

from filters import is_recent_item
from scrapers._common import date_from_iso, make_item

API_URL = "https://ir.sunshinegroup.vn/wp-json/api/v1/thong-tin-co-dong/cong-bo-thong-tin"


def fetch(source: dict, session: requests.Session) -> list[dict]:
    api_url = source.get("api_url", API_URL)
    try:
        resp = session.get(api_url, timeout=25)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        print(f"    KSF API: {e}")
        return []

    items: list[dict] = []
    for doc in payload.get("data", []):
        if doc.get("acf", {}).get("display_none"):
            continue
        title = (doc.get("name") or "").strip()
        if not title:
            continue

        link = ""
        acf = doc.get("acf", {})
        if acf.get("link_option") == "file pdf" and acf.get("list_file"):
            link = acf["list_file"][0].get("file", "")
        elif acf.get("link"):
            link = acf["link"]
        if not link:
            continue

        date = date_from_iso(doc.get("date", ""))
        item = make_item(title, link, date)
        if is_recent_item(item):
            items.append(item)
    return items
