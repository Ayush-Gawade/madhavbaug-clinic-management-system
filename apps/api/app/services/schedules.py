"""Follow-up scheduling services: schedules, templates, materialization, dispatch.

Materialization turns active schedules into concrete instances (PRD schema F);
the dispatch processor marks eligible due instances as QUEUED so the messaging
worker (increment 6) can hand them to the WhatsApp integration.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.models.clinical import ConsentType, Patient, PatientStatus
from app.models.scheduling import (
    FollowUpInstance,
    FollowUpInstanceStatus,
    FollowUpSchedule,
    MessageTemplate,
    ScheduleStatus,
)
from app.models.user import StaffUser
from app.schemas.scheduling import (
    ScheduleCreate,
    ScheduleUpdate,
    TemplateCreate,
    TemplateUpdate,
)
from app.services import patients as patients_service
from app.services.recurrence import dates_between, validate_recurrence_rule

_DEFAULT_CHECK_IN_TIME = time(hour=9, minute=0)
_ModelT = TypeVar("_ModelT")


def local_tz(schedule: FollowUpSchedule) -> ZoneInfo:
    try:
        return ZoneInfo(schedule.timezone or settings.app_timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo(settings.app_timezone)


def local_today(schedule: FollowUpSchedule) -> date:
    """Current calendar date in the schedule's timezone."""
    return datetime.now(local_tz(schedule)).date()


async def require_schedule(db: AsyncSession, schedule_id: uuid.UUID) -> FollowUpSchedule:
    schedule = await db.get(FollowUpSchedule, schedule_id)
    if schedule is None:
        raise NotFoundError("Follow-up schedule not found.")
    return schedule


async def require_template(db: AsyncSession, template_id: uuid.UUID) -> MessageTemplate:
    template = await db.get(MessageTemplate, template_id)
    if template is None:
        raise NotFoundError("Message template not found.")
    return template


async def require_instance(db: AsyncSession, instance_id: uuid.UUID) -> FollowUpInstance:
    instance = await db.get(FollowUpInstance, instance_id)
    if instance is None:
        raise NotFoundError("Follow-up instance not found.")
    return instance


async def create_schedule(
    db: AsyncSession, data: ScheduleCreate, actor: StaffUser
) -> FollowUpSchedule:
    await patients_service.require_patient(db, data.patient_id)
    if data.message_template_id is not None:
        await require_template(db, data.message_template_id)

    recurrence = validate_recurrence_rule(data.recurrence_rule.model_dump(exclude_none=True))
    schedule = FollowUpSchedule(
        patient_id=data.patient_id,
        care_plan_id=data.care_plan_id,
        follow_up_type=data.follow_up_type,
        recurrence_rule=recurrence,
        scheduled_local_time=data.scheduled_local_time,
        timezone=data.timezone,
        message_template_id=data.message_template_id,
        message_body=data.message_body,
        response_deadline_hours=data.response_deadline_hours,
        reminder_policy=(data.reminder_policy.model_dump() if data.reminder_policy else None),
        escalation_policy=(data.escalation_policy.model_dump() if data.escalation_policy else None),
        status=data.status,
        active_from=data.active_from,
        active_to=data.active_to,
        responsible_staff_id=data.responsible_staff_id,
        created_by=actor.id,
    )
    db.add(schedule)
    await db.flush()
    return schedule


async def list_schedules(
    db: AsyncSession,
    *,
    patient_id: uuid.UUID | None = None,
    status: ScheduleStatus | None = None,
    pagination: PageParams | None = None,
) -> tuple[list[FollowUpSchedule], int]:
    stmt = select(FollowUpSchedule)
    count_stmt = select(func.count()).select_from(FollowUpSchedule)
    if patient_id is not None:
        stmt = stmt.where(FollowUpSchedule.patient_id == patient_id)
        count_stmt = count_stmt.where(FollowUpSchedule.patient_id == patient_id)
    if status is not None:
        stmt = stmt.where(FollowUpSchedule.status == status)
        count_stmt = count_stmt.where(FollowUpSchedule.status == status)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(FollowUpSchedule.created_at.desc())
    if pagination is not None:
        stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    rows = list((await db.execute(stmt)).scalars().all())
    return rows, total


async def update_schedule(
    db: AsyncSession, schedule_id: uuid.UUID, data: ScheduleUpdate
) -> FollowUpSchedule:
    schedule = await require_schedule(db, schedule_id)
    updates = data.model_dump(exclude_unset=True)
    if "message_template_id" in updates:
        if updates["message_template_id"] is None:
            schedule.message_template_id = None
        else:
            await require_template(db, updates["message_template_id"])
            schedule.message_template_id = updates["message_template_id"]
        del updates["message_template_id"]
    if "reminder_policy" in updates:
        schedule.reminder_policy = (
            updates["reminder_policy"].model_dump()
            if updates["reminder_policy"] is not None
            else None
        )
        del updates["reminder_policy"]
    if "escalation_policy" in updates:
        schedule.escalation_policy = (
            updates["escalation_policy"].model_dump()
            if updates["escalation_policy"] is not None
            else None
        )
        del updates["escalation_policy"]

    for field, value in updates.items():
        setattr(schedule, field, value)

    return schedule


