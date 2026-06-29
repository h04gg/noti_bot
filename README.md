# 📊 IR Monitor — 5 nguồn công bố thông tin

Bot Telegram tự động theo dõi và thông báo khi có tài liệu mới từ 5 trang IR:

| # | Công ty | Kỹ thuật scraping |
|---|---------|-------------------|
| 1 | **Phát Đạt (PDR)** | JSON API ẩn (`/ajax/reports/filter`) |
| 2 | **VPBank** | Playwright headless (Next.js) |
| 3 | **Gelex** | Playwright headless (WordPress JS) |
| 4 | **Eximbank** | Playwright headless (Next.js) |
| 5 | **Vingroup** | HTML SSR (requests + BeautifulSoup) |

---

## 🚀 Cài đặt (5 bước)

### Bước 1 — Tạo Telegram Bot
1. Mở Telegram → tìm **[@BotFather](https://t.me/BotFather)**
2. Gõ `/newbot` → đặt tên → đặt username (kết thúc bằng `bot`)
3. Copy **Bot Token** (dạng `7123456789:AAFxxx...`)
4. Mở bot vừa tạo → gõ `/start`

### Bước 2 — Lấy Chat ID
```bash
pip install requests
TELEGRAM_BOT_TOKEN=<token> python get_chat_id.py
```

### Bước 3 — Push lên GitHub
```bash
git init && git add . && git commit -m "init"
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

### Bước 4 — Thêm Secrets
Vào repo → **Settings → Secrets → Actions → New repository secret**

| Secret | Giá trị |
|--------|---------|
| `TELEGRAM_BOT_TOKEN` | Token từ BotFather |
| `TELEGRAM_CHAT_ID` | Chat ID từ bước 2 |

### Bước 5 — Kích hoạt & Test
Tab **Actions** → chọn workflow → **Run workflow**

Nếu thành công, bot gửi tin xác nhận kèm số lượng tài liệu hiện có từng nguồn.

---

## 📁 Cấu trúc project

```
ir-monitor/
├── .github/workflows/
│   └── monitor.yml          # GitHub Actions (chạy mỗi 10 phút)
├── scrapers/
│   ├── phatdat.py           # JSON API scraper
│   ├── vingroup.py          # HTML SSR scraper  
│   └── playwright_scraper.py # Headless browser (VPBank, Eximbank, Gelex)
├── config.py                # Danh sách nguồn
├── monitor.py               # Script chính
├── get_chat_id.py           # Helper lấy Chat ID
├── requirements.txt
└── README.md
```

---

## ⚠️ Lưu ý về VPBank, Eximbank, Gelex

3 trang này dùng JavaScript để render nội dung (Next.js/React), nên cần **Playwright** (headless Chromium). GitHub Actions đã được cấu hình để cài Playwright tự động.

Nếu trang thay đổi cấu trúc HTML, chỉnh `SITE_SELECTORS` trong `scrapers/playwright_scraper.py`.

---

## 🔧 Chạy thủ công (local)

```bash
pip install -r requirements.txt
playwright install chromium --with-deps

export TELEGRAM_BOT_TOKEN=xxx
export TELEGRAM_CHAT_ID=xxx
python monitor.py
```
