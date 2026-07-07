"""
Scraper: Eximbank — /thong-tin-khac (Next.js RSC payload)
Trang dùng React Server Components; danh sách CBTT nằm trong payload
self.__next_f.push, không có link PDF trong thẻ <a>.
"""

from __future__ import annotations

import re
import sys

import requests

from scrapers._common import date_from_iso, finalize_fetch, make_item

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0

PAGE_URL = "https://eximbank.com.vn/thong-tin-khac"

_BLOCK_RE = re.compile(
    r'\\"type\\":\\"thong-tin-khac\\"(?P<body>.{0,5000}?)'
    r'\\"created_at\\":\\"(?P<created>[^\\]+)\\"',
    re.S,
)
_TITLE_RE = re.compile(r'\\"title\\":\\"([^\\]+)\\"')
_PATH_RE = re.compile(r'\\"path\\":\\"(https://media\.eximbank\.com\.vn[^\\]+)\\"')
_FILENAME_DATE_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})")


def _date_from_doc(created: str, link: str) -> str:
    date = date_from_iso(created)
    if date:
        return date
    m = _FILENAME_DATE_RE.search(link)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    return ""


def _parse_payload(payload: str) -> list[dict]:
    items: list[dict] = []
    seen_links: set[str] = set()

    for block in _BLOCK_RE.finditer(payload):
        body = block.group("body")
        title_m = _TITLE_RE.search(body)
        path_m = _PATH_RE.search(body)
        if not title_m or not path_m:
            continue

        title = title_m.group(1).strip()
        link = path_m.group(1).strip()
        if not title or not link or link in seen_links:
            continue
        if len(title) < 15 or title.startswith(("Năm ", "Thông báo năm")):
            continue

        seen_links.add(link)
        date = _date_from_doc(block.group("created"), link)
        items.append(make_item(title, link, date))

    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    page_url = source.get("url") or PAGE_URL
    try:
        resp = session.get(page_url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"    Eximbank RSC: {e}")
        raise RuntimeError(f"Eximbank RSC: {e}") from e

    chunks = re.findall(
        r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)', resp.text
    )
    if not chunks:
        print("    Eximbank: không tìm thấy Next.js payload")
        raise RuntimeError("Eximbank: không tìm thấy Next.js payload")

    payload = max(chunks, key=len)
    items = _parse_payload(payload)
    if not items:
        print("    Eximbank: payload có nhưng không parse được tài liệu")
        raise RuntimeError("Eximbank: không parse được tài liệu từ payload")

    return finalize_fetch(_MOD, items)
