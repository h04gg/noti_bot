"""
Cấu hình các nguồn theo dõi IR
"""

# Chỉ theo dõi tin trong N ngày gần nhất (áp dụng tự động cho mọi nguồn)
RECENT_DAYS = 14

CATEGORIES = {
    "bds": {"name": "Bất động sản", "emoji": "🏗️"},
    "finance": {"name": "Tài chính", "emoji": "💰"},
    "securities": {"name": "Chứng khoán", "emoji": "📈"},
    "bank": {"name": "Ngân hàng", "emoji": "🏦"},
    "other": {"name": "Khác", "emoji": "📋"},
}

SOURCES = [
    # ── Bất động sản ──────────────────────────────────────────────────────────
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
    {
        "id": "kdh",
        "name": "Khang Điền (KDH)",
        "emoji": "🏡",
        "category": "bds",
        "url": "https://www.khangdien.com.vn/co-dong/cong-bo-thong-tin",
        "source_page": "https://www.khangdien.com.vn/co-dong/cong-bo-thong-tin",
    },
    {
        "id": "nvl",
        "name": "Novaland (NVL)",
        "emoji": "🌆",
        "category": "bds",
        "url": "https://www.novaland.com.vn/quan-he-dau-tu/cong-bo-thong-tin/thong-bao",
        "source_page": "https://www.novaland.com.vn/quan-he-dau-tu/cong-bo-thong-tin/thong-bao",
    },
    {
        "id": "ksf",
        "name": "Sunshine (KSF)",
        "emoji": "☀️",
        "category": "bds",
        "url": "https://sunshinegroup.vn/cong-bo-thong-tin/",
        "api_url": "https://ir.sunshinegroup.vn/wp-json/api/v1/thong-tin-co-dong/cong-bo-thong-tin",
        "source_page": "https://sunshinegroup.vn/cong-bo-thong-tin/",
    },
    # ── Tài chính ─────────────────────────────────────────────────────────────
    {
        "id": "f88",
        "name": "F88",
        "emoji": "💵",
        "category": "finance",
        "url": "https://nhadautu.f88.vn/cong-bo-thong-tin",
        "api_url": "https://apis.f88.vn/growth/f88vn/api/v1/Initial/InitPageInvestDocument",
        "source_page": "https://nhadautu.f88.vn/cong-bo-thong-tin",
    },
    # ── Chứng khoán ───────────────────────────────────────────────────────────
    {
        "id": "vci",
        "name": "Vietcap (VCI)",
        "emoji": "📊",
        "category": "securities",
        "url": "https://www.vietcap.com.vn/quan-he-co-dong/",
        "source_page": "https://www.vietcap.com.vn/quan-he-co-dong/",
    },
    {
        "id": "hds",
        "name": "HD Securities (HDS)",
        "emoji": "📉",
        "category": "securities",
        "url": "https://hdbs.vn/quan-he-co-dong/cong-bo-thong-tin/",
        "source_page": "https://hdbs.vn/quan-he-co-dong/cong-bo-thong-tin/",
    },
    {
        "id": "vck",
        "name": "VPS (VCK)",
        "emoji": "🧾",
        "category": "securities",
        "url": "https://www.vps.com.vn/quan-he-co-dong/cong-bo-thong-tin",
        "source_page": "https://www.vps.com.vn/quan-he-co-dong/cong-bo-thong-tin",
    },
    {
        "id": "tcx",
        "name": "TCBS (TCX)",
        "emoji": "🏛️",
        "category": "securities",
        "url": "https://www.tcbs.com.vn/nha-dau-tu/quan-he-nha-dau-tu/cong-bo-thong-tin/",
        "source_page": "https://www.tcbs.com.vn/nha-dau-tu/quan-he-nha-dau-tu/cong-bo-thong-tin/",
    },
    # {
    #     "id": "mbs",
    #     "name": "MB Securities (MBS)",
    #     "emoji": "📑",
    #     "category": "securities",
    #     "url": "https://www.mbs.com.vn/cong-bo-thong-tin/",
    #     "source_page": "https://www.mbs.com.vn/cong-bo-thong-tin/",
    # },  # Tạm tắt: site chặn bot (403)
    {
        "id": "ssi",
        "name": "SSI",
        "emoji": "🔷",
        "category": "securities",
        "url": "https://www.ssi.com.vn/quan-he-nha-dau-tu/cong-bo-thong-tin",
        "source_page": "https://www.ssi.com.vn/quan-he-nha-dau-tu/cong-bo-thong-tin",
    },
    # ── Ngân hàng ─────────────────────────────────────────────────────────────
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
        "id": "eximbank",
        "name": "Eximbank",
        "emoji": "💳",
        "category": "bank",
        "url": "https://eximbank.com.vn/thong-tin-khac",
        "source_page": "https://eximbank.com.vn/thong-tin-khac",
    },
    {
        "id": "mbb",
        "name": "MBBank (MBB)",
        "emoji": "🪖",
        "category": "bank",
        "url": "https://www.mbbank.com.vn/Investor/thong-bao-nha-dau-tu/2026/0//0",
        "source_page": "https://www.mbbank.com.vn/Investor/thong-bao-nha-dau-tu/2026/0//0",
    },
    # {
    #     "id": "lpb",
    #     "name": "LPBank (LPB)",
    #     "emoji": "🌿",
    #     "category": "bank",
    #     "url": "https://lpbank.com.vn/nha-dau-tu/cong-bo-thong-tin",
    #     "source_page": "https://lpbank.com.vn/nha-dau-tu/cong-bo-thong-tin",
    # },  # Tạm tắt: chưa có CBTT trên API
    # ── Khác ──────────────────────────────────────────────────────────────────
    {
        "id": "gelex",
        "name": "Gelex",
        "emoji": "⚡",
        "category": "other",
        "url": "https://gelex.vn/wp-json/wp/v2",
        "source_page": "https://gelex.vn/doc-cat/cong-bo-thong-tin-2",
    },
]
