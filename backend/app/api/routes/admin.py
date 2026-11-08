"""Admin / operations endpoints.

  POST /admin/cache/clear   executive only - empties the in-memory response cache
"""
import structlog
from fastapi import APIRouter, Depends

from app.api.deps import require_roles
from app.core.response_cache import cache_stats, invalidate_all
from app.models.user import User, UserRole

router = APIRouter()
logger = structlog.get_logger()


@router.post("/cache/clear", summary="Clear the API response cache (executive only)")
async def clear_cache(user: User = Depends(require_roles(UserRole.EXECUTIVE))):
    cleared = invalidate_all()
    logger.info("response cache cleared", by=str(user.id), entries=cleared)
    return {"status": "ok", "cleared_entries": cleared, "cache": cache_stats()}
