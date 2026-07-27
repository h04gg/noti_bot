"""Scraper: TPBank (TPB) — IBM WCM (Thông báo cổ đông + Báo cáo tài chính)."""

from __future__ import annotations

import re
import sys
import time
from datetime import datetime
from html import unescape
from urllib.parse import unquote

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from scrapers._common import extract_dmY, finalize_fetch, make_item, proxy_for

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0

BASE = "https://tpb.vn"
WCM = f"{BASE}/wps/wcm/connect"
IMPERSONATE_PROFILES = ("chrome124", "chrome120", "safari17_0")
TIMEOUT = 45
RETRIES = 3
RETRY_DELAY = 4

# Fallback nếu không parse được từ HTML trang / năm
_DEFAULT_YEAR_CMPNT = {
    "thong-bao-co-dong": "ba967af0-f513-460f-9c1f-fc2608173164",
    "bao-cao-tai-chinh": "a195ac0f-7c76-41b4-9fcb-faad8c7f22fc",
}
_DEFAULT_MONTH_CMPNT = "5d814d0d-2be7-4527-a5ac-18a3aa727271"

_YEAR_CMPNT_RE = re.compile(
    r'content-collapse-list\s*\.group-wrapper"\)\.click[\s\S]{0,500}?cmpntid=([a-f0-9-]{36})',
    re.I,
)
_MONTH_CMPNT_RE = re.compile(
    r'group-content[\s\S]{0,300}?cmpntid=([a-f0-9-]{36})',
    re.I,
)
_GROUP_PATH_RE = re.compile(r'class="group-wrapper"[^>]*\spath="([^"]+)"', re.I)


def _wcm_url(path: str, cmpntid: str) -> str:
    path = path if path.startswith("/") else f"/{path}"
    return f"{WCM}{path}?source=library&srv=cmpnt&cmpntid={cmpntid}"


def _abs_link(href: str) -> str:
    href = unescape((href or "").strip())
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return f"{BASE}{href}" if href.startswith("/") else f"{BASE}/{href}"


def _parse_docs(html: str) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for a in soup.select("a.file-icon[href], a.file-icon-pdf[href], div.b-right-download a[href]"):
        href = (a.get("href") or "").strip()
        if not href or href == "#":
            continue
        link = _abs_link(href)
        # Bỏ query cache của WCM khỏi UID ổn định hơn — giữ full link để tải được
        text = a.get_text(" ", strip=True)
        if not text or len(text) < 5:
            continue

        date = extract_dmY(text)
        title = text
        if date:
            title = text.replace(date, "", 1).strip(" -–—\t")
        if not title:
            # Fallback: tên file trong URL
            title = unquote(link.split("/")[-1].split("?")[0])
            title = re.sub(r"\+[-\s]*", " ", title)
            title = re.sub(r"\.pdf$", "", title, flags=re.I).strip()

        item = make_item(title, link, date)
        if item["uid"] in seen:
            continue
        seen.add(item["uid"])
        items.append(item)

    return items


def _extract_year_cmpnt(page_html: str, feed_key: str) -> str:
    m = _YEAR_CMPNT_RE.search(page_html or "")
    if m:
        return m.group(1)
    return _DEFAULT_YEAR_CMPNT.get(feed_key, next(iter(_DEFAULT_YEAR_CMPNT.values())))


def _extract_month_cmpnt(year_html: str) -> str:
    m = re.search(
        r'\$\("\.group-content"\)[\s\S]{0,400}?cmpntid=([a-f0-9-]{36})',
        year_html or "",
        re.I,
    )
    if m:
        return m.group(1)
    m = _MONTH_CMPNT_RE.search(year_html or "")
    if m:
        return m.group(1)
    return _DEFAULT_MONTH_CMPNT


def _year_paths(page_html: str, years: list[int]) -> list[str]:
    paths = _GROUP_PATH_RE.findall(page_html or "")
    wanted = []
    for year in years:
        token = f"/{year}/{year}"
        for path in paths:
            if path.endswith(token) or f"/{year}/{year}" in path:
                wanted.append(path)
                break
    return wanted


def _month_paths(year_html: str) -> list[str]:
    soup = BeautifulSoup(year_html or "", "html.parser")
    paths: list[str] = []
    for el in soup.select(".group-content[path]"):
        path = (el.get("path") or "").strip()
        if path and path not in paths:
            paths.append(path)
    return paths


