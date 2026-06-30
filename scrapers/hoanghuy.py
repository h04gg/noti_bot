"""
Scraper: Hoàng Huy — HTML trang Quan hệ cổ đông
URL: https://www.hoanghuy.vn/quan-he-co-dong/
"""

import re
import hashlib
import requests
from bs4 import BeautifulSoup


BASE = "https://www.hoanghuy.vn"


def fetch(source: dict, session: requests.Session) -> list[dict]:
    page_url = source.get("url", f"{BASE}/quan-he-co-dong/")
    try:
        resp = session.get(page_url, timeout=20)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
    except Exception as e:
        print(f"    Hoanghuy HTML: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    seen_links: set[str] = set()

    for a in soup.select("a[href]"):
        title = a.get_text(" ", strip=True).strip()
        if not title.startswith("TCH:"):
            continue

        link = a.get("href", "").strip()
        if not link or link in seen_links:
            continue
        if not link.startswith("http"):
            link = BASE + link
        seen_links.add(link)

        date = _extract_date(a)
        uid = hashlib.md5(link.encode()).hexdigest()[:12]
        items.append({"uid": uid, "title": title, "link": link, "date": date})

    return items


def _extract_date(anchor) -> str:
    parent = anchor.parent
    for _ in range(5):
        if not parent:
            break
        m = re.search(r"Cập nhật:\s*(\d{1,2}/\d{1,2}/\d{4})", parent.get_text(" ", strip=True))
        if m:
            parts = m.group(1).split("/")
            return f"{int(parts[0]):02d}/{int(parts[1]):02d}/{parts[2]}"
        parent = parent.parent
    return ""
