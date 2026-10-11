"""Liveness and readiness endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Response
from sqlalchemy import text

from app import __version__
from app.api.deps import DbSession
from app.core.config import settings
from app.core.redis import get_redis

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "version": __version__,
        "time": datetime.now(UTC).isoformat(),
    }


@router.get("/health/ready", summary="Readiness probe (checks dependencies)")
async def readiness(response: Response, db: DbSession) -> dict[str, object]:
    components: dict[str, str] = {}
    healthy = True

    try:
        await db.execute(text("SELECT 1"))
        components["database"] = "ok"
    except Exception as exc:  # pragma: no cover - depends on infra state
        components["database"] = f"error: {type(exc).__name__}"
        healthy = False

    try:
        redis = get_redis()
        await redis.ping()
        components["redis"] = "ok"
    except Exception as exc:  # pragma: no cover - depends on infra state
        components["redis"] = f"error: {type(exc).__name__}"
        healthy = False

    # A degraded dependency must fail the probe so orchestrators stop routing
    # traffic to this instance; the body still reports which component failed.
    response.status_code = 200 if healthy else 503
    return {
        "status": "ok" if healthy else "degraded",
        "components": components,
        "time": datetime.now(UTC).isoformat(),
    }
