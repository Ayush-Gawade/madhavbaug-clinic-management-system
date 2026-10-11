"""Audit-trail writing helpers (append-only)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent


async def record_event(
    db: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    change_summary: dict[str, Any] | None = None,
    reason: str | None = None,
    request_or_correlation_id: str | None = None,
) -> AuditEvent:
    """Stage an audit event on the session.

    The caller's transaction (committed by the request-scoped session) makes the
    write atomic with the change it describes. Audit rows are never mutated.
    """
    event = AuditEvent(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        change_summary=change_summary,
        reason=reason,
        request_or_correlation_id=request_or_correlation_id,
    )
    db.add(event)
    return event
