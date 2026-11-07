"""
LiveIQ — Auth Routes (Sprint 7A)
Register / login / refresh / me. JWT access tokens (short-lived) +
refresh tokens (long-lived), bcrypt password hashing.
"""

from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User, UserRole
from app.api.deps import get_current_user, invalidate_user_cache
from app.services.auth_service import (
    hash_password, verify_password, create_access_token, create_refresh_token, decode_token,
)

router = APIRouter()
logger = structlog.get_logger()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Minimum 8 characters")
    full_name: str = Field(..., min_length=1, max_length=255)
    # No client-settable `role` field. Every self-registered account is a
    # VIEWER — a prior version accepted an arbitrary UserRole here, which
    # meant anyone could self-register as e.g. "executive" since nothing
    # validated it against the caller's actual privileges. Elevating a
    # user's role is an admin action (not yet built — no admin route
    # exists yet — but the gap must not be reopened by adding one field back).

    @field_validator("password")
    @classmethod
    def password_not_blank(cls, v: str) -> str:
        # min_length=8 counts whitespace, so "        " (8 spaces) would
        # otherwise pass validation and hash successfully.
        if not v.strip():
            raise ValueError("Password cannot be blank or only whitespace")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


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
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == request.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(
        email=request.email,
        hashed_password=hash_password(request.password),
        full_name=request.full_name,
        role=UserRole.VIEWER.value,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {
        "user": _user_public(user),
        "tokens": TokenResponse(
            access_token=create_access_token(user.id, user.role),
            refresh_token=create_refresh_token(user.id, user.token_version),
        ),
    }


@router.post("/login", summary="Log in with email + password")
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    # Deliberately identical error for "no such user" and "wrong password" —
    # distinguishing them lets an attacker enumerate registered emails.
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if user is None or not user.hashed_password or not verify_password(request.password, user.hashed_password):
        raise invalid
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")

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
async def refresh_token(request: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(request.refresh_token)
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
    # after a logout or an earlier refresh already rotated it) is a stale/
    # potentially-leaked token being replayed — reject it outright rather
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
