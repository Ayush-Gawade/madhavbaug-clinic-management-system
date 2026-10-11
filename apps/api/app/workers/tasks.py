"""Background task definitions.

Tasks are added as each workflow increment lands (scheduling, messaging, AI,
rule evaluation, escalation). Scheduler and dispatch work runs here so
nothing blocks an HTTP response (PRD 6.2, 10.2).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.workers.celery_app import celery_app


def _run(task: Callable[[AsyncSession], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    """Run an async service callable inside a fresh transactional session."""
    session_factory = get_sessionmaker()

    async def _runner() -> dict[str, Any]:
        async with session_factory() as session:
            try:
                result = await task(session)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

    return asyncio.run(_runner())


@celery_app.task(name="app.workers.tasks.healthcheck")  # type: ignore[untyped-decorator]
def healthcheck() -> str:
    """Trivial task used to verify the worker is running."""
    return "ok"


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.workers.tasks.materialize_follow_ups",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def materialize_follow_ups() -> dict[str, Any]:
    """Create missing follow-up instances for all active schedules."""
    from app.services import schedules as schedule_service

    return _run(schedule_service.materialize_instances)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.workers.tasks.process_due_follow_ups",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def process_due_follow_ups() -> dict[str, Any]:
    """Dispatch due, eligible instances to the messaging queue."""
    from app.services import schedules as schedule_service

    return _run(schedule_service.process_due_instances)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.workers.tasks.process_non_response",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def process_non_response() -> dict[str, Any]:
    """Send due reminders and flag exhausted follow-ups as overdue (FR-022..025)."""
    from app.services import non_response as non_response_service

    return _run(non_response_service.process_non_response)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.workers.tasks.dispatch_outbound_messages",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def dispatch_outbound_messages() -> dict[str, Any]:
    from app.services import messaging as messaging_service

    return _run(messaging_service.dispatch_outbound)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.workers.tasks.analyze_inbound_message",
    bind=True,
    max_retries=5,
)
def analyze_inbound_message(self: Any, message_id: str) -> dict[str, Any]:
    """Analyze one stored inbound message outside the webhook request (FR-018).

    The webhook enqueues this before its transaction commits, so the row may not
    be visible on the first attempt; a short retry covers that window.
    """
    from app.services import ai as ai_service

    try:
        result = _run(
            lambda session: ai_service.analyze_message_by_id(session, uuid.UUID(message_id))
        )
    except Exception as exc:  # pragma: no cover - exercised against live infra
        raise self.retry(exc=exc) from exc
    if not result.get("found", False):
        raise self.retry(countdown=2)
    return result
