"""
Scraper: Eximbank — Next.js / ISR

Eximbank dùng Next.js. Trang /thong-tin-khac hiện tại "Chưa có mục nào"
(trang mới, chưa có data), nhưng các trang IR khác có data.

Strategy:
1. Thử Next.js _next/data JSON endpoint (build-id cần lấy động)
2. Fetch HTML page với requests, parse nội dung
3. Nếu vẫn trống → Playwright headless

Lưu ý: Eximbank IR hiện tại có vẻ chưa có tài liệu ở /thong-tin-khac.
Vẫn monitor để bắt khi có tin mới.
"""

import re
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime


PAGE_URL = "https://eximbank.com.vn/thong-tin-khac"
BASE = "https://eximbank.com.vn"


def fetch(source: dict, session: requests.Session) -> list[dict]:
    # Strategy 1: Thử fetch HTML (Next.js ISR thường pre-render)
    items = _fetch_html(session)
    if items:
        return items

    # Strategy 2: Thử _next/data endpoint
    items = _fetch_nextjs_data(session)
    return items


def _fetch_html(session: requests.Session) -> list[dict]:
    try:
        resp = session.get(PAGE_URL, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        items = []
        # Tìm link PDF hoặc tài liệu
        for a in soup.select("a[href*='.pdf'], a[href*='/nha-dau-tu/']"):
            title = a.get_text(" ", strip=True).strip()
            link = a.get("href", "").strip()
            if not title or not link or len(title) < 10:
                continue
            if not link.startswith("http"):
                link = BASE + link

            date = ""
            parent = a.parent
            if parent:
                m = re.search(r"\d{1,2}/\d{1,2}/\d{4}", parent.get_text())
                if m:
                    date = m.group(0)

            uid = hashlib.md5(link.encode()).hexdigest()[:12]
            items.append({"uid": uid, "title": title, "link": link, "date": date})

        return items
    except Exception as e:
        print(f"    Eximbank HTML: {e}")
        return []


def _fetch_nextjs_data(session: requests.Session) -> list[dict]:
    """Lấy build ID từ HTML rồi gọi _next/data endpoint."""
    try:
        resp = session.get(PAGE_URL, timeout=20)
        resp.raise_for_status()

        # Tìm build ID trong __NEXT_DATA__
        m = re.search(r'"buildId":"([^"]+)"', resp.text)
        if not m:
            return []
        build_id = m.group(1)

        # Thử các path pattern phổ biến của Next.js
        data_url = f"{BASE}/_next/data/{build_id}/thong-tin-khac.json"
        data_resp = session.get(data_url, timeout=15)
        if not data_resp.ok:
            return []

        data = data_resp.json()
        # Parse tùy cấu trúc data của Eximbank
        page_props = data.get("pageProps", {})
        documents = (
            page_props.get("documents")
            or page_props.get("data")
            or page_props.get("items")
            or []
        )

        items = []
        for doc in documents:
            title = doc.get("title") or doc.get("name") or ""
            link = doc.get("url") or doc.get("link") or doc.get("file") or ""
            raw_date = doc.get("date") or doc.get("publishDate") or ""

            if not title or not link:
                continue
            if not link.startswith("http"):
                link = BASE + link

            date = ""
            if raw_date:
                try:
                    dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                    date = dt.strftime("%d/%m/%Y")
                except Exception:
                    date = raw_date[:10]

            uid = hashlib.md5(link.encode()).hexdigest()[:12]
            items.append({"uid": uid, "title": title, "link": link, "date": date})

        return items

    except Exception as e:
        print(f"    Eximbank _next/data: {e}")
        return []
