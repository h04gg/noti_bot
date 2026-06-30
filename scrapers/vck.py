"""Scraper: VPS Securities (VCK) — Next.js SSR."""

from __future__ import annotations

import re
import requests

from scrapers._common import extract_dmY, make_item, paginate_until_recent

BASE = "https://www.vps.com.vn"


def fetch(source: dict, session: requests.Session) -> list[dict]:
    base_url = source.get("url", f"{BASE}/quan-he-co-dong/cong-bo-thong-tin")

    def _page(page: int) -> list[dict]:
        from datetime import datetime

        year = datetime.now().year
        params = {"year": year, "page": page}
        try:
            resp = session.get(base_url, params=params, timeout=25, verify=False)
            resp.raise_for_status()
        except Exception as e:
            print(f"    VCK page {page}: {e}")
            return []

        items: list[dict] = []
        seen: set[str] = set()
        for m in re.finditer(
            r'href="(/bai-viet/[^"]+)"[^>]*>\s*<span[^>]*>([^<]+)</span>\s*'
            r'<span[^>]*>(\d{1,2}/\d{1,2}/\d{4})</span>',
            resp.text,
            re.S,
        ):
            path, title, date_raw = m.group(1), m.group(2).strip(), m.group(3)
            link = BASE + path
            if link in seen:
                continue
            seen.add(link)
            items.append(make_item(title, link, extract_dmY(date_raw)))
        return items

    return paginate_until_recent(_page)
