"""Shared slowapi limiter (kept out of main.py so route modules can import it
without a circular import).

Default: RATE_LIMIT_PER_MINUTE (floored at SPA_MIN_PER_MINUTE - a single
dashboard page fires 10-20 parallel calls and SWR refreshes on top).
Auth endpoints use much tighter per-route limits (see app/api/routes/auth.py).
Storage is in-memory per process; set a shared storage_uri for multi-instance.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

SPA_MIN_PER_MINUTE = 240
DEFAULT_LIMIT = f"{max(settings.RATE_LIMIT_PER_MINUTE, SPA_MIN_PER_MINUTE)}/minute"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[DEFAULT_LIMIT],
    config_filename="__no_such_file__",  # see main.py history: avoids slowapi reading .env with locale encoding
    headers_enabled=False,
)
