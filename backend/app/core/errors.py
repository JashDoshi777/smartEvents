"""Structured JSON error handling.

Every error leaves the API as JSON of the shape
    {"detail": <str|list>, "error": "<code>", "request_id": "<id>"}
(`detail` kept for backwards compatibility with the SPA). Stack traces,
SQL text and request bodies are never returned; they are logged server side
with the request id.
"""
from __future__ import annotations

import asyncio

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import exc as sa_exc
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings

logger = structlog.get_logger()

RETRY_AFTER_SECONDS = "5"

try:  # asyncpg is always present with this stack, but never hard-fail on import
    import asyncpg
    _PG_CONN_ERRORS: tuple = (asyncpg.PostgresConnectionError, asyncpg.InterfaceError,
                               asyncpg.CannotConnectNowError, asyncpg.TooManyConnectionsError)
except Exception:  # pragma: no cover
    _PG_CONN_ERRORS = ()

_UNAVAILABLE = (
    sa_exc.TimeoutError,          # pool exhausted (pool_timeout)
    sa_exc.OperationalError,      # connection lost / server closed / statement timeout
    sa_exc.InterfaceError,
    asyncio.TimeoutError,
    TimeoutError,
    ConnectionError,
    OSError,
) + _PG_CONN_ERRORS


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request.headers.get("x-request-id", "-")


def error_response(request: Request, status: int, code: str, detail, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"detail": detail, "error": code, "request_id": request_id_of(request)},
        headers=headers,
    )


def classify_exception(exc: BaseException) -> tuple[int, str, str, dict]:
    """Map an arbitrary exception to (status, code, public message, headers)."""
    if isinstance(exc, sa_exc.DBAPIError):
        orig = getattr(exc, "orig", None)
        code = str(getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None) or "")
        if code.startswith("22"):   # data exception (bad text/encoding/NUL byte, out of range ...)
            return 400, "bad_request", "Invalid value in request", {}
        if code.startswith("23"):   # integrity constraint violation
            return 409, "conflict", "The request conflicts with existing data", {}
    if isinstance(exc, sa_exc.IntegrityError):
        return 409, "conflict", "The request conflicts with existing data", {}
    if isinstance(exc, sa_exc.DataError):
        return 400, "bad_request", "Invalid value in request", {}
    if isinstance(exc, _UNAVAILABLE) or (isinstance(exc, sa_exc.DBAPIError) and exc.connection_invalidated):
        return 503, "service_unavailable", "Database temporarily unavailable, please retry", {"Retry-After": RETRY_AFTER_SECONDS}
    return 500, "internal_error", "Internal server error", {}


async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    headers = dict(getattr(exc, "headers", None) or {})
    code = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
            405: "method_not_allowed", 409: "conflict", 422: "validation_error", 429: "rate_limited"}.get(exc.status_code, "http_error")
    return error_response(request, exc.status_code, code, exc.detail, headers)


async def _validation_handler(request: Request, exc: RequestValidationError):
    # Strip `input`/`ctx`: they echo the raw request (passwords!) and can hold
    # non-JSON-serialisable exception objects.
    errors = [{"loc": list(e.get("loc", [])), "msg": str(e.get("msg", "")), "type": e.get("type", "")} for e in exc.errors()]
    return error_response(request, 422, "validation_error", errors)


async def _db_handler(request: Request, exc: Exception):
    status, code, msg, headers = classify_exception(exc)
    logger.error("db error", status=status, exc_type=type(exc).__name__, request_id=request_id_of(request),
                 path=request.url.path)
    return error_response(request, status, code, msg, headers)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    # Registered on specific classes (not bare Exception) so they run inside
    # CORSMiddleware and the JSON error carries CORS headers.
    for cls in (sa_exc.SQLAlchemyError, asyncio.TimeoutError, ConnectionError):
        app.add_exception_handler(cls, _db_handler)
