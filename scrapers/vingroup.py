"""
Scraper: Vingroup — HTML SSR (requests + BeautifulSoup)
URL: /quan-he-co-dong/cong-bo-thong-tin/dai-hoi-dong-co-dong
"""

import hashlib
import requests
from bs4 import BeautifulSoup


def fetch(source: dict, session: requests.Session) -> list[dict]:
    params = source.get("params", {})
    resp = session.get(source["url"], params=params, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    items = []

    for a in soup.select("a[href*='ircdn.vingroup.net'], a[href*='/bai-viet/']"):
        title = a.get_text(" ", strip=True).strip()
        if not title:
            continue
        link = a.get("href", "").strip()
        if not link.startswith("http"):
            link = "https://vingroup.net" + link

        date = ""
        parent = a.parent
        if parent:
            em = parent.find("em") or parent.find("i")
            if em:
                date = em.get_text(strip=True)

        uid = hashlib.md5(link.encode()).hexdigest()[:12]
        items.append({"uid": uid, "title": title, "link": link, "date": date})

    return items
