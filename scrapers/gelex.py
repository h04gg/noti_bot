"""
Scraper: Gelex — HTML (trang công bố thông tin)
WP REST API /wp/v2/doc trả 404; lấy PDF từ trang doc-cat.
"""

import re
import sys

import requests
import urllib3
from bs4 import BeautifulSoup

from scrapers._common import finalize_fetch, make_item

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0


def fetch(source: dict, session: requests.Session) -> list[dict]:
    page_url = source.get("source_page", "https://gelex.vn/doc-cat/cong-bo-thong-tin-2")
    try:
        # gelex.vn có lỗi chuỗi chứng chỉ trên một số môi trường (GitHub Actions)
        resp = session.get(page_url, timeout=20, verify=False)
        resp.raise_for_status()
    except Exception as e:
        print(f"    Gelex HTML: {e}")
        raise RuntimeError(f"Gelex HTML: {e}") from e

    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    seen_links: set[str] = set()

    for a in soup.select("a[href*='wp-content/uploads']"):
        link = a.get("href", "").strip()
        if not link or link in seen_links:
            continue
        seen_links.add(link)

        title = a.get_text(" ", strip=True).strip()
        if not title:
            parent = a.find_parent("div")
            if parent:
                title = parent.get_text("\n", strip=True).split("\n")[0].strip()
        if not title or len(title) < 5:
            continue

        date = _date_from_url(link)
        items.append(make_item(title, link, date))

    return finalize_fetch(_MOD, items)


def _date_from_url(link: str) -> str:
    m = re.search(r"/(20\d{2})(\d{2})(\d{2})-", link)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    return ""
