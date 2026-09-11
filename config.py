import os


def env_int(name: str, default: int = 0) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# Accept both names so existing deployments do not break.
AI_API_KEY = os.getenv("GEMINI_API_KEY", os.getenv("AI_API_KEY", "")).strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
AI_TIMEOUT = max(5, min(env_int("AI_TIMEOUT", 15), 60))
AI_HIGH_CONFIDENCE = 0.90
AI_LOW_CONFIDENCE = 0.50
AI_TIMEOUT_MINUTES = max(1, min(env_int("AI_TIMEOUT_MINUTES", 10), 60))

SPAM_MAX_MESSAGES = max(3, env_int("SPAM_MAX_MESSAGES", 7))
SPAM_WINDOW_SECONDS = max(3, env_int("SPAM_WINDOW_SECONDS", 8))
RAID_JOIN_LIMIT = max(3, env_int("RAID_JOIN_LIMIT", 8))
RAID_WINDOW_SECONDS = max(5, env_int("RAID_WINDOW_SECONDS", 15))
MASS_MENTION_LIMIT = max(3, env_int("MASS_MENTION_LIMIT", 5))
WEBHOOK_LIMIT = max(2, env_int("WEBHOOK_LIMIT", 3))
LOCKDOWN_SECONDS = max(30, env_int("LOCKDOWN_SECONDS", 120))
