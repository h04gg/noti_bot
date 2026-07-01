"""Scraper: VPS Securities (VCK) — Next.js SSR."""

from __future__ import annotations

import re
import time

import requests
from requests.exceptions import RequestException

from scrapers._common import extract_dmY, make_item, paginate_until_recent

BASE = "https://www.vps.com.vn"
VCK_TIMEOUT = (20, 50)  # (connect, read) — VPS đôi khi chậm từ GHA
VCK_RETRIES = 3
VCK_RETRY_DELAY = 5


def _get_page(
    session: requests.Session,
    url: str,
    params: dict,
    page: int,
) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, VCK_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=VCK_TIMEOUT, verify=False)
            resp.raise_for_status()
            return resp
        except RequestException as e:
            last_error = e
            if attempt < VCK_RETRIES:
                print(
                    f"    VCK page {page}: lỗi lần {attempt}/{VCK_RETRIES}"
                    f" — thử lại sau {VCK_RETRY_DELAY}s"
                )
                time.sleep(VCK_RETRY_DELAY)
    raise RuntimeError(f"VCK page {page}: {last_error}") from last_error


def fetch(source: dict, session: requests.Session) -> list[dict]:
    base_url = source.get("url", f"{BASE}/quan-he-co-dong/cong-bo-thong-tin")
    session.headers.setdefault("Referer", f"{BASE}/quan-he-co-dong/cong-bo-thong-tin")

    def _page(page: int) -> list[dict]:
        from datetime import datetime

        year = datetime.now().year
        params = {"year": year, "page": page}
        try:
            resp = _get_page(session, base_url, params, page)
        except RuntimeError as e:
            print(f"    {e}")
            if page == 1:
                raise
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
