"""
LiveIQ — Auth Routes (Sprint 7A)
Register / login / refresh / me. JWT access tokens (short-lived) +
refresh tokens (long-lived), bcrypt password hashing.
"""

import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.limiter import limiter
from app.models.user import User, UserRole
from app.api.deps import get_current_user, invalidate_user_cache
from app.services.auth_service import (
    hash_password_async, verify_password_async, create_access_token, create_refresh_token, decode_token,
)

router = APIRouter()
logger = structlog.get_logger()

# ── Brute-force protection ────────────────────────────────────────────────────
# Two layers: (1) slowapi per-IP ceilings on the endpoints below, (2) a
# failed-login lockout keyed by (client ip, email): 5 failures in 10 minutes
# -> 429 + Retry-After until the window slides. Keyed by ip+email (not email
# alone) so an attacker can't lock a victim out from another address.
# In-memory / per-process, like the limiter; use a shared store if scaled out.
MAX_FAILED_LOGINS = 5
LOCKOUT_WINDOW_S = 600
_FAILED: dict[tuple[str, str], deque] = defaultdict(deque)
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "-"


def _lock_remaining(key: tuple[str, str]) -> int:
    q = _FAILED.get(key)
    if not q:
        return 0
    now = time.monotonic()
    while q and now - q[0] > LOCKOUT_WINDOW_S:
        q.popleft()
    if not q:
        _FAILED.pop(key, None)
        return 0
    return int(LOCKOUT_WINDOW_S - (now - q[0])) + 1 if len(q) >= MAX_FAILED_LOGINS else 0


def _norm_email(email: str) -> str:
    return email.strip().lower()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128, description="8-128 characters")
    full_name: str = Field(..., min_length=1, max_length=255)
    # No client-settable `role` field. Every self-registered account is a
    # VIEWER (extra fields such as "role" are ignored, never mass-assigned).
    # Elevating a role is an admin/DB action.

    @field_validator("password")
    @classmethod
    def password_not_blank(cls, v: str) -> str:
        # min_length=8 counts whitespace, so "        " (8 spaces) would
        # otherwise pass validation and hash successfully.
        if not v.strip():
            raise ValueError("Password cannot be blank or only whitespace")
        return v

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = _CTRL.sub("", v).strip()
        if not v:
            raise ValueError("full_name cannot be blank")
        return v

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return _norm_email(v)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=128)

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return _norm_email(v)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., max_length=4096)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def _user_public(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_verified": user.is_verified,
    }


@router.post("/register", summary="Create a new account", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def register(request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User.id).where(func.lower(User.email) == payload.email))
    if existing.first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(
        email=payload.email,
        hashed_password=await hash_password_async(payload.password),
        full_name=payload.full_name,
        role=UserRole.VIEWER.value,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:  # lost a registration race on the unique email
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    await db.refresh(user)

    return {
        "user": _user_public(user),
        "tokens": TokenResponse(
            access_token=create_access_token(user.id, user.role),
            refresh_token=create_refresh_token(user.id, user.token_version),
        ),
    }


@router.post("/login", summary="Log in with email + password")
@limiter.limit("30/minute")
async def login(request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    key = (_client_ip(request), payload.email)
    wait = _lock_remaining(key)
    if wait:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed login attempts. Try again later.",
                            headers={"Retry-After": str(wait)})

    result = await db.execute(select(User).where(func.lower(User.email) == payload.email))
    user = result.scalar_one_or_none()

    # Always run one bcrypt verify (against a dummy hash if no such user) so
    # response time and the error are identical for "no such user" and
    # "wrong password" - no email enumeration via body or timing.
    ok = await verify_password_async(payload.password, user.hashed_password if user else None)
    if user is None or not ok:
        _FAILED[key].append(time.monotonic())
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")

    _FAILED.pop(key, None)
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "user": _user_public(user),
        "tokens": TokenResponse(
            access_token=create_access_token(user.id, user.role),
            refresh_token=create_refresh_token(user.id, user.token_version),
        ),
    }


@router.post("/refresh", summary="Exchange a refresh token for a new access token")
@limiter.limit("60/minute")
async def refresh_token(request: Request, body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    # Same UUID validation as get_current_user (deps.py) — a malformed
    # `sub` in an otherwise-valid token must cleanly 401, not fall through
    # to the DB layer and risk an unhandled ValueError/DataError (500).
    try:
        user_uid = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token payload")

    result = await db.execute(select(User).where(User.id == user_uid))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or deactivated")

    # A refresh token minted before the user's current token_version (i.e.
    # revoked by a logout) is a stale/potentially-leaked token being replayed — reject it outright rather
    # than silently honoring it.
    if payload.get("ver") != user.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token has been revoked")

    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id, user.token_version),
    )


@router.post("/logout", summary="Revoke all refresh tokens for the current user")
async def logout(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Bumping token_version invalidates every refresh token issued so far
    # (this session's and any other device's) in one step — the access
    # token already in the caller's hand still works until it naturally
    # expires (access tokens don't carry/check token_version, by design),
    # but no refresh token minted before this call can mint a new one.
    # `user` may come from the in-memory auth cache (a detached object from
    # another session), so mutate a fresh row bound to THIS session.
    fresh = await db.get(User, user.id)
    if fresh is not None:
        fresh.token_version += 1
        await db.commit()
    invalidate_user_cache(user.id)
    return {"status": "logged_out"}


@router.get("/me", summary="Get the currently authenticated user")
async def get_me(user: User = Depends(get_current_user)):
    return _user_public(user)
