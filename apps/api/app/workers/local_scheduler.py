"""Development-only in-process follow-up pipeline loop.

Production drives materialisation, dispatch and non-response handling with
Celery Beat + workers (see ``celery_app.beat_schedule``). For local demos on
machines without Redis (e.g. Windows) this module runs a lightweight asyncio
loop inside the API process that mirrors that schedule: every interval it
materialises instances, processes due instances, dispatches queued outbound
WhatsApp messages and runs the non-response pass.

It is only ever started when ``settings.local_scheduler_enabled`` is true and
the app is not running in production.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.services import messaging as messaging_service
from app.services import non_response as non_response_service
from app.services import schedules as schedules_service

logger = get_logger(__name__)

PipelineStep = Callable[[AsyncSession], Any]

# Mirrors the Celery beat cadence: materialise first, then due processing,
# then dispatch, then non-response (each in its own transactional session).
_PIPELINE_STEPS: tuple[tuple[str, PipelineStep], ...] = (
    ("materialize", schedules_service.materialize_instances),
    ("process_due", schedules_service.process_due_instances),
    ("dispatch_outbound", messaging_service.dispatch_outbound),
    ("non_response", non_response_service.process_non_response),
)


async def run_pipeline_once() -> dict[str, Any]:
    """Run every pipeline step once, each in its own session with a commit.

    A failing step never blocks the others: the error is logged and the run
    continues so a transient provider outage cannot take down the loop.
    """
    results: dict[str, Any] = {}
    session_factory = get_sessionmaker()
    for name, step in _PIPELINE_STEPS:
        async with session_factory() as db:
            try:
                result = await step(db)
                await db.commit()
                results[name] = result
            except Exception:
                await db.rollback()
                logger.exception("local_scheduler_step_failed", step=name)
                results[name] = {"error": "failed"}
    return results


async def scheduler_loop(*, interval_seconds: float | None = None) -> None:
    """Periodically run the pipeline until cancelled.

    The interval is measured from the start of each run so long passes (e.g. a
    slow Meta call) never bunch up behind the timer.
    """
    interval = max(5.0, interval_seconds or settings.local_scheduler_interval_seconds)
    logger.info("local_scheduler_start", interval_seconds=interval)
    while True:
        started = datetime.now(UTC)
        try:
            await run_pipeline_once()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("local_scheduler_run_failed", error=str(exc))
        elapsed = (datetime.now(UTC) - started).total_seconds()
        await asyncio.sleep(max(0.0, interval - elapsed))
