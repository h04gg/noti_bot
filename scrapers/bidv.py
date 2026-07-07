"""
Scraper: BIDV — dữ liệu nhúng trong HTML (IBM WebSphere Portal + Angular).

Trang https://bidv.com.vn/vn/quan-he-nha-dau-tu/thong-tin-co-dong không gọi API JSON;
danh sách CBTT nằm trong các khối `var item = { ... }` trên HTML.
"""

from __future__ import annotations

import re
import sys
from html import unescape

import requests

from scrapers._common import finalize_fetch, make_item

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0

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
    feeds = source.get("feeds") or [
        {
            "url": source.get("url", PAGE_URL),
            "label": "CBTT",
        }
    ]
    session.headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    )

    merged: list[dict] = []
    seen_uids: set[str] = set()
    counts: list[str] = []

    for i, feed in enumerate(feeds):
        page_url = feed["url"]
        label = feed.get("label", "feed")
        try:
            resp = session.get(page_url, timeout=40)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
        except Exception as e:
            print(f"    BIDV {label}: {e}")
            if i == 0:
                raise RuntimeError(f"BIDV {label}: {e}") from e
            continue

        batch = _parse_items(resp.text)
        if not batch and i == 0:
            print(f"    BIDV {label}: không parse được tài liệu từ HTML")
            raise RuntimeError(f"BIDV {label}: không parse được tài liệu từ HTML")

        counts.append(f"{label}: {len(batch)}")
        for item in batch:
            if item["uid"] in seen_uids:
                continue
            seen_uids.add(item["uid"])
            merged.append(item)

    if counts:
        print(f"    BIDV {', '.join(counts)}")
    return finalize_fetch(_MOD, merged, filter_recent=True)
