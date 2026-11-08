"""Error boundary, JSON error shapes, security headers, JWT pinning, SQL helpers."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import exc as sa_exc

from app.api.routes import auth as auth_routes
from app.core.config import settings
from app.core.errors import classify_exception, register_exception_handlers
from app.core.middleware import ErrorBoundaryMiddleware, RequestContextMiddleware
from app.core.sql import escape_like
from app.services import auth_service
from app.services.auth_service import create_access_token, create_refresh_token, decode_token


def _app():
    app = FastAPI()

    class Body(BaseModel):
        password: str
        n: int

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret internal detail: postgres://user:pw@host/db")

    @app.get("/db-down")
    async def db_down():
        raise sa_exc.TimeoutError("QueuePool limit of size 8 overflow 12 reached")

    @app.get("/teapot")
    async def teapot():
        raise HTTPException(418, "short and stout")

    @app.post("/val")
    async def val(b: Body):
        return {}

    app.add_middleware(ErrorBoundaryMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    register_exception_handlers(app)
    return app


def _c(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t")


ORIGIN = {"Origin": "http://localhost:3000"}


async def test_unhandled_exception_is_json_500_with_cors_and_no_leak():
    async with _c(_app()) as c:
        r = await c.get("/boom", headers=ORIGIN)
    assert r.status_code == 500
    j = r.json()
    assert j["error"] == "internal_error" and j["request_id"]
    assert "postgres://" not in r.text and "secret" not in r.text
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert r.headers["x-request-id"] == j["request_id"]


async def test_pool_exhaustion_is_503_with_retry_after_and_cors():
    async with _c(_app()) as c:
        r = await c.get("/db-down", headers=ORIGIN)
    assert r.status_code == 503
    assert r.headers["retry-after"] == "5"
    assert r.json()["error"] == "service_unavailable"
    assert "QueuePool" not in r.text
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


async def test_http_exception_keeps_detail_and_adds_error_code():
    async with _c(_app()) as c:
        r = await c.get("/teapot")
    assert r.status_code == 418 and r.json()["detail"] == "short and stout" and r.json()["request_id"]


async def test_validation_error_does_not_echo_input():
    async with _c(_app()) as c:
        r = await c.post("/val", json={"password": "hunter2-very-secret", "n": "x"})
    assert r.status_code == 422
    assert "hunter2" not in r.text
    d = r.json()["detail"]
    assert isinstance(d, list) and set(d[0]) == {"loc", "msg", "type"}


async def test_security_headers_and_request_id_passthrough():
    async with _c(_app()) as c:
        r = await c.get("/teapot", headers={"X-Request-ID": "abcdef123456"})
        r2 = await c.get("/teapot", headers={"X-Request-ID": "bad id\r\nx"})
    assert r.headers["x-request-id"] == "abcdef123456"
    assert r2.headers["x-request-id"] != "bad id\r\nx"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"]
    assert r.headers["x-frame-options"] == "DENY"


def test_classify_exception_mapping():
    assert classify_exception(sa_exc.IntegrityError("s", {}, Exception()))[0] == 409
    assert classify_exception(sa_exc.DataError("s", {}, Exception()))[0] == 400
    assert classify_exception(sa_exc.OperationalError("s", {}, Exception()))[0] == 503
    assert classify_exception(asyncio.TimeoutError())[0] == 503
    assert classify_exception(ValueError("x"))[0] == 500


# ── JWT ────────────────────────────────────────────────────────────────────────
def test_jwt_roundtrip_and_claims():
    uid = uuid4()
    p = decode_token(create_access_token(uid, "viewer"))
    assert p["sub"] == str(uid) and p["type"] == "access" and p["jti"] and p["iat"]
    r = decode_token(create_refresh_token(uid, 3))
    assert r["type"] == "refresh" and r["ver"] == 3


def test_jwt_rejects_none_alg_wrong_key_expired_and_garbage():
    uid = str(uuid4())
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    unsigned = jwt.encode({"sub": uid, "type": "access", "exp": exp}, "", algorithm="HS256")
    forged_none = ".".join([
        "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0",  # {"alg":"none","typ":"JWT"}
        unsigned.split(".")[1], "",
    ])
    assert decode_token(forged_none) is None
    assert decode_token(unsigned) is None  # signed with a different key
    expired = jwt.encode({"sub": uid, "type": "access", "exp": datetime.now(timezone.utc) - timedelta(seconds=5)},
                         settings.SECRET_KEY, algorithm="HS256")
    assert decode_token(expired) is None
    noexp = jwt.encode({"sub": uid, "type": "access"}, settings.SECRET_KEY, algorithm="HS256")
    assert decode_token(noexp) is None
    for junk in ("", "abc", "a.b.c", "x" * 10000, None):
        assert decode_token(junk) is None


def test_jwt_algorithm_is_pinned_to_hmac():
    assert auth_service.JWT_ALGORITHM in {"HS256", "HS384", "HS512"}


async def test_password_hashing_and_dummy_verify():
    h = await auth_service.hash_password_async("correct horse battery")
    assert h.startswith("$2") and "$12$" in h
    assert await auth_service.verify_password_async("correct horse battery", h)
    assert not await auth_service.verify_password_async("wrong", h)
    assert not await auth_service.verify_password_async("anything", None)  # unknown user path


def test_login_lockout_window(monkeypatch):
    key = ("1.2.3.4", "victim@example.com")
    auth_routes._FAILED.pop(key, None)
    assert auth_routes._lock_remaining(key) == 0
    for _ in range(auth_routes.MAX_FAILED_LOGINS):
        auth_routes._FAILED[key].append(auth_routes.time.monotonic())
    assert auth_routes._lock_remaining(key) > 0
    other = ("5.6.7.8", "victim@example.com")  # different IP is not locked out
    assert auth_routes._lock_remaining(other) == 0
    auth_routes._FAILED.pop(key, None)


def test_register_schema_normalises_and_ignores_role():
    r = auth_routes.RegisterRequest(email="  Foo@Example.COM ", password="longenough1", full_name="  Ann \x00 Lee ", role="executive")
    assert r.email == "foo@example.com" and r.full_name == "Ann  Lee"
    assert not hasattr(r, "role")
    with pytest.raises(Exception):
        auth_routes.RegisterRequest(email="a@b.co", password="        ", full_name="x")
    with pytest.raises(Exception):
        auth_routes.RegisterRequest(email="a@b.co", password="x" * 200, full_name="x")


def test_escape_like_neutralises_wildcards():
    assert escape_like("50%_off\\") == "50\\%\\_off\\\\"


def test_cors_never_wildcard(monkeypatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS", '["*", "http://a.test"]')
    assert settings.cors_origins_list == ["http://a.test"]


def test_secret_key_warnings_never_contain_the_key(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "changeme")
    w = settings.secret_key_warnings()
    assert w and all("changeme" not in x for x in w)
