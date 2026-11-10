"""FastAPI application factory and entrypoint."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    AccessLogMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings)
    settings.media_root.mkdir(parents=True, exist_ok=True)
    logger.info(
        "app_startup",
        app=settings.app_name,
        env=settings.app_env,
        version=__version__,
        whatsapp_enabled=settings.whatsapp_enabled,
        ai_enabled=settings.ai_enabled,
    )

    # Development machines without Redis cannot run the Celery beat pipeline,
    # so an in-process loop drives scheduled dispatch instead (production
    # always uses Celery).
    scheduler_task: asyncio.Task[None] | None = None
    if settings.local_scheduler_enabled and not settings.is_production:
        from app.workers import local_scheduler

        scheduler_task = asyncio.create_task(local_scheduler.scheduler_loop())

    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler_task
        logger.info("app_shutdown")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        description=(
            "Clinic Management System with WhatsApp-based patient engagement "
            "and AI-assisted monitoring."
        ),
        # Interactive docs and the schema expose the full API surface. Keep them
        # for local development but never publish them from a production edge.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # Middleware is applied outermost-first in reverse order of registration:
    # RequestID runs first (binds log context), then access logging, then the
    # defensive security headers, then CORS.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIDMiddleware)

    register_exception_handlers(app)

    # Liveness/readiness live at the root so probes do not depend on the API
    # version prefix.
    app.include_router(health.router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
