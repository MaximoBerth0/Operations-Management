from app.infra.config import settings
from app.infra.database.session import get_session
from app.infra.redis.client import ping as redis_ping
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", include_in_schema=False)
async def ready(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    """verifies the database connection is usable."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable", "database": "down"},
        )

    # Redis backs the rate limiter, which fails open, so a sick Redis is
    # reported but does not flip readiness.
    redis_status = "not_configured" if not settings.REDIS_URL else (
        "up" if await redis_ping() else "down"
    )
    return JSONResponse(content={"status": "ok", "database": "up", "redis": redis_status})
