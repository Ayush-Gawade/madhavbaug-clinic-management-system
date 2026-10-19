"""Alert queue and clinician-action workflow (PRD FR-021, FR-026, FR-041).

Alerts are raised by the deterministic rule engine and then routed through a
staff review queue. Every disposition is recorded as an append-only
``ClinicianAction`` so unresolved high-priority cases stay visible and auditable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.models.alerts import (
    Alert,
    AlertPriority,
    AlertStatus,
    ClinicianAction,
    ClinicianActionType,
)
from app.models.user import StaffUser

_TERMINAL = (AlertStatus.RESOLVED, AlertStatus.DISMISSED)

_PRIORITY_ORDER = case(
    (Alert.priority == AlertPriority.URGENT, 0),
    (Alert.priority == AlertPriority.PRIORITY, 1),
    else_=2,
)


async def require_alert(db: AsyncSession, alert_id: uuid.UUID) -> Alert:
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise NotFoundError("Alert not found.")
    return alert


async def list_alerts(
    db: AsyncSession,
    *,
    status: AlertStatus | None,
    priority: AlertPriority | None,
    patient_id: uuid.UUID | None,
    assigned_to: uuid.UUID | None,
    pagination: PageParams,
) -> tuple[list[Alert], int]:
    filters = []
    if status is not None:
        filters.append(Alert.status == status)
    if priority is not None:
        filters.append(Alert.priority == priority)
    if patient_id is not None:
        filters.append(Alert.patient_id == patient_id)
    if assigned_to is not None:
        filters.append(Alert.assigned_to == assigned_to)

    count_stmt = select(func.count()).select_from(Alert).where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Alert)
        .where(*filters)
        .order_by(_PRIORITY_ORDER.asc(), Alert.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return rows, total


async def alert_summary(db: AsyncSession, *, patient_id: uuid.UUID | None = None) -> dict[str, int]:
    """Counts for the dashboard and alert queue header."""
    filters = [Alert.patient_id == patient_id] if patient_id is not None else []

    status_rows = (
        await db.execute(
            select(Alert.status, func.count())
            .select_from(Alert)
            .where(*filters)
            .group_by(Alert.status)
        )
    ).all()
    by_status = {status.value: count for status, count in status_rows}

    open_filters = [*filters, Alert.status.in_((AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED))]
    priority_rows = (
        await db.execute(
            select(Alert.priority, func.count())
            .select_from(Alert)
            .where(*open_filters)
            .group_by(Alert.priority)
        )
    ).all()
    by_priority = {priority.value: count for priority, count in priority_rows}

    open_total = sum(by_priority.values())

    patients_open_total = (
        await db.execute(
            select(func.count(func.distinct(Alert.patient_id)))
            .select_from(Alert)
            .where(*open_filters)
        )
    ).scalar_one()
    patients_open_urgent = (
        await db.execute(
            select(func.count(func.distinct(Alert.patient_id)))
            .select_from(Alert)
            .where(*open_filters, Alert.priority == AlertPriority.URGENT)
        )
    ).scalar_one()
    return {
        "open": by_status.get(AlertStatus.OPEN.value, 0),
        "acknowledged": by_status.get(AlertStatus.ACKNOWLEDGED.value, 0),
        "resolved": by_status.get(AlertStatus.RESOLVED.value, 0),
        "dismissed": by_status.get(AlertStatus.DISMISSED.value, 0),
        "open_total": open_total,
        "open_urgent": by_priority.get(AlertPriority.URGENT.value, 0),
        "open_priority": by_priority.get(AlertPriority.PRIORITY.value, 0),
        "open_routine": by_priority.get(AlertPriority.ROUTINE.value, 0),
        "patients_open_total": patients_open_total,
        "patients_open_urgent": patients_open_urgent,
    }


def _record_action(
    db: AsyncSession,
    alert: Alert,
    *,
    actor: StaffUser,
    action_type: ClinicianActionType,
    from_status: AlertStatus,
    to_status: AlertStatus,
    notes: str | None,
) -> ClinicianAction:
    action = ClinicianAction(
        alert_id=alert.id,
        patient_id=alert.patient_id,
        action_type=action_type,
        actor_id=actor.id,
        from_status=from_status.value,
        to_status=to_status.value,
        notes=notes,
    )
    db.add(action)
    return action


async def acknowledge(
    db: AsyncSession, alert: Alert, *, actor: StaffUser, notes: str | None
) -> Alert:
    if alert.status == AlertStatus.ACKNOWLEDGED:
        raise ConflictError("This alert has already been acknowledged.")
    if alert.status in _TERMINAL:
        raise ConflictError("This alert is already closed.")
    previous = alert.status
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_by = actor.id
    alert.acknowledged_at = datetime.now(UTC)
    _record_action(
        db,
        alert,
        actor=actor,
        action_type=ClinicianActionType.ACKNOWLEDGE,
        from_status=previous,
        to_status=alert.status,
        notes=notes,
    )
    await db.flush()
    await db.refresh(alert)
    return alert


async def assign(
    db: AsyncSession,
    alert: Alert,
    *,
    actor: StaffUser,
    assignee_id: uuid.UUID,
    notes: str | None,
) -> Alert:
    if alert.status in _TERMINAL:
        raise ConflictError("This alert is already closed.")
    alert.assigned_to = assignee_id
    _record_action(
        db,
        alert,
        actor=actor,
        action_type=ClinicianActionType.ASSIGN,
        from_status=alert.status,
        to_status=alert.status,
        notes=notes,
    )
    await db.flush()
    await db.refresh(alert)
    return alert


async def escalate(db: AsyncSession, alert: Alert, *, actor: StaffUser, notes: str | None) -> Alert:
    if alert.status in _TERMINAL:
        raise ConflictError("This alert is already closed.")
    alert.priority = AlertPriority.URGENT
    _record_action(
        db,
        alert,
        actor=actor,
        action_type=ClinicianActionType.ESCALATE,
        from_status=alert.status,
        to_status=alert.status,
        notes=notes,
    )
    await db.flush()
    await db.refresh(alert)
    return alert


async def resolve(db: AsyncSession, alert: Alert, *, actor: StaffUser, notes: str | None) -> Alert:
    if alert.status in _TERMINAL:
        raise ConflictError("This alert is already closed.")
    previous = alert.status
    alert.status = AlertStatus.RESOLVED
    alert.resolved_by = actor.id
    alert.resolved_at = datetime.now(UTC)
    alert.resolution_notes = notes
    _record_action(
        db,
        alert,
        actor=actor,
        action_type=ClinicianActionType.RESOLVE,
        from_status=previous,
        to_status=alert.status,
        notes=notes,
    )
    await db.flush()
    await db.refresh(alert)
    return alert


async def dismiss(db: AsyncSession, alert: Alert, *, actor: StaffUser, notes: str | None) -> Alert:
    if alert.status in _TERMINAL:
        raise ConflictError("This alert is already closed.")
    previous = alert.status
    alert.status = AlertStatus.DISMISSED
    alert.resolved_by = actor.id
    alert.resolved_at = datetime.now(UTC)
    alert.resolution_notes = notes
    _record_action(
        db,
        alert,
        actor=actor,
        action_type=ClinicianActionType.DISMISS,
        from_status=previous,
        to_status=alert.status,
        notes=notes,
    )
    await db.flush()
    await db.refresh(alert)
    return alert


async def list_actions(db: AsyncSession, alert_id: uuid.UUID) -> list[ClinicianAction]:
    stmt = (
        select(ClinicianAction)
        .where(ClinicianAction.alert_id == alert_id)
        .order_by(ClinicianAction.occurred_at.asc(), ClinicianAction.created_at.asc())
    )
    return list((await db.execute(stmt)).scalars().all())
