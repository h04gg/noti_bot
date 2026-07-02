"""
Scraper: HDBank — API investor (response AES, giống FE Next.js).

Trang CBTT không có JSON công khai; FE gọi:
  GET /api/vi/investors/{slug_type}/{slug_category}/{slug_detail}
Header bắt buộc: local=vi (không phải cookie).
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from scrapers._common import extract_dmY, format_dmY, make_item

BASE = "https://hdbank.com.vn"
API_BASE = f"{BASE}/api"
_AES_KEY = b"Z9GRKIgYKH2CUdqfas858Q=="
_FILENAME_DATE_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})")


def _decrypt_payload(raw: str) -> dict | list:
    text = raw.strip()
    pad = (-len(text)) % 4
    if pad:
        text += "=" * pad
    plain = unpad(AES.new(_AES_KEY, AES.MODE_ECB).decrypt(base64.b64decode(text)), 16)
    return json.loads(plain.decode("utf-8"))


def _date_from_link(link: str, title: str) -> str:
    m = _FILENAME_DATE_RE.search(link)
    if m:
        return format_dmY(m.group(3), m.group(2), m.group(1))
    return extract_dmY(title)


def _parse_menu_html(html: str) -> list[dict]:
    items: list[dict] = []
    seen_links: set[str] = set()
    soup = BeautifulSoup(html or "", "html.parser")

    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href or ".pdf" not in href.lower():
            continue
        if not href.startswith("http"):
            href = BASE + href if href.startswith("/") else f"{BASE}/{href.lstrip('/')}"
        if href in seen_links:
            continue

        title = a.get_text(" ", strip=True)
        if not title or len(title) < 8:
            continue

        seen_links.add(href)
        items.append(make_item(title, href, _date_from_link(href, title)))

    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    api_path = source.get(
        "api_path",
        "/vi/investors/thong-tin-nha-dau-tu/quan-he-co-dong/cong-bo-thong-tin-thong-tin-khac",
    )
    page_url = source.get(
        "source_page",
        f"{BASE}/vi/investor/thong-tin-nha-dau-tu/quan-he-co-dong/cong-bo-thong-tin-thong-tin-khac",
    )

    session.headers.setdefault("Accept", "application/json")
    session.headers.setdefault("Content-Type", "application/json")
    session.headers.setdefault("local", "vi")
    session.headers.setdefault("Origin", BASE)
    session.headers.setdefault("Referer", page_url)

    try:
        resp = session.get(f"{API_BASE}{api_path}", timeout=30)
        resp.raise_for_status()
        payload = _decrypt_payload(resp.text)
    except Exception as e:
        print(f"    HDBank API: {e}")
        return []

    menu = payload.get("menuList") if isinstance(payload, dict) else None
    if not menu:
        print("    HDBank: menuList rỗng")
        return []

    min_year = datetime.now().year - 1
    items: list[dict] = []
    seen_uids: set[str] = set()

    for section in menu:
        year_label = (section.get("name") or "").strip()
        if year_label.isdigit() and int(year_label) < min_year:
            continue

        for item in _parse_menu_html(section.get("content") or ""):
            if item["uid"] in seen_uids:
                continue
            seen_uids.add(item["uid"])
            items.append(item)

    return items
