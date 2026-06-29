"""
Lấy Chat ID Telegram — chạy 1 lần sau khi tạo bot và gõ /start
    
    TELEGRAM_BOT_TOKEN=xxx python get_chat_id.py
"""
import os, requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or input("Nhập Bot Token: ").strip()
resp = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", timeout=10)
data = resp.json()

if not data.get("ok"):
    print("❌ Token không hợp lệ:", data); exit(1)

updates = data.get("result", [])
if not updates:
    print("⚠️  Chưa có tin. Hãy mở bot trong Telegram, gõ /start rồi chạy lại."); exit(1)

seen = set()
for u in updates:
    msg = u.get("message") or u.get("channel_post") or {}
    chat = msg.get("chat", {})
    cid = chat.get("id")
    if cid and cid not in seen:
        seen.add(cid)
        print(f"✅ Chat ID: {cid}  |  Type: {chat.get('type')}  |  Name: {chat.get('title') or chat.get('first_name','')}")

print("\n→ Copy Chat ID trên vào GitHub Secrets với tên TELEGRAM_CHAT_ID")
