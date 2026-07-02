"""
Scraper: HDBank — API investor (response AES, giống FE Next.js).

Trang CBTT không có JSON công khai; FE gọi:
  GET /api/vi/investors/{slug_type}/{slug_category}/{slug_detail}
Header bắt buộc: local=vi (không phải cookie).
"""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from scrapers._common import extract_dmY, format_dmY, make_item

BASE = "https://hdbank.com.vn"
API_BASE = f"{BASE}/api"
# Fallback nếu không lấy được từ FE / env
_DEFAULT_AES_KEY = b"Z9GRKIgYKH2CUdqfas858Q=="
_AES_KEY_RE = re.compile(
    r'enc\.Utf8\.parse\("([A-Za-z0-9+/=]+)"\)[\s\S]{0,120}?AES\.decrypt',
)
_FILENAME_DATE_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})")
_cached_aes_key: bytes | None = None


def _key_from_env() -> bytes | None:
    raw = (os.environ.get("HDBANK_AES_KEY") or "").strip()
    if not raw:
        return None
    # CryptoJS Utf8.parse — dùng chuỗi UTF-8 literal, không base64-decode
    return raw.encode("utf-8")


def _key_from_fe(session: requests.Session, page_url: str) -> bytes | None:
    """Lấy key từ bundle Next.js (_app-*.js) — cùng nguồn FE dùng khi decrypt."""
    try:
        resp = session.get(page_url, timeout=30)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"    HDBank FE page: {e}")
        return None

    scripts = re.findall(r'src="(/_next/static/chunks/[^"]+\.js)"', html)
    # Ưu tiên _app chunk (thường chứa crypto helper)
    scripts.sort(key=lambda s: (0 if "/_app-" in s else 1, s))

    for path in scripts:
        try:
            js = session.get(f"{BASE}{path}", timeout=25).text
        except Exception:
            continue
        match = _AES_KEY_RE.search(js)
        if match:
            return match.group(1).encode("utf-8")

    return None


def _is_valid_aes_key(key: bytes) -> bool:
    try:
        key.decode("ascii")
    except UnicodeDecodeError:
        return False
    return 0 < len(key) <= 32


def _decrypt_payload(raw: str, key: bytes) -> dict | list:
    if not _is_valid_aes_key(key):
        raise ValueError("AES key không hợp lệ (cần ASCII)")
    text = raw.strip()
    pad = (-len(text)) % 4
    if pad:
        text += "=" * pad
    plain = unpad(AES.new(key, AES.MODE_ECB).decrypt(base64.b64decode(text)), 16)
    return json.loads(plain.decode("utf-8"))


def _aes_key_candidates(session: requests.Session, page_url: str) -> list[bytes]:
    candidates: list[bytes] = []
    seen: set[bytes] = set()

    def _add(key: bytes | None) -> None:
        if not key or not _is_valid_aes_key(key) or key in seen:
            return
        seen.add(key)
        candidates.append(key)

    _add(_key_from_env())
    _add(_DEFAULT_AES_KEY)
    _add(_key_from_fe(session, page_url))
    return candidates


def _date_from_link(link: str, title: str) -> str:
    m = _FILENAME_DATE_RE.search(link)
    if m:
        return format_dmY(m.group(3), m.group(2), m.group(1))
    return extract_dmY(title)


def _parse_menu_html(html: str) -> list[dict]:
    items: list[dict] = []
    seen_links: set[str] = set()
    soup = BeautifulSoup(html or "", "html.parser")

    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href or ".pdf" not in href.lower():
            continue
        if not href.startswith("http"):
            href = BASE + href if href.startswith("/") else f"{BASE}/{href.lstrip('/')}"
        if href in seen_links:
            continue

        title = a.get_text(" ", strip=True)
        if not title or len(title) < 8:
            continue

        seen_links.add(href)
        items.append(make_item(title, href, _date_from_link(href, title)))

    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    api_path = source.get(
        "api_path",
        "/vi/investors/thong-tin-nha-dau-tu/quan-he-co-dong/cong-bo-thong-tin-thong-tin-khac",
    )
    page_url = source.get(
        "source_page",
        f"{BASE}/vi/investor/thong-tin-nha-dau-tu/quan-he-co-dong/cong-bo-thong-tin-thong-tin-khac",
    )

    session.headers.setdefault("Accept", "application/json")
    session.headers.setdefault("Content-Type", "application/json")
    session.headers.setdefault("local", "vi")
    session.headers.setdefault("Origin", BASE)
    session.headers.setdefault("Referer", page_url)

    try:
        resp = session.get(f"{API_BASE}{api_path}", timeout=30)
        resp.raise_for_status()
        raw = resp.text
        payload = None
        last_error: Exception | None = None
        for key in _aes_key_candidates(session, page_url):
            try:
                payload = _decrypt_payload(raw, key)
                global _cached_aes_key
                _cached_aes_key = key
                break
            except Exception as e:
                last_error = e
        if payload is None:
            raise last_error or RuntimeError("HDBank decrypt thất bại")
    except Exception as e:
        print(f"    HDBank API: {e}")
        return []

    menu = payload.get("menuList") if isinstance(payload, dict) else None
    if not menu:
        print("    HDBank: menuList rỗng")
        return []

    min_year = datetime.now().year - 1
    items: list[dict] = []
    seen_uids: set[str] = set()

    for section in menu:
        year_label = (section.get("name") or "").strip()
        if year_label.isdigit() and int(year_label) < min_year:
            continue

        for item in _parse_menu_html(section.get("content") or ""):
            if item["uid"] in seen_uids:
                continue
            seen_uids.add(item["uid"])
            items.append(item)

    return items
