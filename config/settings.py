import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
USDT_ADDRESS = os.getenv("USDT_ADDRESS", "")
BTC_ADDRESS = os.getenv("BTC_ADDRESS", "")
LTC_ADDRESS = os.getenv("LTC_ADDRESS", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/chinatown_market")
WEBAPP_URL = os.getenv("WEBAPP_URL", "")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# Default prices
DEFAULT_NAKED_PRICE = 0.33
DEFAULT_CLOTHED_PRICE = 25.0
