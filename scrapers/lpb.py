"""Scraper: LPBank (LPB) — API content-service."""

from __future__ import annotations

import requests

from scrapers._common import date_from_iso, make_item

BASE = "https://lpbank.com.vn"
API = f"{BASE}/api/content-service/public/findAllPosts"
CATEGORY = "NHA_ĐAU_TU.CONG_BO_THONG_TIN"


def fetch(source: dict, session: requests.Session) -> list[dict]:
    page_url = source.get("url", f"{BASE}/nha-dau-tu/cong-bo-thong-tin")
    session.headers.setdefault("Origin", BASE)
    session.headers.setdefault("Referer", page_url)
    session.headers.setdefault("Accept", "application/json, text/plain, */*")
    session.headers.setdefault("Content-Type", "application/json")

    try:
        session.get(page_url, timeout=25, verify=False)
    except Exception as e:
        print(f"    LPB HTML: {e}")

    items: list[dict] = []
    seen: set[str] = set()
    page = 0

    while page < 5:
        try:
            resp = session.post(
                API,
                json={"postCategoryCode": CATEGORY, "page": page, "size": 50},
                timeout=25,
                verify=False,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            print(f"    LPB API page {page}: {e}")
            break

        content = (payload.get("data") or {}).get("content") or []
        if not content:
            break

        for doc in content:
            title = (doc.get("title") or "").strip()
            doc_id = doc.get("id")
            slug = doc.get("slug") or doc.get("titleSeo") or ""
            if not title or not doc_id:
                continue
            link = f"{BASE}/nha-dau-tu/cong-bo-thong-tin/chi-tiet/{doc_id}"
            if slug:
                link = f"{BASE}/nha-dau-tu/cong-bo-thong-tin/{slug}"
            if link in seen:
                continue
            seen.add(link)
            date = date_from_iso(
                doc.get("publishDate") or doc.get("createdDate") or doc.get("approvedDate") or ""
            )
            items.append(make_item(title, link, date))

        if (payload.get("data") or {}).get("last", True):
            break
        page += 1

    return items
