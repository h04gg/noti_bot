"""Scraper: HNX — Thông tin công bố NY · tab TIN TỪ TỔ CHỨC PHÁT HÀNH."""

from __future__ import annotations

import re
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning

from hnx_watchlist import get_company
from scrapers._common import extract_dmY, finalize_fetch, item_uid, make_item, page_fetch_failed

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

_MOD = sys.modules[__name__]
LAST_RAW_COUNT = 0

BASE = "https://hnx.vn"
PAGE_URL = f"{BASE}/thong-tin-cong-bo-ny-tcph.html"
LIST_API = f"{BASE}/ModuleArticles/ArticlesCPEtfs/NextPageTinCPNY_CBTCPH"
FILE_API = f"{BASE}/ModuleArticles/ArticlesCPEtfs/ArticlesFileAttach"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PAGE_SIZE = 50
MAX_PAGES = 20
FILE_WORKERS = 8
_ARTICLE_ID_RE = re.compile(r"funcViewDetailArticlesByID\((\d+)\s*,")
_TOTAL_RE = re.compile(r"Tổng số\s*(\d+)", re.I)


def _date_range() -> tuple[str, str]:
    """HNX: hôm qua → hôm nay (dd/MM/yyyy)."""
    today = datetime.now(VN_TZ).date()
    start = today - timedelta(days=1)
    return start.strftime("%d/%m/%Y"), today.strftime("%d/%m/%Y")


def _session() -> requests.Session:
    session = requests.Session()
    session.verify = False
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "vi-VN,vi;q=0.9",
        }
    )
    return session


def _fetch_list_page(
    session: requests.Session,
    *,
    page: int,
    action: int,
    from_date: str,
    to_date: str,
    page_size: int,
) -> str:
    resp = session.post(
        LIST_API,
        data={
            "pNumPage": page,
            "pAction": action,
            "pNhomTin": "",
            "pTieuDeTin": "",
            "pMaChungKhoan": "",
            "pFromDate": from_date,
            "pToDate": to_date,
            "pOrderBy": "",
            "pNumRecord": page_size,
        },
        timeout=45,
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Referer": PAGE_URL,
            "Accept": "*/*",
        },
    )
    resp.raise_for_status()
    return resp.text


def _parse_total(html: str) -> int | None:
    m = _TOTAL_RE.search(html or "")
    return int(m.group(1)) if m else None


def _pdf_link(article_id: int) -> str:
    """Mỗi gọi dùng session riêng — requests.Session không thread-safe."""
    session = _session()
    try:
        resp = session.post(
            FILE_API,
            data={"pArticlesID": article_id, "pType": 1},
            timeout=20,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": PAGE_URL,
                "Accept": "*/*",
            },
        )
        resp.raise_for_status()
    except Exception:
        return ""
    finally:
        session.close()

    soup = BeautifulSoup(resp.text, "html.parser")
    links = [
        (a.get("href") or "").strip()
        for a in soup.select("a[href]")
        if (a.get("href") or "").startswith("http")
    ]
    if not links:
        return ""

    for link in links:
        name = link.lower().rsplit("/", 1)[-1]
        if "_vi" in name or name.endswith("vi.pdf"):
            return link
    for link in links:
        if ".pdf" in link.lower():
            return link
    return links[0]


def _parse_rows(html: str) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    items: list[dict] = []
    for tr in soup.select("table#_tableDatas tbody tr"):
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue

        date = extract_dmY(cells[1].get_text(" ", strip=True))
        symbol = (cells[2].get_text(" ", strip=True) or "").upper()
        title_a = cells[4].select_one("a.hrefViewDetail") or cells[4].select_one("a")
        title = title_a.get_text(" ", strip=True) if title_a else ""
        if not title:
            continue

        onclick = (title_a.get("onclick") if title_a else "") or ""
        m = _ARTICLE_ID_RE.search(onclick)
        if not m:
            continue

        items.append(
            {
                "article_id": int(m.group(1)),
                "symbol": symbol,
                "title": title,
                "date": date,
            }
        )
    return items


