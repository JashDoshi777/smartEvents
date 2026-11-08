"""
LiveIQ — Application Configuration
Type-safe settings using pydantic-settings.
Crashes at startup if any required key is missing — intentional.
"""

from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings
import json


class Settings(BaseSettings):
    # ─── App ───────────────────────────────────────────────────
    APP_NAME: str = "LiveIQ"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    SCHEDULER_ENABLED: bool = True      # in-process APScheduler (set false for secondary workers / one-off scripts)

    # ─── CORS ──────────────────────────────────────────────────
    CORS_ORIGINS: str = '["http://localhost:3000"]'

    @property
    def cors_origins_list(self) -> List[str]:
        try:
            origins = json.loads(self.CORS_ORIGINS)
        except Exception:
            return ["http://localhost:3000"]
        # Credentialed CORS must never use a wildcard origin.
        origins = [o for o in origins if isinstance(o, str) and o.strip() and o.strip() != "*"]
        return origins or ["http://localhost:3000"]

    # ─── Database ──────────────────────────────────────────────
    POSTGRES_URL: str
    POSTGRES_SYNC_URL: str
    POSTGRES_PASSWORD: str = ""          # only used by docker-compose; the API reads POSTGRES_URL

    # ─── MongoDB ───────────────────────────────────────────────
    MONGO_URL: str = "mongodb://localhost:27017"   # optional service; app runs fine without it
    MONGO_DB_NAME: str = "liveiq"

    # ─── Redis ─────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"    # optional service; app runs fine without it
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ─── Auth ──────────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ─── Music APIs ────────────────────────────────────────────
    SPOTIFY_CLIENT_ID: Optional[str] = None
    SPOTIFY_CLIENT_SECRET: Optional[str] = None
    YOUTUBE_API_KEY: Optional[str] = None
    LASTFM_API_KEY: Optional[str] = None
    LASTFM_SHARED_SECRET: Optional[str] = None

    # ─── Events APIs ───────────────────────────────────────────
    TICKETMASTER_API_KEY: Optional[str] = None
    BANDSINTOWN_APP_ID: Optional[str] = None
    SONGKICK_API_KEY: Optional[str] = None
    SETLISTFM_API_KEY: Optional[str] = None
    EVENTBRITE_TOKEN: Optional[str] = None
    PREDICT_HQ_TOKEN: Optional[str] = None

    # ─── Entertainment APIs ────────────────────────────────────
    TMDB_API_KEY: Optional[str] = None
    TMDB_ACCESS_TOKEN: Optional[str] = None
    ESPN_API_KEY: Optional[str] = None
    CRICBUZZ_API_KEY: Optional[str] = None

    # ─── Social APIs ───────────────────────────────────────────
    REDDIT_CLIENT_ID: Optional[str] = None
    REDDIT_CLIENT_SECRET: Optional[str] = None
    REDDIT_USER_AGENT: str = "LiveIQ/1.0"
    NEWSAPI_KEY: Optional[str] = None
    TWITTER_BEARER_TOKEN: Optional[str] = None

    # ─── Geo & Maps ────────────────────────────────────────────
    MAPBOX_TOKEN: Optional[str] = None
    GOOGLE_PLACES_API_KEY: Optional[str] = None
    FOURSQUARE_PLACES_API: Optional[str] = None
    FOURSQUARE_CLIENT_ID: Optional[str] = None
    FOURSQUARE_CLIENT_SECRET: Optional[str] = None
    OPENMETEO_BASE_URL: str = "https://api.open-meteo.com/v1"

    # ─── Google Trends ─────────────────────────────────────────
    PYTRENDS_LANGUAGE: str = "en-IN"
    PYTRENDS_TIMEZONE: int = 330  # IST = UTC+5:30

    # ─── AI (Groq) ─────────────────────────────────────────────
    # Groq is OpenAI-compatible — base URL: https://api.groq.com/openai/v1
    GROQ_API_KEY: Optional[str] = None
    # Best versatile model: llama-3.3-70b-versatile (128K context, fast)
    # Alternative (most capable): moonshotai/kimi-k2-instruct
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    # Keep Gemini as optional fallback
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-pro"

    # ─── Rate Limiting ─────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",  # Ignore unknown env vars — safe for dev
        # Secrets pasted into hosting dashboards often carry a trailing newline/space
        # (e.g. database "neondb\n" does not exist) — trim every string setting.
        "str_strip_whitespace": True,
    }

    def secret_key_warnings(self) -> List[str]:
        """Human-readable problems with SECRET_KEY (never includes the key)."""
        k = self.SECRET_KEY or ""
        problems = []
        if len(k) < 32:
            problems.append("SECRET_KEY is shorter than 32 characters")
        low = k.lower()
        if any(w in low for w in ("change-me", "changeme", "change_me", "your-secret", "your_secret", "secret-key", "supersecret", "default", "example", "dev-secret", "test-secret")):
            problems.append("SECRET_KEY looks like a placeholder/default value")
        if len(set(k)) < 8:
            problems.append("SECRET_KEY has very low entropy")
        return problems

    def is_api_configured(self, api_name: str) -> bool:
        """Check if an API has credentials configured (not None AND not empty string)."""
        key_map = {
            "spotify": ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"],
            "youtube": ["YOUTUBE_API_KEY"],
            "ticketmaster": ["TICKETMASTER_API_KEY"],
            "tmdb": ["TMDB_ACCESS_TOKEN"],
            "groq": ["GROQ_API_KEY"],
            "gemini": ["GEMINI_API_KEY"],
            "newsapi": ["NEWSAPI_KEY"],
            "reddit": ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"],
            "lastfm": ["LASTFM_API_KEY"],
            "mapbox": ["MAPBOX_TOKEN"],
            "eventbrite": ["EVENTBRITE_TOKEN"],
            "predicthq": ["PREDICT_HQ_TOKEN"],
            "google_places": ["GOOGLE_PLACES_API_KEY"],
            "foursquare": ["FOURSQUARE_PLACES_API"],
        }
        keys = key_map.get(api_name.lower(), [])
        return all(
            getattr(self, k) is not None and getattr(self, k) != ""
            for k in keys
        )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
