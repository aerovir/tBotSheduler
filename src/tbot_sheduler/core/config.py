from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
CHANNEL_USERNAME: str = os.getenv("CHANNEL_USERNAME", "")
WEB_APP_URL: str = os.getenv("WEB_APP_URL", "")
DATABASE_URL: str = os.getenv(
    "DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'bot.db'}"
)

# External API (будущие милстоуны)
INTEGRATION_ENCRYPTION_KEY: str | None = os.getenv("INTEGRATION_ENCRYPTION_KEY")
EXTERNAL_API_CORS_ORIGINS: str = os.getenv("EXTERNAL_API_CORS_ORIGINS", "*")

# Bot settings
BOT_VERSION = "0.1.0"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = BASE_DIR / "logs"
DB_PATH = BASE_DIR / "bot.db"
