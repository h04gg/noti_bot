"""
Cấu hình các nguồn theo dõi IR
"""

# Chỉ theo dõi tin trong N ngày gần nhất (áp dụng tự động cho mọi nguồn)
RECENT_DAYS = 14

CATEGORIES = {
    "bds": {"name": "Bất động sản", "emoji": "🏗️"},
    "bank": {"name": "Ngân hàng", "emoji": "🏦"},
    "other": {"name": "Khác", "emoji": "📋"},
}

SOURCES = [
    {
        "id": "phatdat",
        "name": "Phát Đạt (PDR)",
        "emoji": "🏠",
        "category": "bds",
        "url": "https://www.phatdat.com.vn/ajax/reports/filter",
        "params": {"category_id": 5, "year": "", "quarter": "", "page": 1, "lang": "vi"},
        "source_page": "https://www.phatdat.com.vn/quan-he-co-dong/cong-bo-thong-tin",
    },
    {
        "id": "vpbank",
        "name": "VPBank",
        "emoji": "🏦",
        "category": "bank",
        "url": "https://www.vpbank.com.vn/uiux-api/api/document",
        "params": {
            "lang": "vi",
            "categoryPath": "/quan-he-nha-dau-tu/cong-bo-thong-tin-khac/2026",
            "pageSize": 10,
            "pageIndex": 1,
        },
        "source_page": "https://www.vpbank.com.vn/quan-he-nha-dau-tu/cong-bo-thong-tin-khac",
    },
    {
        "id": "gelex",
        "name": "Gelex",
        "emoji": "⚡",
        "category": "other",
        "url": "https://gelex.vn/wp-json/wp/v2",
        "source_page": "https://gelex.vn/doc-cat/cong-bo-thong-tin-2",
    },
    {
        "id": "eximbank",
        "name": "Eximbank",
        "emoji": "💳",
        "category": "bank",
        "url": "https://eximbank.com.vn/thong-tin-khac",
        "source_page": "https://eximbank.com.vn/thong-tin-khac",
    },
    {
        "id": "vingroup",
        "name": "Vingroup",
        "emoji": "🏢",
        "category": "bds",
        "url": "https://vingroup.net/quan-he-co-dong/cong-bo-thong-tin/dai-hoi-dong-co-dong",
        "params": {"items": 50},
        "source_page": "https://vingroup.net/quan-he-co-dong/cong-bo-thong-tin/dai-hoi-dong-co-dong",
    },
    {
        "id": "hoanghuy",
        "name": "Hoàng Huy",
        "emoji": "🏗️",
        "category": "bds",
        "url": "https://www.hoanghuy.vn/quan-he-co-dong/",
        "source_page": "https://www.hoanghuy.vn/quan-he-co-dong/",
    },
    {
        "id": "dic",
        "name": "DIG (DIC Corp)",
        "emoji": "🏘️",
        "category": "bds",
        "url": "https://www.dic.vn/cong-bo-thong-tin",
        "source_page": "https://www.dic.vn/cong-bo-thong-tin",
    },
]
