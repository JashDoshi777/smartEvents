"""Pure-ASGI middlewares: request id + access log + security headers, and an
error boundary that turns any unhandled exception into a JSON 500/503.

Stack order in main.py (outermost first):
    CORS -> GZip -> RequestContext -> ResponseCache -> ErrorBoundary -> SlowAPI -> routes
ErrorBoundary sits INSIDE CORS, so even 500s carry Access-Control-* headers
(Starlette's built-in ServerErrorMiddleware is outside CORS, which is why bare
`@app.exception_handler(Exception)` responses lacked them), and inside the
response cache, so error bodies are never cached.
"""
from __future__ import annotations

import json
import re
import time
import uuid

import structlog

from app.core.config import settings
from app.core.errors import classify_exception

logger = structlog.get_logger()

_RID_OK = re.compile(r"^[A-Za-z0-9._\-]{8,64}$")

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
]
_HSTS = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
# Swagger UI needs inline scripts/styles and a CDN; only loosen CSP for docs.
_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        raw = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        rid = raw if _RID_OK.match(raw) else uuid.uuid4().hex[:16]
        scope.setdefault("state", {})["request_id"] = rid
        structlog.contextvars.bind_contextvars(request_id=rid)
        start = time.perf_counter()
        status_holder = {"status": 500}
        is_doc = scope["path"].startswith(_DOC_PATHS)
        is_auth = scope["path"].startswith("/auth")

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = [(k, v) for k, v in message.get("headers", [])
                           if k.lower() not in (b"x-request-id", b"server")]
                headers.append((b"x-request-id", rid.encode()))
                existing = {k.lower() for k, _ in headers}
                if not is_doc:
                    headers += [h for h in SECURITY_HEADERS if h[0] not in existing]
                else:
                    headers += [h for h in SECURITY_HEADERS[:5] if h[0] not in existing]
                if settings.APP_ENV == "production":
                    headers.append(_HSTS)
                if is_auth and b"cache-control" not in existing:
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            ms = round((time.perf_counter() - start) * 1000, 1)
            logger.info("access", method=scope["method"], path=scope["path"],
                        status=status_holder["status"], ms=ms,
                        client=(scope.get("client") or ("-",))[0])
            structlog.contextvars.clear_contextvars()


class ErrorBoundaryMiddleware:
    """Catch anything the route layer did not handle and answer with JSON."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def send_wrapper(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:  # noqa: BLE001 - this IS the last line of defence
            rid = (scope.get("state") or {}).get("request_id", "-")
            status, code, msg, extra = classify_exception(exc)
            # Full detail goes to the log only (never the response).
            logger.error("unhandled exception", request_id=rid, path=scope.get("path"),
                         status=status, exc_type=type(exc).__name__, exc_info=status >= 500 and status != 503)
            if started:
                raise  # response already streaming; cannot change it
            body = json.dumps({"detail": msg, "error": code, "request_id": rid}).encode()
            headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
            headers += [(k.lower().encode(), v.encode()) for k, v in extra.items()]
            await send({"type": "http.response.start", "status": status, "headers": headers})
            await send({"type": "http.response.body", "body": body})
