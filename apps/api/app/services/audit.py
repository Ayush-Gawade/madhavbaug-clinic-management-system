"""Audit-trail writing helpers (append-only)."""

from __future__ import annotations

import json
import uuid
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent


def _jsonable_summary(change_summary: dict[str, Any] | None) -> dict[str, Any] | None:
    """Coerce changes (UUIDs, datetimes, enums) to JSON-safe primitives.

    ``change_summary`` is stored in a JSONB column, so every value must survive
    ``json.dumps``. A raw ``uuid.UUID`` from a pydantic ``model_dump()`` would
    otherwise fail at commit and roll back the caller's whole transaction.
    """
    if change_summary is None:
        return None
    try:
        return cast(dict[str, Any], json.loads(json.dumps(change_summary, default=str)))
    except (TypeError, ValueError):
        return {"serialization_error": str(change_summary)}


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
        change_summary=_jsonable_summary(change_summary),
        reason=reason,
        request_or_correlation_id=request_or_correlation_id,
    )
    db.add(event)
    return event