async def _existing_due_dates(
    db: AsyncSession, schedule_ids: list[uuid.UUID]
) -> dict[uuid.UUID, set[date]]:
    if not schedule_ids:
        return {}
    rows = await db.execute(
        select(FollowUpInstance.schedule_id, FollowUpInstance.due_date).where(
            FollowUpInstance.schedule_id.in_(schedule_ids)
        )
    )
    existing: dict[uuid.UUID, set[date]] = {sid: set() for sid in schedule_ids}
    for schedule_id, due_date in rows.all():
        existing[schedule_id].add(due_date)
    return existing


def _due_at(schedule: FollowUpSchedule, occurrence: date) -> datetime:
    tz = local_tz(schedule)
    local_dt = datetime.combine(
        occurrence, schedule.scheduled_local_time or _DEFAULT_CHECK_IN_TIME, tzinfo=tz
    )
    return local_dt


def _in_active_range(schedule: FollowUpSchedule, occurrence: date) -> bool:
    if schedule.active_from and occurrence < schedule.active_from:
        return False
    return not (schedule.active_to and occurrence > schedule.active_to)


async def materialize_instances(
    db: AsyncSession,
    *,
    schedule_id: uuid.UUID | None = None,
    horizon_days: int = 7,
) -> dict[str, Any]:
    """Create missing instances for active schedules within the look-ahead window.

    Idempotent: instances are keyed by ``(schedule_id, due_date)`` so repeated
    runs never duplicate an occurrence. Returns creation counts.
    """
    horizon_days = max(1, min(horizon_days, 60))

    stmt = select(FollowUpSchedule).where(FollowUpSchedule.status == ScheduleStatus.ACTIVE)
    if schedule_id is not None:
        stmt = stmt.where(FollowUpSchedule.id == schedule_id)
    schedules = list((await db.execute(stmt)).scalars().all())

    existing = await _existing_due_dates(db, [schedule.id for schedule in schedules])
    candidates: list[FollowUpInstance] = []
    for schedule in schedules:
        today = local_today(schedule)
        if schedule.active_from and today < schedule.active_from:
            today = schedule.active_from
        lookahead = today + timedelta(days=horizon_days)
        occurrences = dates_between(schedule.recurrence_rule, today, lookahead)
        for occurrence in occurrences:
            if occurrence in existing[schedule.id]:
                continue
            if not _in_active_range(schedule, occurrence):
                continue
            due = _due_at(schedule, occurrence)
            candidates.append(
                FollowUpInstance(
                    schedule_id=schedule.id,
                    patient_id=schedule.patient_id,
                    due_date=occurrence,
                    due_at=due,
                    response_deadline_at=due + timedelta(hours=schedule.response_deadline_hours),
                    status=FollowUpInstanceStatus.SCHEDULED,
                    assigned_staff_id=schedule.responsible_staff_id,
                )
            )
    db.add_all(candidates)
    await db.flush()
    return {
        "instances_created": len(candidates),
        "schedule_count": len(schedules),
        "horizon_days": horizon_days,
        "schedule_id": schedule_id,
    }


async def _is_eligible(
    db: AsyncSession, instance: FollowUpInstance, schedule: FollowUpSchedule
) -> bool:
    if schedule.status != ScheduleStatus.ACTIVE:
        return False
    if not _in_active_range(schedule, instance.due_date):
        return False
    patient = await db.get(Patient, instance.patient_id)
    if patient is None:
        return False
    if patient.status != PatientStatus.ACTIVE:
        return False
    return patients_service.has_active_consent(patient, ConsentType.COMMUNICATION)


async def instance_is_eligible(
    db: AsyncSession, instance: FollowUpInstance, schedule: FollowUpSchedule
) -> bool:
    """Public wrapper around the dispatch eligibility check (consent + schedule)."""
    return await _is_eligible(db, instance, schedule)


async def process_due_instances(db: AsyncSession, *, now: datetime | None = None) -> dict[str, Any]:
    """Mark eligible SCHEDULED instances whose due time has arrived as QUEUED.

    Eligibility re-checks schedule state, active range and communication
    consent at dispatch time (PRD FR-010). Ineligible instances are left in
    place for a later run.
    """
    now = now or datetime.now(UTC)
    stmt = (
        select(FollowUpInstance)
        .where(
            FollowUpInstance.status == FollowUpInstanceStatus.SCHEDULED,
            FollowUpInstance.due_at <= now,
        )
        .order_by(FollowUpInstance.due_at.asc())
    )
    instances = list((await db.execute(stmt)).scalars().all())

    eligible = 0
    skipped = 0
    for instance in instances:
        schedule = await require_schedule(db, instance.schedule_id)
        if await _is_eligible(db, instance, schedule):
            instance.status = FollowUpInstanceStatus.QUEUED
            eligible += 1
        else:
            skipped += 1
    await db.flush()
    return {
        "eligible_to_send": eligible,
        "skipped_consent": skipped,
        "instances_scanned": len(instances),
    }


