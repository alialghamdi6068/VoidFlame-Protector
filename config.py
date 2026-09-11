import os


def env_int(name: str, default: int = 0) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


AI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
AI_TIMEOUT = env_int("AI_TIMEOUT", 12)
AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() in {"1", "true", "yes", "on"}

# Safety limits. AI is never allowed to ban/kick members.
AI_TIMEOUT_MINUTES = max(1, min(env_int("AI_TIMEOUT_MINUTES", 10), 60))
AI_HIGH_CONFIDENCE = 0.90
AI_LOW_CONFIDENCE = 0.50

# Protection defaults
SPAM_MAX_MESSAGES = max(3, env_int("SPAM_MAX_MESSAGES", 7))
SPAM_WINDOW_SECONDS = max(3, env_int("SPAM_WINDOW_SECONDS", 8))
RAID_JOIN_LIMIT = max(3, env_int("RAID_JOIN_LIMIT", 8))
RAID_WINDOW_SECONDS = max(5, env_int("RAID_WINDOW_SECONDS", 15))
