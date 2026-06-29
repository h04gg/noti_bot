"""
Scraper: Eximbank — /thong-tin-khac (Next.js RSC payload)
Trang dùng React Server Components; danh sách CBTT nằm trong payload
self.__next_f.push, không có link PDF trong thẻ <a> như Gelex.
"""

import re
import hashlib
import requests
from datetime import datetime


PAGE_URL = "https://eximbank.com.vn/thong-tin-khac"

_DOC_PATTERN = re.compile(
    r'\\"title\\":\\"([^\\]+)\\",\\"type\\":\\"thong-tin-khac\\".{0,3000}?'
    r'\\"featured_image\\":\{[^}]*?\\"path\\":\\"(https://media\.eximbank\.com\.vn[^\\]+)\\"'
    r'.{0,800}?\\"created_at\\":\\"([^\\]+)\\"',
    re.S,
)


def fetch(source: dict, session: requests.Session) -> list[dict]:
    page_url = source.get("url") or PAGE_URL
    try:
        resp = session.get(page_url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"    Eximbank RSC: {e}")
        return []

    chunks = re.findall(
        r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)', resp.text
    )
    if not chunks:
        print("    Eximbank: không tìm thấy Next.js payload")
        return []

    payload = max(chunks, key=len)
    items = []
    seen_links: set[str] = set()

    for match in _DOC_PATTERN.finditer(payload):
        title = match.group(1).strip()
        link = match.group(2).strip()
        created = match.group(3).strip()

        if not title or not link or link in seen_links:
            continue
        if len(title) < 15 or title.startswith(("Năm ", "Thông báo năm")):
            continue

        seen_links.add(link)
        date = _format_date(created)
        uid = hashlib.md5(link.encode()).hexdigest()[:12]
        items.append({"uid": uid, "title": title, "link": link, "date": date})

    if not items:
        print("    Eximbank: payload có nhưng không parse được tài liệu")

    return items


def _format_date(raw: str) -> str:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except Exception:
        return raw[:10]