def _get(session: curl_requests.Session, url: str, referer: str) -> str:
    resp = session.get(
        url,
        timeout=TIMEOUT,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
            "Referer": referer,
        },
        proxies=proxy_for("tpb"),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}")
    return resp.text


def _open_session(profile: str) -> curl_requests.Session:
    session = curl_requests.Session(impersonate=profile)
    session.get(BASE, timeout=TIMEOUT, proxies=proxy_for("tpb"))
    return session


def _get_with_retry(url: str, referer: str) -> str:
    last_error: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        profile = IMPERSONATE_PROFILES[(attempt - 1) % len(IMPERSONATE_PROFILES)]
        session = _open_session(profile)
        try:
            return _get(session, url, referer)
        except Exception as e:
            last_error = e
            if attempt < RETRIES:
                print(
                    f"    TPB {profile}: lỗi lần {attempt}/{RETRIES}: {e}"
                    f" — thử lại sau {RETRY_DELAY}s"
                )
                time.sleep(RETRY_DELAY)
        finally:
            session.close()
    raise RuntimeError(str(last_error)) from last_error


def _fetch_feed(
    session: curl_requests.Session,
    page_url: str,
    feed_key: str,
    label: str,
    years: list[int],
) -> list[dict]:
    page_html = unescape(_get(session, page_url, page_url))
    year_cmpnt = _extract_year_cmpnt(page_html, feed_key)
    year_paths = _year_paths(page_html, years)
    if not year_paths:
        raise RuntimeError(f"TPB {label}: không thấy nhóm năm trên trang")

    merged: list[dict] = []
    seen: set[str] = set()

    for ypath in year_paths:
        try:
            year_html = _get(session, _wcm_url(ypath, year_cmpnt), page_url)
        except Exception as e:
            # Một số IP bị chặn endpoint năm BCTC — thử lại với session mới
            try:
                year_html = _get_with_retry(_wcm_url(ypath, year_cmpnt), page_url)
            except Exception as e2:
                print(f"    TPB {label} year {ypath.rsplit('/', 1)[-1]}: {e2}")
                continue

        month_cmpnt = _extract_month_cmpnt(year_html)
        months = _month_paths(year_html)
        if not months:
            for item in _parse_docs(year_html):
                if item["uid"] not in seen:
                    seen.add(item["uid"])
                    merged.append(item)
            continue

        for mpath in months:
            try:
                month_html = _get(session, _wcm_url(mpath, month_cmpnt), page_url)
            except Exception as e:
                print(f"    TPB {label} month: {e}")
                continue
            for item in _parse_docs(month_html):
                if item["uid"] not in seen:
                    seen.add(item["uid"])
                    merged.append(item)

    if not merged and year_paths:
        raise RuntimeError(f"TPB {label}: không lấy được tài liệu (có thể bị chặn)")
    return merged


def fetch(source: dict, session) -> list[dict]:
    year = datetime.now().year
    years = [year, year - 1]
    feeds = source.get(
        "feeds",
        [
            {
                "page_url": f"{BASE}/nha-dau-tu/thong-bao-co-dong",
                "key": "thong-bao-co-dong",
                "label": "TBCD",
            },
            {
                "page_url": f"{BASE}/nha-dau-tu/bao-cao-tai-chinh",
                "key": "bao-cao-tai-chinh",
                "label": "BCTC",
            },
        ],
    )

    curl = curl_requests.Session(impersonate=IMPERSONATE_PROFILES[0])
    merged: list[dict] = []
    seen: set[str] = set()

    try:
        curl.get(BASE, timeout=TIMEOUT, proxies=proxy_for("tpb"))
        for feed in feeds:
            page_url = feed.get("page_url") or feed.get("url")
            label = feed.get("label", "FEED")
            key = feed.get("key") or ""
            if not key and page_url:
                key = page_url.rstrip("/").rsplit("/", 1)[-1]
            try:
                items = _fetch_feed(curl, page_url, key, label, years)
            except Exception as e:
                # BCTC có thể fail trên một số IP — không kéo fail cả TBCD
                print(f"    {e} — bỏ qua {label}")
                items = []
            print(f"    TPB {label}: {len(items)}")
            for item in items:
                if item["uid"] not in seen:
                    seen.add(item["uid"])
                    merged.append(item)
    finally:
        curl.close()

    if not merged:
        raise RuntimeError("TPB: không lấy được tin từ TBCD/BCTC (có thể bị chặn)")

    return finalize_fetch(_MOD, merged)
