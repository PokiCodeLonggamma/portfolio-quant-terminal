"""Configuration centralisée."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    ROOT = Path(__file__).resolve().parent.parent
    DB_PATH = ROOT / os.getenv("DB_PATH", "data/scanner.db")

    SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "ShortSqueezeScanner contact@example.com")

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # LLM (Google Gemini)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
    AI_CONVICTION_THRESHOLD = float(os.getenv("AI_CONVICTION_THRESHOLD", 4))
    CACHE_TTL_HOURS = float(os.getenv("CACHE_TTL_HOURS", 4))

    # Seuils Pilier 1
    MIN_SHORT_FLOAT = float(os.getenv("MIN_SHORT_FLOAT", 0.25))
    MIN_DAYS_TO_COVER = float(os.getenv("MIN_DAYS_TO_COVER", 5))

    # Seuils Pilier 2
    MAX_PUT_CALL_RATIO = float(os.getenv("MAX_PUT_CALL_RATIO", 0.8))

    # Scoring
    MIN_SCORE_ALERT = float(os.getenv("MIN_SCORE_ALERT", 5))
    MIN_MARKET_CAP = float(os.getenv("MIN_MARKET_CAP", 300_000_000))

    @classmethod
    def telegram_enabled(cls) -> bool:
        return bool(cls.TELEGRAM_BOT_TOKEN and cls.TELEGRAM_CHAT_ID)

    @classmethod
    def llm_enabled(cls) -> bool:
        return bool(cls.GEMINI_API_KEY)
