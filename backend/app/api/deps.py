"""
LiveIQ — Auth Dependencies (Sprint 7A)
FastAPI dependencies for extracting and validating the current user from
a Bearer JWT, plus role-based route guards.
"""

import time
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User, UserRole
from app.services.auth_service import decode_token

bearer_scheme = HTTPBearer(auto_error=False)

# user_id -> (expires_at, User). The remote DB costs ~200ms per query, so
# re-reading the same user row on every API call dominated latency.
_USER_CACHE: dict[UUID, tuple[float, User]] = {}
_USER_TTL = 60.0


def invalidate_user_cache(user_id: UUID | None = None) -> None:
    if user_id is None:
        _USER_CACHE.clear()
    else:
        _USER_CACHE.pop(user_id, None)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})

    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token payload", headers={"WWW-Authenticate": "Bearer"})

    hit = _USER_CACHE.get(user_id)
    if hit and hit[0] > time.monotonic():
        return hit[1]

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is not None and user.is_active:
        db.expunge(user)  # detach with all columns loaded: safe to reuse across requests
        _USER_CACHE[user_id] = (time.monotonic() + _USER_TTL, user)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or deactivated", headers={"WWW-Authenticate": "Bearer"})

    return user


def require_roles(*allowed_roles: UserRole):
    """
    Route guard factory: Depends(require_roles(UserRole.EXECUTIVE, UserRole.ANALYST))
    restricts a route to only the given roles, on top of requiring auth at all.
    """
    allowed_values = {r.value for r in allowed_roles}

    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_values:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{user.role}' is not permitted for this action — requires one of: {sorted(allowed_values)}",
            )
        return user

    return _check
