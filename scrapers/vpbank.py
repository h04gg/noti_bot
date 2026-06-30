"""
Scraper: VPBank — JSON API
API: /uiux-api/api/document?lang=vi&categoryPath=...&pageSize=...&pageIndex=...
"""

import re
import hashlib
import requests
from datetime import datetime

from config import RECENT_DAYS
from filters import filter_recent_items, newest_item_date, recent_cutoff


def fetch(source: dict, session: requests.Session) -> list[dict]:
    url = source["url"]
    params = dict(source.get("params", {}))
    page_size = int(params.get("pageSize", 4))
    page_index = int(params.pop("pageIndex", 1))

    category_path = params.get("categoryPath", "")
    if category_path:
        year = str(datetime.now().year)
        params["categoryPath"] = re.sub(r"/\d{4}$", f"/{year}", category_path)

    all_items: list[dict] = []
    while True:
        params["pageIndex"] = page_index
        items, total = _fetch_page(session, url, params)
        all_items.extend(items)

        if not items or page_index * page_size >= total:
            break

        page_newest = newest_item_date(items)
        if page_newest and page_newest < recent_cutoff(RECENT_DAYS):
            break

        page_index += 1

    return filter_recent_items(all_items)


def _fetch_page(
    session: requests.Session, url: str, params: dict
) -> tuple[list[dict], int]:
    try:
        resp = session.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    VPBank page {params.get('pageIndex', 1)}: {e}")
        return [], 0

    items = []
    for doc in data.get("data", []):
        title = doc.get("title", "").strip()
        publish_date = doc.get("publishDate", "")
        path = doc.get("path", "")
        link = f"https://www.vpbank.com.vn{path}" if path else ""

        item_list = doc.get("itemList", [])
        if item_list:
            pdf_url = item_list[0].get("url", "")
            if pdf_url:
                if pdf_url.startswith("/"):
                    pdf_url = "https://www.vpbank.com.vn" + pdf_url
                link = pdf_url

        if not title or not link:
            continue

        date = ""
        if publish_date:
            try:
                dt = datetime.fromisoformat(publish_date.replace("Z", "+00:00"))
                date = dt.strftime("%d/%m/%Y")
            except Exception:
                date = publish_date[:10]

        uid = hashlib.md5(link.encode()).hexdigest()[:12]
        items.append({"uid": uid, "title": title, "link": link, "date": date})

    return items, int(data.get("total", 0))
