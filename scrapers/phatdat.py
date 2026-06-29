"""
Scraper: Phát Đạt — JSON API
URL: /ajax/reports/filter?category_id=5&page=1&lang=vi
"""

import hashlib
import requests
from bs4 import BeautifulSoup


def fetch(source: dict, session: requests.Session) -> list[dict]:
    resp = session.get(source["url"], params=source["params"], timeout=20)
    resp.raise_for_status()

    data = resp.json()
    html = data.get("data", {}).get("html", "")
    soup = BeautifulSoup(html, "html.parser")

    items = []
    for a in soup.select("a.recruitment-link"):
        title = a.get_text(" ", strip=True).strip()
        link = a.get("href", "").strip()
        if not title or not link:
            continue
        if not link.startswith("http"):
            link = "https://www.phatdat.com.vn" + link

        # Ngày nằm trong <div class="date"> kế tiếp
        date = ""
        date_div = a.find_next("div", class_="date")
        if date_div:
            date = date_div.get_text(strip=True)

        uid = hashlib.md5(link.encode()).hexdigest()[:12]
        items.append({"uid": uid, "title": title, "link": link, "date": date})

    return items
