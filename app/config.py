"""Sozlamalar: hamma narsa muhit o'zgaruvchilaridan o'qiladi."""
import os

try:  # lokal ishlatishda .env o'qiladi; Docker/Render'da kerak emas
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
SITE_URL = os.environ["SITE_URL"].rstrip("/")
API_TOKEN = os.environ["BOT_API_TOKEN"]
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").rstrip("/")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
PORT = int(os.environ.get("PORT", 10000))
