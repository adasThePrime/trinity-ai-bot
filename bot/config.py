from __future__ import annotations

import sys
import os

from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
TYPING_STATUS_INTERVAL: float = float(os.getenv("TYPING_STATUS_INTERVAL", "5.0"))
STREAM_ENABLED: bool = os.getenv("STREAM_ENABLED", "false").lower() == "true"
STREAM_DRAFT_INTERVAL: int = float(os.getenv("STREAM_DRAFT_INTERVAL", "1.5"))
STREAM_CHUNK_SIZE: int = int(os.getenv("STREAM_CHUNK_SIZE", "64"))
INLINE_QUERY_ENABLED: bool = os.getenv("INLINE_QUERY_ENABLED", "false").lower() == "true"
ADMIN_IDS: set[int] = {
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
}

# Maintenance
MAINTENANCE_MODE: bool = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"
MAINTENANCE_MESSAGE: str = os.getenv(
    "MAINTENANCE_MESSAGE",
    "The bot is currently under maintenance. Please try again later."
)

# MongoDB
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "trinity_bot")

# Cache
CACHE_MAX_USERS: int = int(os.getenv("CACHE_MAX_USER", "100"))

# Rate Limits
# Empty dict {} means no rate limit for that category.
# "cooldown" is optional, omit it to rate-limit for the window duration only.
RATE_LIMITS_USER: dict[str, dict] = {
    "per_5s":  {"label": "Burst", "max": 2,  "window": 5, "cooldown": 300},
    "per_min": {"label": "Minute", "max": 5, "window": 60},
    "per_hr":  {"label": "Hourly", "max": 45, "window": 3600},
    "per_day": {"label": "Daily", "max": 100, "window": 86400}
}
RATE_LIMITS_APPROVED_USER: dict[str, dict] | None = {
    "per_5s":  {"label": "Burst", "max": 2,  "window": 5, "cooldown": 300}
} # None = same as RATE_LIMITS_USER
# Rate limits imposed for more than below seconds or more will be stored in the database.
RATE_LIMITS_DB_THRESHOLD: int = int(os.getenv("RATE_LIMITS_DB_THRESHOLD", "3600"))

# Httpx
HTTPX_PROXY_URL: str = os.getenv("HTTPX_PROXY_URL", "")

# OpenRouter
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_TIMEOUT: int = int(os.getenv("OPENROUTER_TIMEOUT", "300"))
OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_MODELS: list[dict[str, str]] = [
    {"name": "Step 3.5 Flash", "id": "stepfun/step-3.5-flash:free"}
]
OPENROUTER_DEFAULT_MODEL: str = os.getenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")

# ZAI
USE_ZAI: bool = os.getenv("USE_ZAI", "false").lower() == "true"
ZAI_TIMEOUT: float = float(os.getenv("ZAI_TIMEOUT", "300.0"))
ZAI_MODELS: list[dict[str, str]] = [
    {"name": "GLM 4.7", "id": "glm-4.7"},
    {"name": "GLM 4.7 Think", "id": "glm-4.7-thinking"},
    {"name": "GLM 5", "id": "glm-5"},
    {"name": "GLM 5 Think", "id": "glm-5-thinking"}
]
ZAI_DEFAULT_MODEL: str = os.getenv("ZAI_DEFAULT_MODEL", "glm-4.7-thinking")

# Limits
MAX_TOOL_ROUNDS: int = int(os.getenv("MAX_TOOL_ROUNDS", "7"))
MAX_CONTEXT_MESSAGES: int = int(os.getenv("MAX_CONTEXT_MESSAGES", "20"))
MAX_CONTEXT_CHARS: int = int(os.getenv("MAX_CONTEXT_CHARS", "24000"))

# Search Tool
MAX_SEARCH_RESULTS: int = int(os.getenv("MAX_SEARCH_RESULTS", "10"))
DDGS_TIMEOUT: int = int(os.getenv("DDGS_TIMEOUT", "30"))
DDGS_MAX_RETRIES: int = int(os.getenv("DDGS_MAX_RETRIES", "3"))
DDGS_RETRY_DELAY: float = float(os.getenv("DDGS_RETRY_DELAY", "2.0"))
DDGS_API_URL: str = os.getenv("DDGS_API_URL", "http://localhost:8000")
SEARCH_ENGINES: dict[str, set[str]] = {
    "text":   {"brave", "duckduckgo", "google", "grokipedia", "wikipedia", "yahoo"},
    "images": {"duckduckgo"},
    "news":   {"bing", "duckduckgo", "yahoo"},
    "videos": {"duckduckgo"}
}

# Time Tool
MAX_TIMEZONES_PER_CALL: int = int(os.getenv("MAX_TIMEZONES_PER_CALL", "10"))

# Currency Tool
FRANKFURTER_BASE_URL: str = os.getenv("FRANKFURTER_BASE_URL", "https://api.frankfurter.dev/v1")
MAX_CURRENCY_SYMBOLS: int = int(os.getenv("MAX_CURRENCY_SYMBOLS", "10"))

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
_LOG_LEVEL_PREFIX = "LOG_LEVEL_"
LOG_LEVELS: dict[str, str] = {
    key[len(_LOG_LEVEL_PREFIX):]: value.upper()
    for key, value in os.environ.items()
    if key.startswith(_LOG_LEVEL_PREFIX) and len(key) > len(_LOG_LEVEL_PREFIX) and value
}


if not BOT_TOKEN:
    print("Error: BOT_TOKEN is not set in the environment variables")
    sys.exit(1)

if not USE_ZAI and not OPENROUTER_API_KEY:
    print("Error: OPENROUTER_API_KEY is not set")
    sys.exit(1)

if LOG_LEVEL not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
    print(f"Error: Invalid LOG_LEVEL '{LOG_LEVEL}'. Must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL.")
    sys.exit(1)