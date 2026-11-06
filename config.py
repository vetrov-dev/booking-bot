"""Settings from .env plus the business catalog (services, masters, hours)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x}
DB_PATH = BASE_DIR / os.getenv("DB_PATH", "data/bookings.db")
UTC_OFFSET = int(os.getenv("UTC_OFFSET", "3"))          # business time zone, hours from UTC (Moscow = 3)
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Барбершоп «Бритва»")
ADDRESS = os.getenv("ADDRESS", "ул. Примерная, 1")
PHONE = os.getenv("PHONE", "+7 900 000-00-00")

OPEN_HOUR = int(os.getenv("OPEN_HOUR", "10"))
CLOSE_HOUR = int(os.getenv("CLOSE_HOUR", "21"))
SLOT_MINUTES = int(os.getenv("SLOT_MINUTES", "30"))      # grid of start times
DAYS_AHEAD = int(os.getenv("DAYS_AHEAD", "14"))          # how far ahead clients can book
DAYS_OFF = {int(x) for x in os.getenv("DAYS_OFF", "").split(",") if x}   # 0 = Monday ... 6 = Sunday
MIN_LEAD_MINUTES = int(os.getenv("MIN_LEAD_MINUTES", "60"))              # no bookings closer than this
REMIND_HOURS = [int(x) for x in os.getenv("REMIND_HOURS", "24,2").split(",") if x]


@dataclass(frozen=True)
class Service:
    code: str
    title: str
    minutes: int
    price: int


SERVICES = [
    Service("cut", "Мужская стрижка", 60, 1500),
    Service("beard", "Стрижка бороды", 30, 800),
    Service("combo", "Стрижка + борода", 90, 2100),
    Service("kids", "Детская стрижка", 45, 1000),
]
MASTERS = ["Алексей", "Дмитрий", "Ирина"]

SERVICE_BY_CODE = {s.code: s for s in SERVICES}
