"""
Scraper: BIDV — dữ liệu nhúng trong HTML (IBM WebSphere Portal + Angular).

Trang https://bidv.com.vn/vn/quan-he-nha-dau-tu/thong-tin-co-dong không gọi API JSON;
danh sách CBTT nằm trong các khối `var item = { ... }` trên HTML.
"""

from __future__ import annotations

import re
from html import unescape

import requests

from filters import filter_recent_items
from scrapers._common import make_item

BASE = "https://bidv.com.vn"
PAGE_URL = f"{BASE}/vn/quan-he-nha-dau-tu/thong-tin-co-dong"

_ITEM_RE = re.compile(
    r"var item = \{(?P<body>.*?)\};\s*tempData(?:TN|PT|CD)?\.push\(item\)",
    re.S,
)


def _get_field(body: str, name: str) -> str:
    patterns = (
        rf"(?:^|[\n\r])\s*{re.escape(name)}:\s*formatTitle\('((?:\\'|[^'])*)'\)",
        rf"(?:^|[\n\r])\s*{re.escape(name)}:\s*'((?:\\'|[^'])*)'",
    )
    for pattern in patterns:
        match = re.search(pattern, body, re.M)
        if match:
            return unescape(match.group(1).replace("\\'", "'"))
    return ""


def _abs_link(file_title: str, path: str) -> str:
    link = (file_title or "").strip()
    if not link:
        link = (path or "").strip()
    if not link:
        return ""
    link = unescape(link)
    if link.startswith("http"):
        return link
    if link.startswith("/"):
        return BASE + link
    return f"{BASE}/{link.lstrip('/')}"


def _parse_items(html: str) -> list[dict]:
    items: list[dict] = []
    seen_uids: set[str] = set()

    for match in _ITEM_RE.finditer(html):
        body = match.group("body")
        title = _get_field(body, "title").strip()
        date = _get_field(body, "publishdate").strip()
        link = _abs_link(_get_field(body, "file_title"), _get_field(body, "path"))

        if not title or not date or not link:
            continue
        if re.fullmatch(r"\d{4}", title):
            continue

        item = make_item(title, link, date)
        if item["uid"] in seen_uids:
            continue
        seen_uids.add(item["uid"])
        items.append(item)

    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    page_url = source.get("url", PAGE_URL)
    session.headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    )

    try:
        resp = session.get(page_url, timeout=40)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
    except Exception as e:
        print(f"    BIDV HTML: {e}")
        return []

    items = _parse_items(resp.text)
    if not items:
        print("    BIDV: không parse được tài liệu từ HTML")

    return filter_recent_items(items)
