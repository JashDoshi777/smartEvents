"""
LiveIQ — Auth Service (Sprint 7A)
Password hashing (bcrypt via passlib) and JWT access/refresh token
creation + verification. No external API — pure crypto/DB logic.
"""

import asyncio
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import bcrypt
from jose import jwt, JWTError

from app.core.config import settings

# passlib's CryptContext is unmaintained and incompatible with bcrypt>=4.1
# (its internal self-test calls a bcrypt internal API that no longer
# exists, raising on every hash/verify call) — using the bcrypt package
# directly sidesteps that entirely and is one less layer of indirection.
# bcrypt has a hard 72-byte input limit; encode+truncate defensively so a
# very long password doesn't raise instead of just hashing what fits.
_BCRYPT_MAX_BYTES = 72
BCRYPT_ROUNDS = 12  # explicit (bcrypt's default is also 12): ~250ms/hash, the OWASP-recommended floor

# JWT algorithm is PINNED to the HMAC family regardless of env: `decode` is
# always called with an explicit one-element allow-list so a forged
# `alg: none` / RS-HS confusion token can never verify.
_ALLOWED_ALGS = {"HS256", "HS384", "HS512"}
JWT_ALGORITHM = settings.ALGORITHM if settings.ALGORITHM in _ALLOWED_ALGS else "HS256"


def hash_password(password: str) -> str:
    truncated = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(truncated, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    truncated = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(truncated, hashed_password.encode("utf-8"))
    except ValueError:
        return False  # malformed hash — treat as non-matching, not a crash


# A valid hash of a random value, used to burn the same CPU time when the
# account does not exist so login latency doesn't reveal which emails are
# registered (timing side channel).
_DUMMY_HASH = bcrypt.hashpw(_uuid.uuid4().hex.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode()


async def hash_password_async(password: str) -> str:
    """bcrypt is CPU-bound (~250ms): run it off the event loop so a login
    burst can't stall every other request."""
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(plain: str, hashed: Optional[str]) -> bool:
    return await asyncio.to_thread(verify_password, plain, hashed or _DUMMY_HASH) and bool(hashed)


# Refresh tokens live much longer than access tokens — this is a real
# expiry choice, not arbitrary: short-lived access tokens limit the blast
# radius of a leaked token, while the longer refresh token lets a user
# stay logged in without re-entering a password every hour.
#
# Revocation: every refresh token embeds the User.token_version it was
# issued under. /auth/logout bumps the DB column (refresh issues a new token
# under the same version so a user's other devices/tabs keep working -
# per-session single-use rotation would need a sessions table); any refresh
# token minted before the bump then fails the version check in /auth/refresh
# even though the JWT signature itself is still valid —
# this is what makes revocation possible at all for a stateless JWT
# (there's no denylist table; the single integer column on User IS the
# revocation store). Access tokens intentionally do NOT carry or check
# token_version — they're short-lived enough that this would just be
# an extra DB round-trip per request for negligible benefit.
REFRESH_TOKEN_EXPIRE_DAYS = 30


def create_access_token(user_id: UUID, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "role": role, "type": "access", "exp": expire,
               "iat": datetime.now(timezone.utc), "jti": _uuid.uuid4().hex}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: UUID, token_version: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "type": "refresh", "ver": token_version, "exp": expire,
               "iat": datetime.now(timezone.utc), "jti": _uuid.uuid4().hex}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Returns the decoded payload, or None if invalid/expired/malformed."""
    if not token or not isinstance(token, str) or len(token) > 4096:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM],
                             options={"require_exp": True, "require_sub": True})
    except (JWTError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None
