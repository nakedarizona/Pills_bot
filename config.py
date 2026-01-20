import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables")

TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
EVENING_REMINDER_TIME = os.getenv("EVENING_REMINDER_TIME", "20:00")

DB_PATH = "pills_bot.db"
