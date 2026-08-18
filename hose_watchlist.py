"""Watchlist mã HOSE dùng để lọc tin HSX (Tin TCNY)."""

from __future__ import annotations

# Thứ tự = thứ tự gửi Telegram (theo ngành trong sheet).
# Mỗi entry: ticker -> {name, sector, sector_emoji, emoji}
HOSE_WATCHLIST: dict[str, dict[str, str]] = {
    # ── Ngân hàng ────────────────────────────────────────────────────────────
    "VCB": {"name": "Vietcombank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🟢"},
    "BID": {"name": "BIDV", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🟠"},
    "CTG": {"name": "VietinBank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🔵"},
    "TCB": {"name": "Techcombank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🔴"},
    "VPB": {"name": "VPBank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🏦"},
    "MBB": {"name": "MBBank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🪖"},
    "LPB": {"name": "LPBank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🌿"},
    "STB": {"name": "Sacombank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🟣"},
    "ACB": {"name": "ACB", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🟡"},
    "HDB": {"name": "HDBank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🔴"},
    "SSB": {"name": "SeABank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🌊"},
    "SHB": {"name": "SHB", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🟤"},
    "MSB": {"name": "MSB", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "⬛"},
    "VIB": {"name": "VIB", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "💠"},
    "TPB": {"name": "TPBank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🟣"},
    "EIB": {"name": "Eximbank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "💳"},
    "OCB": {"name": "OCB", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "⚪"},
    "NAB": {"name": "Nam A Bank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🟢"},
    "KLB": {"name": "KienlongBank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🔷"},
    "VBB": {"name": "VietBank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🟡"},
    # ── Chứng khoán ──────────────────────────────────────────────────────────
    "TCX": {"name": "TCBS", "sector": "Chứng khoán", "sector_emoji": "📈", "emoji": "📊"},
    "VCK": {"name": "VPS", "sector": "Chứng khoán", "sector_emoji": "📈", "emoji": "📉"},
    "SSI": {"name": "SSI", "sector": "Chứng khoán", "sector_emoji": "📈", "emoji": "🧾"},
    "VPX": {"name": "VPBank Securities", "sector": "Chứng khoán", "sector_emoji": "📈", "emoji": "🏦"},
    "HCM": {"name": "HSC", "sector": "Chứng khoán", "sector_emoji": "📈", "emoji": "📑"},
    "VIX": {"name": "VIX", "sector": "Chứng khoán", "sector_emoji": "📈", "emoji": "🔶"},
    "VND": {"name": "VNDirect", "sector": "Chứng khoán", "sector_emoji": "📈", "emoji": "🔷"},
    "VCI": {"name": "Vietcap", "sector": "Chứng khoán", "sector_emoji": "📈", "emoji": "🔹"},
    "EVS": {"name": "Everest Securities", "sector": "Chứng khoán", "sector_emoji": "📈", "emoji": "⛰️"},
    # ── Bảo hiểm ─────────────────────────────────────────────────────────────
    "BVH": {"name": "Bảo Việt", "sector": "Bảo hiểm", "sector_emoji": "🛡️", "emoji": "🛡️"},
    # ── Bất động sản ─────────────────────────────────────────────────────────
    "VIC": {"name": "Vingroup", "sector": "Bất động sản", "sector_emoji": "🏗️", "emoji": "🏢"},
    "VHM": {"name": "Vinhomes", "sector": "Bất động sản", "sector_emoji": "🏗️", "emoji": "🏡"},
    "VPL": {"name": "Vinpearl", "sector": "Bất động sản", "sector_emoji": "🏗️", "emoji": "🏝️"},
    "VRE": {"name": "Vincom Retail", "sector": "Bất động sản", "sector_emoji": "🏗️", "emoji": "🏬"},
    "NVL": {"name": "Novaland", "sector": "Bất động sản", "sector_emoji": "🏗️", "emoji": "🌆"},
    "BCM": {"name": "Becamex", "sector": "Bất động sản", "sector_emoji": "🏗️", "emoji": "🏙️"},
    "KBC": {"name": "Kinh Bắc", "sector": "Bất động sản", "sector_emoji": "🏗️", "emoji": "🏘️"},
    "KDH": {"name": "Khang Điền", "sector": "Bất động sản", "sector_emoji": "🏗️", "emoji": "☀️"},
    "DXG": {"name": "Đất Xanh", "sector": "Bất động sản", "sector_emoji": "🏗️", "emoji": "🌳"},
    "PDR": {"name": "Phát Đạt", "sector": "Bất động sản", "sector_emoji": "🏗️", "emoji": "🏠"},
    "DIG": {"name": "DIC Corp", "sector": "Bất động sản", "sector_emoji": "🏗️", "emoji": "🏘️"},
    # ── Tiêu dùng thiết yếu ──────────────────────────────────────────────────
    "MCH": {"name": "Masan Consumer", "sector": "Tiêu dùng thiết yếu", "sector_emoji": "🛒", "emoji": "🍜"},
    "VNM": {"name": "Vinamilk", "sector": "Tiêu dùng thiết yếu", "sector_emoji": "🛒", "emoji": "🥛"},
    "MSN": {"name": "Masan Group", "sector": "Tiêu dùng thiết yếu", "sector_emoji": "🛒", "emoji": "🏪"},
    "SAB": {"name": "Sabeco", "sector": "Tiêu dùng thiết yếu", "sector_emoji": "🛒", "emoji": "🍺"},
    "KDC": {"name": "Kido", "sector": "Tiêu dùng thiết yếu", "sector_emoji": "🛒", "emoji": "🍦"},
    "OCH": {"name": "OCH", "sector": "Tiêu dùng thiết yếu", "sector_emoji": "🛒", "emoji": "🏨"},
    "DMX": {"name": "Điện Máy Xanh", "sector": "Tiêu dùng thiết yếu", "sector_emoji": "🛒", "emoji": "📺"},
    "MWG": {"name": "Thế Giới Di Động", "sector": "Tiêu dùng thiết yếu", "sector_emoji": "🛒", "emoji": "📱"},
    # ── Bán lẻ ───────────────────────────────────────────────────────────────
    "FRT": {"name": "FPT Retail", "sector": "Bán lẻ", "sector_emoji": "🛍️", "emoji": "💊"},
    "PNJ": {"name": "PNJ", "sector": "Bán lẻ", "sector_emoji": "🛍️", "emoji": "💎"},
    # ── Công nghệ ────────────────────────────────────────────────────────────
    "FPT": {"name": "FPT", "sector": "Công nghệ", "sector_emoji": "💻", "emoji": "💻"},
    # ── Game ─────────────────────────────────────────────────────────────────
    "VNZ": {"name": "VNG", "sector": "Game", "sector_emoji": "🎮", "emoji": "🎮"},
    # ── Nguyên vật liệu ──────────────────────────────────────────────────────
    "HPG": {"name": "Hòa Phát", "sector": "Nguyên vật liệu", "sector_emoji": "🏭", "emoji": "⚙️"},
    "GVR": {"name": "Tập đoàn Cao su", "sector": "Nguyên vật liệu", "sector_emoji": "🏭", "emoji": "🪵"},
    "DGC": {"name": "Đức Giang", "sector": "Nguyên vật liệu", "sector_emoji": "🏭", "emoji": "🧪"},
    "DCM": {"name": "Đạm Cà Mau", "sector": "Nguyên vật liệu", "sector_emoji": "🏭", "emoji": "🌾"},
    "DPM": {"name": "Đạm Phú Mỹ", "sector": "Nguyên vật liệu", "sector_emoji": "🏭", "emoji": "🌱"},
    "BMP": {"name": "Nhựa Bình Minh", "sector": "Nguyên vật liệu", "sector_emoji": "🏭", "emoji": "🔵"},
    # ── Năng lượng ───────────────────────────────────────────────────────────
    "GAS": {"name": "PV Gas", "sector": "Năng lượng", "sector_emoji": "⛽", "emoji": "🔥"},
    "BSR": {"name": "Lọc dầu Bình Sơn", "sector": "Năng lượng", "sector_emoji": "⛽", "emoji": "🛢️"},
    "PLX": {"name": "Petrolimex", "sector": "Năng lượng", "sector_emoji": "⛽", "emoji": "⛽"},
    "POW": {"name": "PV Power", "sector": "Năng lượng", "sector_emoji": "⛽", "emoji": "⚡"},
    "PVD": {"name": "PV Drilling", "sector": "Năng lượng", "sector_emoji": "⛽", "emoji": "🛠️"},
    # ── Tiện ích ─────────────────────────────────────────────────────────────
    "PGV": {"name": "EVN Genco 3", "sector": "Tiện ích", "sector_emoji": "⚡", "emoji": "⚡"},
    # ── Vận tải ──────────────────────────────────────────────────────────────
    "VJC": {"name": "Vietjet", "sector": "Vận tải", "sector_emoji": "✈️", "emoji": "🟥"},
    "HVN": {"name": "Vietnam Airlines", "sector": "Vận tải", "sector_emoji": "✈️", "emoji": "✈️"},
    "GMD": {"name": "Gemadept", "sector": "Vận tải", "sector_emoji": "✈️", "emoji": "🚢"},
    # ── Công nghiệp ──────────────────────────────────────────────────────────
    "GEE": {"name": "Gelex Electric", "sector": "Công nghiệp", "sector_emoji": "🔧", "emoji": "🔌"},
    "GEX": {"name": "Gelex", "sector": "Công nghiệp", "sector_emoji": "🔧", "emoji": "🔧"},
    "REE": {"name": "REE", "sector": "Công nghiệp", "sector_emoji": "🔧", "emoji": "🌡️"},
    "VGC": {"name": "Viglacera", "sector": "Công nghiệp", "sector_emoji": "🔧", "emoji": "🧱"},
    "CII": {"name": "CII", "sector": "Công nghiệp", "sector_emoji": "🔧", "emoji": "🛣️"},
    "PC1": {"name": "PC1", "sector": "Công nghiệp", "sector_emoji": "🔧", "emoji": "🏗️"},
}

HOSE_TICKERS = set(HOSE_WATCHLIST.keys())


def get_company(ticker: str) -> dict[str, str] | None:
    return HOSE_WATCHLIST.get((ticker or "").strip().upper())