_RESOLVED_INSTANCE_STATUSES = (
    FollowUpInstanceStatus.RESPONDED,
    FollowUpInstanceStatus.SKIPPED,
)


async def acknowledge_instance(
    db: AsyncSession, instance_id: uuid.UUID, *, actor: StaffUser
) -> FollowUpInstance:
    """Record that a staff member has seen an overdue/pending follow-up (FR-026)."""
    instance = await require_instance(db, instance_id)
    instance.acknowledged_by = actor.id
    instance.acknowledged_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(instance)
    return instance


async def assign_instance(
    db: AsyncSession, instance_id: uuid.UUID, *, staff_id: uuid.UUID
) -> FollowUpInstance:
    """Assign a follow-up to an authorised staff member (FR-026)."""
    instance = await require_instance(db, instance_id)
    staff = await db.get(StaffUser, staff_id)
    if staff is None:
        raise NotFoundError("Staff member not found.")
    instance.assigned_staff_id = staff_id
    await db.flush()
    await db.refresh(instance)
    return instance


async def resolve_instance(
    db: AsyncSession, instance_id: uuid.UUID, *, actor: StaffUser
) -> FollowUpInstance:
    """Close an overdue/pending follow-up that staff handled outside the app (FR-026).

    Resolving marks the instance skipped so it leaves the overdue queue and is
    excluded from the adherence denominator.
    """
    instance = await require_instance(db, instance_id)
    if instance.status in _RESOLVED_INSTANCE_STATUSES:
        raise ConflictError("This follow-up has already been resolved.")
    instance.status = FollowUpInstanceStatus.SKIPPED
    instance.skip_reason = "Resolved by staff."
    instance.acknowledged_by = actor.id
    instance.acknowledged_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(instance)
    return instance


async def list_instances(
    db: AsyncSession,
    *,
    status: FollowUpInstanceStatus | None = None,
    patient_id: uuid.UUID | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    pagination: PageParams,
) -> tuple[list[FollowUpInstance], int]:
    stmt = select(FollowUpInstance)
    count_stmt = select(func.count()).select_from(FollowUpInstance)
    if status is not None:
        stmt = stmt.where(FollowUpInstance.status == status)
        count_stmt = count_stmt.where(FollowUpInstance.status == status)
    if patient_id is not None:
        stmt = stmt.where(FollowUpInstance.patient_id == patient_id)
        count_stmt = count_stmt.where(FollowUpInstance.patient_id == patient_id)
    if due_from is not None:
        stmt = stmt.where(FollowUpInstance.due_date >= due_from)
        count_stmt = count_stmt.where(FollowUpInstance.due_date >= due_from)
    if due_to is not None:
        stmt = stmt.where(FollowUpInstance.due_date <= due_to)
        count_stmt = count_stmt.where(FollowUpInstance.due_date <= due_to)

    total = (await db.execute(count_stmt)).scalar_one()
    rows = list(
        (
            await db.execute(
                stmt.order_by(FollowUpInstance.due_at.asc())
                .offset(pagination.offset)
                .limit(pagination.limit)
            )
        )
        .scalars()
        .all()
    )
    return rows, total


async def day_counts(db: AsyncSession) -> dict[str, int]:
    """Dashboard counts for follow-ups due/overdue/done today (clinic tz)."""
    clinic_tz = ZoneInfo(settings.app_timezone)
    today = datetime.now(clinic_tz).date()

    due_today = (
        await db.execute(
            select(func.count())
            .select_from(FollowUpInstance)
            .where(
                FollowUpInstance.due_date == today,
                FollowUpInstance.status.in_(
                    (FollowUpInstanceStatus.SCHEDULED, FollowUpInstanceStatus.QUEUED)
                ),
            )
        )
    ).scalar_one()

    overdue = (
        await db.execute(
            select(func.count())
            .select_from(FollowUpInstance)
            .where(
                FollowUpInstance.status == FollowUpInstanceStatus.OVERDUE,
                FollowUpInstance.due_date <= today,
            )
        )
    ).scalar_one()

    done_today = (
        await db.execute(
            select(func.count())
            .select_from(FollowUpInstance)
            .where(
                FollowUpInstance.due_date == today,
                FollowUpInstance.status == FollowUpInstanceStatus.RESPONDED,
            )
        )
    ).scalar_one()

    return {"due_today": due_today, "overdue": overdue, "done_today": done_today}


async def create_template(db: AsyncSession, data: TemplateCreate) -> MessageTemplate:
    existing = await db.execute(select(MessageTemplate).where(MessageTemplate.code == data.code))
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("A template with this code already exists.")
    template = MessageTemplate(**data.model_dump())
    db.add(template)
    await db.flush()
    return template


async def list_templates(db: AsyncSession, *, active_only: bool = False) -> list[MessageTemplate]:
    stmt = select(MessageTemplate).order_by(MessageTemplate.code.asc())
    if active_only:
        stmt = stmt.where(MessageTemplate.is_active.is_(True))
    return list((await db.execute(stmt)).scalars().all())


async def update_template(
    db: AsyncSession, template_id: uuid.UUID, data: TemplateUpdate
) -> MessageTemplate:
    template = await require_template(db, template_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    return template