def _enrich_rows(rows: list[dict]) -> list[dict]:
    """Gắn meta watchlist; tin ngoài list → mục Khác."""
    enriched: list[dict] = []
    for row in rows:
        row = dict(row)
        symbol = (row.get("symbol") or "").upper()
        row["symbol"] = symbol
        company = get_company(symbol)
        if company:
            row["company"] = company["name"]
            row["sector"] = company["sector"]
            row["sector_emoji"] = company["sector_emoji"]
            row["company_emoji"] = company["emoji"]
            row["is_other"] = False
        else:
            row["company"] = symbol or "Khác"
            row["sector"] = "Khác"
            row["sector_emoji"] = "📋"
            row["company_emoji"] = "📄"
            row["is_other"] = True
            title = row.get("title") or ""
            if symbol and not title.upper().startswith(f"{symbol}:"):
                row["title"] = f"{symbol}: {title}"
        enriched.append(row)
    return enriched


def _resolve_links(rows: list[dict], page_url: str) -> list[dict]:
    """Lấy PDF song song — fallback về trang list nếu không có file."""
    links: dict[int, str] = {}

    def _one(article_id: int) -> tuple[int, str]:
        return article_id, _pdf_link(article_id)

    with ThreadPoolExecutor(max_workers=FILE_WORKERS) as pool:
        futures = [pool.submit(_one, row["article_id"]) for row in rows]
        for fut in as_completed(futures):
            article_id, link = fut.result()
            links[article_id] = link

    items: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        article_id = row["article_id"]
        uid = item_uid(f"hnx-news:{article_id}")
        if uid in seen:
            continue
        link = links.get(article_id) or f"{page_url}#article-{article_id}"
        item = make_item(row["title"], link, row["date"])
        item["uid"] = uid
        item["symbol"] = row["symbol"]
        item["company"] = row["company"]
        item["sector"] = row["sector"]
        item["sector_emoji"] = row["sector_emoji"]
        item["company_emoji"] = row["company_emoji"]
        item["is_other"] = bool(row.get("is_other"))
        seen.add(uid)
        items.append(item)
    return items


def fetch(source: dict, session: requests.Session) -> list[dict]:
    http = _session()
    page_size = int(source.get("params", {}).get("pageSize", PAGE_SIZE))
    from_date, to_date = _date_range()
    page_url = source.get("source_page", PAGE_URL)

    try:
        http.get(page_url, timeout=45)
    except Exception as e:
        http.close()
        raise RuntimeError(f"HNX warmup: {e}") from e

    all_rows: list[dict] = []
    seen_ids: set[int] = set()
    total: int | None = None
    page = 1
    last_page_error: Exception | None = None

    try:
        while page <= MAX_PAGES:
            action = 1 if page == 1 else 0
            try:
                html = _fetch_list_page(
                    http,
                    page=page,
                    action=action,
                    from_date=from_date,
                    to_date=to_date,
                    page_size=page_size,
                )
            except Exception as e:
                last_page_error = e
                page_fetch_failed(page, e, "HNX")
                break

            if total is None:
                total = _parse_total(html)

            rows = _parse_rows(html)
            if not rows:
                break

            new_rows = []
            for row in rows:
                aid = row["article_id"]
                if aid in seen_ids:
                    continue
                seen_ids.add(aid)
                new_rows.append(row)

            if not new_rows:
                break

            all_rows.extend(new_rows)
            print(
                f"    HNX page {page}: +{len(new_rows)} "
                f"(from={from_date}, to={to_date}"
                f"{f', total={total}' if total is not None else ''})"
            )

            if total is not None and len(all_rows) >= total:
                break
            if len(rows) < page_size:
                break
            page += 1

        if not all_rows:
            if last_page_error:
                raise RuntimeError(f"HNX: {last_page_error}") from last_page_error
            print(f"    HNX: 0 tin trong cửa sổ {from_date} → {to_date}")
            return finalize_fetch(_MOD, [])

        enriched = _enrich_rows(all_rows)
        watched = sum(1 for r in enriched if not r.get("is_other"))
        print(f"    HNX phân loại: watchlist={watched}, khác={len(enriched) - watched}")
        merged = _resolve_links(enriched, page_url)
    finally:
        http.close()

    print(f"    HNX tổng: {len(merged)} tin ({from_date} → {to_date})")
    return finalize_fetch(_MOD, merged)
