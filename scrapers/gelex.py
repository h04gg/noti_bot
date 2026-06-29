"""
Scraper: Gelex — WordPress REST API (custom post type 'doc')
URL: /wp-json/wp/v2/doc?doc-cat=cong-bo-thong-tin-2&per_page=20

robots.txt chặn scraping HTML nhưng WP REST API thường vẫn accessible.
Nếu bị block, fallback về HTML scraping với Playwright.

Cách xác định category ID:
  GET https://gelex.vn/wp-json/wp/v2/doc-cat?slug=cong-bo-thong-tin-2
  → lấy trường "id"
"""

import hashlib
import requests
from datetime import datetime


WP_API_BASE = "https://gelex.vn/wp-json/wp/v2"
DOC_CAT_SLUG = "cong-bo-thong-tin-2"


def fetch(source: dict, session: requests.Session) -> list[dict]:
    # Bước 1: Lấy category ID từ slug
    cat_id = _get_category_id(session)
    if cat_id is None:
        print("    Gelex: không lấy được category ID, bỏ qua")
        return []

    # Bước 2: Lấy danh sách documents
    params = {
        "doc-cat": cat_id,
        "per_page": 50,
        "page": 1,
        "orderby": "date",
        "order": "desc",
        "_fields": "id,title,date,link,slug",
    }
    try:
        resp = session.get(f"{WP_API_BASE}/doc", params=params, timeout=20)
        resp.raise_for_status()
        posts = resp.json()
    except Exception as e:
        print(f"    Gelex WP API /doc: {e}")
        return []

    items = []
    for post in posts:
        title_raw = post.get("title", {})
        title = title_raw.get("rendered", "") if isinstance(title_raw, dict) else str(title_raw)
        title = title.strip()
        link = post.get("link", "").strip()
        raw_date = post.get("date", "")

        if not title or not link:
            continue

        date = ""
        if raw_date:
            try:
                dt = datetime.fromisoformat(raw_date)
                date = dt.strftime("%d/%m/%Y")
            except Exception:
                date = raw_date[:10]

        uid = hashlib.md5(link.encode()).hexdigest()[:12]
        items.append({"uid": uid, "title": title, "link": link, "date": date})

    return items


def _get_category_id(session: requests.Session) -> int | None:
    try:
        resp = session.get(
            f"{WP_API_BASE}/doc-cat",
            params={"slug": DOC_CAT_SLUG, "_fields": "id,slug,name"},
            timeout=15,
        )
        resp.raise_for_status()
        cats = resp.json()
        if cats:
            return cats[0]["id"]
    except Exception as e:
        print(f"    Gelex get category: {e}")
    return None
