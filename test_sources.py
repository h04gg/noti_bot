"""
Script test nhanh để kiểm tra từng nguồn có lấy được data không.
Chạy: python test_sources.py
"""

import requests
import json
import re
from datetime import datetime

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
})

def sep(title): print(f"\n{'='*55}\n{title}\n{'='*55}")

# ─── 1. Phát Đạt ──────────────────────────────────────────────
sep("1. PHÁT ĐẠT — JSON API")
try:
    r = session.get("https://www.phatdat.com.vn/ajax/reports/filter",
                    params={"category_id":5,"year":"","page":1,"lang":"vi"}, timeout=15)
    from bs4 import BeautifulSoup
    data = r.json()
    soup = BeautifulSoup(data["data"]["html"], "html.parser")
    links = soup.select("a.recruitment-link")
    print(f"✅ OK — {len(links)} items | First: {links[0].text.strip()[:60] if links else 'N/A'}")
except Exception as e:
    print(f"❌ {e}")

# ─── 2. VPBank ────────────────────────────────────────────────
sep("2. VPBANK — JSON API")
try:
    r = session.get("https://www.vpbank.com.vn/uiux-api/api/document",
                    params={"lang":"vi",
                            "categoryPath":f"/quan-he-nha-dau-tu/cong-bo-thong-tin-khac/{datetime.now().year}",
                            "pageSize":5,"pageIndex":1}, timeout=15)
    data = r.json()
    items = data.get("data", [])
    print(f"✅ OK — {len(items)} items | Total: {data.get('total')} | First: {items[0]['title'][:60] if items else 'N/A'}")
except Exception as e:
    print(f"❌ {e}")

# ─── 3. Gelex — WordPress REST API ───────────────────────────
sep("3. GELEX — WordPress REST API")
# 3a. Thử lấy danh sách post types để xem có 'doc' không
try:
    r = session.get("https://gelex.vn/wp-json/wp/v2/types", timeout=15)
    print(f"  /types status: {r.status_code}")
    if r.ok:
        types = list(r.json().keys())
        print(f"  Post types: {types}")
        has_doc = "doc" in types
        print(f"  Has 'doc' type: {has_doc}")
    else:
        print(f"  Response: {r.text[:200]}")
except Exception as e:
    print(f"  /types error: {e}")

# 3b. Thử lấy doc trực tiếp
try:
    r = session.get("https://gelex.vn/wp-json/wp/v2/doc",
                    params={"per_page":3,"_fields":"id,title,date,link"}, timeout=15)
    print(f"  /doc status: {r.status_code}")
    if r.ok:
        items = r.json()
        print(f"✅ OK — {len(items)} items | First: {items[0]['title']['rendered'][:60] if items else 'N/A'}")
    else:
        print(f"  Response: {r.text[:300]}")
except Exception as e:
    print(f"  /doc error: {e}")

# 3c. Thử posts thông thường
try:
    r = session.get("https://gelex.vn/wp-json/wp/v2/posts",
                    params={"per_page":3,"_fields":"id,title,date,link","search":"cong-bo"}, timeout=15)
    print(f"  /posts status: {r.status_code}")
    if r.ok:
        items = r.json()
        print(f"  /posts — {len(items)} items")
    else:
        print(f"  /posts: {r.text[:200]}")
except Exception as e:
    print(f"  /posts error: {e}")

# ─── 4. Eximbank — Next.js ───────────────────────────────────
sep("4. EXIMBANK — Next.js")
try:
    r = session.get("https://eximbank.com.vn/thong-tin-khac", timeout=20)
    print(f"  HTML status: {r.status_code}")
    
    # Tìm __NEXT_DATA__
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
    if m:
        nd = json.loads(m.group(1))
        build_id = nd.get("buildId", "N/A")
        props = nd.get("props", {}).get("pageProps", {})
        print(f"  buildId: {build_id}")
        print(f"  pageProps keys: {list(props.keys())}")
        
        # Tìm data trong props
        for key in ["documents","data","items","list","posts","records"]:
            if key in props:
                val = props[key]
                print(f"  ✅ Found '{key}': {len(val) if isinstance(val, list) else val}")
                break
        else:
            # In toàn bộ props để debug
            print(f"  pageProps content: {json.dumps(props, ensure_ascii=False)[:500]}")
    else:
        # Tìm buildId theo cách khác
        m2 = re.search(r'"buildId":"([^"]+)"', r.text)
        if m2:
            print(f"  buildId: {m2.group(1)} (nhưng không có __NEXT_DATA__)")
        else:
            print(f"  Không tìm thấy __NEXT_DATA__ hay buildId")
            print(f"  HTML snippet: {r.text[:300]}")
except Exception as e:
    print(f"❌ {e}")

# ─── 5. Vingroup ─────────────────────────────────────────────
sep("5. VINGROUP — HTML SSR")
try:
    r = session.get("https://vingroup.net/quan-he-co-dong/cong-bo-thong-tin/dai-hoi-dong-co-dong",
                    params={"items":10}, timeout=15)
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "html.parser")
    links = soup.select("a[href*='ircdn.vingroup.net'], a[href*='/bai-viet/']")
    print(f"✅ OK — {len(links)} items | First: {links[0].text.strip()[:60] if links else 'N/A'}")
except Exception as e:
    print(f"❌ {e}")

print("\n" + "="*55)
print("Xong! Kết quả trên cho biết nguồn nào hoạt động.")
print("="*55)
