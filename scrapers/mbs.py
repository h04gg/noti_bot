"""Scraper: MB Securities (MBS)."""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from scrapers._common import extract_dmY, make_item, paginate_until_recent

BASE = "https://www.mbs.com.vn"


def fetch(source: dict, session: requests.Session) -> list[dict]:
    page_url = source.get("url", f"{BASE}/cong-bo-thong-tin/")
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        }
    )

    def _page(page: int) -> list[dict]:
        params = {"page": page} if page > 1 else None
        try:
            resp = session.get(page_url, params=params, timeout=25, verify=False)
            if resp.status_code == 403:
                print("    MBS: bị chặn bot (403)")
                return []
            resp.raise_for_status()
        except Exception as e:
            print(f"    MBS page {page}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items: list[dict] = []
        seen: set[str] = set()

        for a in soup.select("a[href*='cong-bo-thong-tin'], a[href*='tin-co-dong'], a[href*='.pdf']"):
            title = a.get_text(" ", strip=True)
            link = a.get("href", "").strip()
            if not title or len(title) < 15 or not link:
                continue
            if not link.startswith("http"):
                link = BASE + link
            if link in seen:
                continue
            seen.add(link)
            parent = a.parent
            date = extract_dmY(parent.get_text(" ", strip=True) if parent else "")
            if not date:
                dm = re.search(r"(20\d{6})", link)
                if dm:
                    s = dm.group(1)
                    date = f"{s[6:8]}/{s[4:6]}/{s[0:4]}"
            items.append(make_item(title, link, date))
        return items

    return paginate_until_recent(_page)
