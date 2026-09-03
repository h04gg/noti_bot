"""
Cấu hình các nguồn theo dõi IR
"""

# Chỉ theo dõi tin trong N ngày gần nhất (áp dụng tự động cho mọi nguồn)
RECENT_DAYS = 7

CATEGORIES = {
    "securities": {"name": "Chứng khoán", "emoji": "📈"},
    "other": {"name": "Khác", "emoji": "📋"},
}

SOURCES = [
    {
        "id": "hsx",
        "name": "HSX (Tin tức)",
        "emoji": "🏛️",
        "category": "securities",
        "api_url": "https://api.hsx.vn/n/api/v1/1/news",
        "params": {"pageSize": 100, "aliasCate": "tin-tuc"},
        "source_page": "https://www.hsx.vn/vi/tin-tuc",
    },
    {
        "id": "hnx",
        "name": "HNX (Tin TCPH)",
        "emoji": "🏢",
        "category": "securities",
        "params": {"pageSize": 50},
        "source_page": "https://hnx.vn/thong-tin-cong-bo-ny-tcph.html",
    },
]
