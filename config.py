import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("8873576471:AAGfACDjylwW-1vtdV1ZlnWeCJW7ktyyFhU", "")

_admin_raw = os.getenv("8940203655", "")
ADMIN_IDS = set(int(x.strip()) for x in _admin_raw.split(",") if x.strip())

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

REFERRAL_BONUS = float(os.getenv("REFERRAL_BONUS", "0.05"))


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
