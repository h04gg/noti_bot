"""Scraper: Techcombank (TCB) — GraphQL viewDocumentList."""

from __future__ import annotations

import requests

from filters import filter_recent_items
from scrapers._common import date_from_iso, make_item

BASE = "https://techcombank.com"
PAGE_URL = f"{BASE}/nha-dau-tu/cong-bo-thong-tin"

DEFAULT_ENDPOINTS = (
    {"cf_slug": "disclosure-khac", "referer": "thong-tin-khac"},
    {"cf_slug": "hoi-dong-quan-tri", "referer": "nghi-quyet-hdqt"},
    {"cf_slug": "tai-lieu-doanh-nghiep", "referer": "tai-lieu-doanh-nghiep"},
)


def _api_url(cf_slug: str) -> str:
    return (
        f"{BASE}/graphql/execute.json/techcombank/viewDocumentList%3BcfPath%3D"
        f"/content/dam/techcombank/master-data/vi/list-view-document/{cf_slug}/"
    )


def _abs_link(path: str) -> str:
    path = (path or "").strip()
    if not path:
        return ""
    if path.startswith("http"):
        return path
    return BASE + path if path.startswith("/") else f"{BASE}/{path}"


def _doc_link(doc: dict) -> str:
    doc_path = doc.get("documentPath") or {}
    link = (doc_path.get("_publishUrl") or "").strip()
    if link:
        return link
    return _abs_link(doc.get("externalDocumentPath") or "")


def _plaintext(field: dict | None) -> str:
    if not field:
        return ""
    return (field.get("plaintext") or "").strip()


def _item_date(raw: str) -> str:
    return date_from_iso(raw or "")


def _parse_doc(doc: dict, parent_date: str) -> list[dict]:
    if doc.get("isDisable"):
        return []

    date = _item_date(doc.get("date") or parent_date)
    nested = doc.get("documentItems") or []
    if nested:
        items: list[dict] = []
        for child in nested:
            if child.get("isDisable"):
                continue
            title = _plaintext(child.get("documentTitle"))
            link = _doc_link(child)
            if not title or not link:
                continue
            items.append(make_item(title, link, date))
        return items

    title = _plaintext(doc.get("categoryTitle")) or _plaintext(doc.get("documentTitle"))
    link = _doc_link(doc)
    if not title or not link:
        return []
    return [make_item(title, link, date)]


def _fetch_endpoint(
    session: requests.Session,
    cf_slug: str,
    referer_slug: str,
) -> list[dict]:
    try:
        resp = session.get(
            _api_url(cf_slug),
            headers={"Referer": f"{PAGE_URL}/{referer_slug}"},
            timeout=40,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        print(f"    TCB {cf_slug}: {e}")
        return []

    fragment = (payload.get("data") or {}).get("listViewDocumentFragmentList") or {}
    items: list[dict] = []
    for doc in fragment.get("items") or []:
        items.extend(_parse_doc(doc, doc.get("date") or ""))
    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    page_url = source.get("source_page", PAGE_URL)
    endpoints = source.get("endpoints", DEFAULT_ENDPOINTS)

    session.headers.setdefault("Accept", "*/*")
    session.headers.setdefault("X-Requested-With", "XMLHttpRequest")
    session.headers.setdefault("Referer", page_url)

    seen_uids: set[str] = set()
    all_items: list[dict] = []

    for endpoint in endpoints:
        cf_slug = endpoint["cf_slug"]
        referer = endpoint.get("referer", cf_slug)
        for item in _fetch_endpoint(session, cf_slug, referer):
            if item["uid"] in seen_uids:
                continue
            seen_uids.add(item["uid"])
            all_items.append(item)

    return filter_recent_items(all_items)
