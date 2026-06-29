"""
Scraper: VPBank — JSON API ẩn
API: /uiux-api/api/document?lang=vi&categoryPath=...&pageSize=20&pageIndex=1

categoryPath theo năm: /quan-he-nha-dau-tu/cong-bo-thong-tin-khac/2026
Để lấy tất cả năm, cần fetch từng năm hoặc dùng path không có năm.
"""

import hashlib
import requests
from datetime import datetime


BASE_URL = "https://www.vpbank.com.vn/uiux-api/api/document"
CATEGORY_BASE = "/quan-he-nha-dau-tu/cong-bo-thong-tin-khac"


def fetch(source: dict, session: requests.Session) -> list[dict]:
    year = datetime.now().year
    # Fetch năm hiện tại (và năm trước nếu muốn bắt chéo)
    all_items = []
    for y in [year, year - 1]:
        items = _fetch_year(session, y)
        all_items.extend(items)
        if len(items) == 0:
            break  # năm trước không có thì thôi

    return all_items


def _fetch_year(session: requests.Session, year: int) -> list[dict]:
    params = {
        "lang": "vi",
        "categoryPath": f"{CATEGORY_BASE}/{year}",
        "pageSize": 50,
        "pageIndex": 1,
    }
    try:
        resp = session.get(BASE_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    VPBank {year}: {e}")
        return []

    items = []
    for doc in data.get("data", []):
        title = doc.get("title", "").strip()
        publish_date = doc.get("publishDate", "")
        path = doc.get("path", "")
        link = f"https://www.vpbank.com.vn{path}" if path else ""

        # Lấy link PDF đầu tiên trong itemList nếu có
        item_list = doc.get("itemList", [])
        if item_list:
            pdf_url = item_list[0].get("url", "")
            if pdf_url:
                if pdf_url.startswith("/"):
                    pdf_url = "https://www.vpbank.com.vn" + pdf_url
                link = pdf_url  # Prefer PDF link

        if not title or not link:
            continue

        # Format ngày: "2026-06-25T16:00:00+07:00" → "25/06/2026"
        date = ""
        if publish_date:
            try:
                dt = datetime.fromisoformat(publish_date.replace("Z", "+00:00"))
                date = dt.strftime("%d/%m/%Y")
            except Exception:
                date = publish_date[:10]

        uid = hashlib.md5(link.encode()).hexdigest()[:12]
        items.append({"uid": uid, "title": title, "link": link, "date": date})

    return items
