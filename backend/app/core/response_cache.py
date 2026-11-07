"""
LiveIQ — Stale-while-revalidate response cache (pure ASGI middleware).

Why this exists: the primary database is a remote Neon instance (~200ms per
round-trip) and most dashboard endpoints run several sequential queries, so
an uncached page load costs 2-8 seconds. The data behind these endpoints is
global (not per-user) and changes on the order of minutes, so we serve it
from memory:

  * fresh  (< ttl)          → served instantly from memory
  * stale  (< ttl + swr)    → served instantly, refreshed in the background
  * miss                    → computed once (single-flight), then cached

Authentication is still enforced: a valid, unexpired access JWT is required
before any cached byte is served. Per-user routes (notifications, watchlist,
auth, writes) are never cached.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass

import structlog

from app.services.auth_service import decode_token

logger = structlog.get_logger()

# (regex, fresh_ttl_seconds, stale_window_seconds)
_RULES: list[tuple[re.Pattern, int, int]] = [
    (re.compile(r"^/dashboard/"), 120, 3600),
    (re.compile(r"^/entities/"), 300, 3600),
    (re.compile(r"^/trends/"), 300, 3600),
    (re.compile(r"^/cities(/|$)"), 300, 3600),
    (re.compile(r"^/competitors/"), 300, 3600),
    (re.compile(r"^/social/"), 300, 3600),
    (re.compile(r"^/pricing/(benchmarks|elasticity/)"), 600, 7200),
    (re.compile(r"^/executive/(kpis|portfolio)$"), 180, 3600),
    (re.compile(r"^/executive/briefing$"), 900, 7200),  # LLM call — expensive
    (re.compile(r"^/recommend/entities$"), 300, 3600),
    (re.compile(r"^/events$"), 300, 3600),
    (re.compile(r"^/psychology/"), 600, 7200),
    (re.compile(r"^/intelligence/[^/]+/forecast$"), 600, 7200),
    (re.compile(r"^/copilot/models$"), 3600, 86400),
    (re.compile(r"^/venues/[^/]+/calendar$"), 300, 3600),
]

MAX_ENTRIES = 600


@dataclass
class _Entry:
    status: int
    headers: list[tuple[bytes, bytes]]
    body: bytes
    fresh_until: float
    stale_until: float


_CACHE: dict[str, _Entry] = {}
_LOCKS: dict[str, asyncio.Lock] = {}
_REFRESHING: set[str] = set()


def _rule_for(path: str) -> tuple[int, int] | None:
    for pattern, ttl, swr in _RULES:
        if pattern.match(path):
            return ttl, swr
    return None


def invalidate_all() -> int:
    n = len(_CACHE)
    _CACHE.clear()
    return n


def cache_stats() -> dict:
    return {"entries": len(_CACHE), "refreshing": len(_REFRESHING)}


async def _capture(app, scope) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    """Run the downstream app and buffer its whole response."""
    status = 500
    headers: list[tuple[bytes, bytes]] = []
    chunks: list[bytes] = []

    receive = _make_receive()

    async def send(message):
        nonlocal status, headers
        if message["type"] == "http.response.start":
            status = message["status"]
            headers = list(message.get("headers", []))
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(scope, receive, send)
    return status, headers, b"".join(chunks)


class ResponseCacheMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "GET":
            return await self.app(scope, receive, send)

        path: str = scope["path"]
        rule = _rule_for(path)
        if rule is None:
            return await self.app(scope, receive, send)

        headers = {k.lower(): v for k, v in scope["headers"]}
        auth = headers.get(b"authorization", b"").decode("latin-1")
        token = auth[7:] if auth.lower().startswith("bearer ") else ""
        payload = decode_token(token) if token else None
        if not payload or payload.get("type") != "access":
            # Let the real app produce the proper 401.
            return await self.app(scope, receive, send)

        ttl, swr = rule
        key = f"{path}?{scope.get('query_string', b'').decode('latin-1')}"
        now = time.monotonic()
        entry = _CACHE.get(key)

        if entry and now < entry.fresh_until:
            return await self._reply(send, entry, "HIT")

        if entry and now < entry.stale_until:
            self._refresh_in_background(key, scope, ttl, swr)
            return await self._reply(send, entry, "STALE")

        # Miss: single-flight so a burst of identical requests computes once.
        lock = _LOCKS.setdefault(key, asyncio.Lock())
        async with lock:
            entry = _CACHE.get(key)
            if entry and time.monotonic() < entry.stale_until:
                return await self._reply(send, entry, "HIT")
            status, hdrs, body = await _capture(self.app, scope)
            if status == 200:
                self._store(key, status, hdrs, body, ttl, swr)
                entry = _CACHE.get(key)
                if entry is not None:
                    return await self._reply(send, entry, "MISS")
        # Non-200 — pass through uncached.
        await send({"type": "http.response.start", "status": status, "headers": hdrs})
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    def _store(key, status, hdrs, body, ttl, swr):
        if b"temporarily unavailable" in body:  # degraded AI fallback — never pin it in cache
            return
        if len(_CACHE) >= MAX_ENTRIES:
            oldest = min(_CACHE, key=lambda k: _CACHE[k].stale_until)
            _CACHE.pop(oldest, None)
            _LOCKS.pop(oldest, None)
        now = time.monotonic()
        # Drop hop-by-hop / stale framing headers; recomputed on reply.
        keep = [(k, v) for k, v in hdrs if k.lower() not in (b"content-length", b"x-cache", b"content-encoding")]
        _CACHE[key] = _Entry(status, keep, body, now + ttl, now + ttl + swr)

    @staticmethod
    async def _reply(send, entry: _Entry, state: str):
        headers = [(k, v) for k, v in entry.headers]
        headers.append((b"content-length", str(len(entry.body)).encode()))
        headers.append((b"x-cache", state.encode()))
        await send({"type": "http.response.start", "status": entry.status, "headers": headers})
        await send({"type": "http.response.body", "body": entry.body})

    def _refresh_in_background(self, key, scope, ttl, swr):
        if key in _REFRESHING:
            return
        _REFRESHING.add(key)

        async def _run():
            try:
                status, hdrs, body = await _capture(self.app, dict(scope))
                if status == 200:
                    self._store(key, status, hdrs, body, ttl, swr)
            except Exception as exc:  # never let a refresh crash the server
                logger.warning("cache refresh failed", key=key, error=str(exc))
            finally:
                _REFRESHING.discard(key)

        asyncio.create_task(_run())


async def warm_cache(app, access_token: str, paths: list[str]) -> None:
    """Populate the cache at startup so the first real user gets instant pages."""
    sem = asyncio.Semaphore(3)

    async def _one(path: str):
        async with sem:
            p, _, qs = path.partition("?")
            scope = {
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "method": "GET", "scheme": "http", "path": p, "raw_path": p.encode(),
                "query_string": qs.encode(), "root_path": "",
                "headers": [(b"authorization", f"Bearer {access_token}".encode()), (b"host", b"localhost")],
                "client": ("127.0.0.1", 0), "server": ("127.0.0.1", 8000),
            }
            try:
                await app(scope, _make_receive(), _noop_send)
            except Exception as exc:
                logger.warning("warm failed", path=path, error=str(exc))

    await asyncio.gather(*[_one(p) for p in paths])


def _make_receive():
    """First call yields the (empty) request body; later calls block, as a
    real client connection would, so BaseHTTPMiddleware's disconnect
    listener doesn't see a bogus second http.request message."""
    sent = False
    never = asyncio.Event()

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await never.wait()
        return {"type": "http.disconnect"}

    return receive


async def _noop_send(message):
    return None
