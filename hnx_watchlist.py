"""Watchlist mã HNX dùng để lọc tin HNX (Tin TCPH)."""

from __future__ import annotations

# Thứ tự = thứ tự gửi Telegram (theo ngành trong sheet).
HNX_WATCHLIST: dict[str, dict[str, str]] = {
    # ── Ngân hàng ────────────────────────────────────────────────────────────
    "ABB": {"name": "An Bình Bank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🟩"},
    "NVB": {"name": "National Citizen", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🔵"},
    "VBB": {"name": "VietBank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🟡"},
    "BAB": {"name": "Bắc Á Bank", "sector": "Ngân hàng", "sector_emoji": "🏦", "emoji": "🟠"},
    # ── Chứng khoán ──────────────────────────────────────────────────────────
    "MBS": {"name": "MB Securities", "sector": "Chứng khoán", "sector_emoji": "📈", "emoji": "📑"},
    "SHS": {"name": "SHS", "sector": "Chứng khoán", "sector_emoji": "📈", "emoji": "🔹"},
    "EVS": {"name": "Everest Securities", "sector": "Chứng khoán", "sector_emoji": "📈", "emoji": "⛰️"},
    # ── Bất động sản ─────────────────────────────────────────────────────────
    "KSF": {"name": "Sunshine Group", "sector": "Bất động sản", "sector_emoji": "🏗️", "emoji": "☀️"},
    "THD": {"name": "Thaiholdings", "sector": "Bất động sản", "sector_emoji": "🏗️", "emoji": "🏢"},
    "HUT": {"name": "Tasco", "sector": "Bất động sản", "sector_emoji": "🏗️", "emoji": "🛣️"},
    # ── Vận tải ──────────────────────────────────────────────────────────────
    "ACV": {"name": "ACV", "sector": "Vận tải", "sector_emoji": "✈️", "emoji": "🛫"},
    "PHP": {"name": "Cảng Hải Phòng", "sector": "Vận tải", "sector_emoji": "✈️", "emoji": "⚓"},
    # ── Công nghiệp ──────────────────────────────────────────────────────────
    "VEA": {"name": "VEAM", "sector": "Công nghiệp", "sector_emoji": "🔧", "emoji": "🚗"},
    # ── Nguyên vật liệu ──────────────────────────────────────────────────────
    "KSV": {"name": "Vinacomin Minerals", "sector": "Nguyên vật liệu", "sector_emoji": "🏭", "emoji": "⛏️"},
    "MSR": {"name": "Masan High-Tech", "sector": "Nguyên vật liệu", "sector_emoji": "🏭", "emoji": "🧪"},
    # ── Năng lượng ───────────────────────────────────────────────────────────
    "PVS": {"name": "PV Technical Services", "sector": "Năng lượng", "sector_emoji": "⛽", "emoji": "🛢️"},
    # ── Tài chính khác ───────────────────────────────────────────────────────
    "F88": {"name": "F88", "sector": "Tài chính khác", "sector_emoji": "💰", "emoji": "💵"},
    # ── Tiện ích ─────────────────────────────────────────────────────────────
    "IDC": {"name": "IDICO", "sector": "Tiện ích", "sector_emoji": "⚡", "emoji": "🏗️"},
    # ── Tiêu dùng ────────────────────────────────────────────────────────────
    "QNS": {"name": "Đường Quảng Ngãi", "sector": "Tiêu dùng", "sector_emoji": "🛒", "emoji": "🍬"},
    "OCH": {"name": "OCH", "sector": "Tiêu dùng", "sector_emoji": "🛒", "emoji": "🏨"},
    "DMX": {"name": "Điện Máy Xanh", "sector": "Tiêu dùng", "sector_emoji": "🛒", "emoji": "📺"},
    "MWG": {"name": "Thế Giới Di Động", "sector": "Tiêu dùng", "sector_emoji": "🛒", "emoji": "📱"},
}


def get_company(ticker: str) -> dict[str, str] | None:
    return HNX_WATCHLIST.get((ticker or "").strip().upper())
