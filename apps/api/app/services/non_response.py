"""Non-response handling: deadline monitoring, reminders, overdue and escalation.

Implements PRD section 5.6 (FR-022..FR-025, FR-027). The deterministic decision
of what to do next for a pending follow-up lives in :func:`decide_non_response`
so it is unit-testable without a database. Provider delivery failures are never
treated as non-response: only instances that actually reached the patient (SENT,
DELIVERED, READ) are reminded or flagged overdue (FR-027).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alerts import Alert, AlertPriority, AlertStatus, AlertType
from app.models.clinical import Patient
from app.models.scheduling import (
    FollowUpInstance,
    FollowUpInstanceStatus,
    FollowUpSchedule,
    FollowUpType,
    MessageTemplate,
)
from app.services import messaging as messaging_service
from app.services import schedules as schedules_service
from app.services import whatsapp as whatsapp_client

# Only follow-ups that were delivered to the patient can be "unanswered"; a
# FAILED instance is a delivery failure, not a patient non-response (FR-027).
_RESPONSE_PENDING = (
    FollowUpInstanceStatus.SENT,
    FollowUpInstanceStatus.DELIVERED,
    FollowUpInstanceStatus.READ,
)

_REMINDER_PREFIX = "Reminder: "
_DEFAULT_CHECK_IN_BODY = "It is time for your scheduled check-in. Please share your update."

NonResponseDecision = Literal["wait", "remind", "overdue"]


def follow_up_label(follow_up_type: FollowUpType) -> str:
    """Human-readable label for a follow-up type."""
    return follow_up_type.value.replace("_", " ").strip().capitalize()


def decide_non_response(
    *,
    deadline: datetime | None,
    status: FollowUpInstanceStatus,
    reminder_count: int,
    max_reminders: int,
    now: datetime,
) -> NonResponseDecision:
    """Decide the next non-response action for one pending instance (pure).

    - ``wait`` while the response deadline has not passed, or the instance is no
      longer awaiting a patient response (responded, failed, overdue).
    - ``remind`` once the deadline passes while reminders remain.
    - ``overdue`` once the deadline passes and reminders are exhausted.
    """
    if status not in _RESPONSE_PENDING:
        return "wait"
    if deadline is None or now < deadline:
        return "wait"
    if reminder_count < max_reminders:
        return "remind"
    return "overdue"


def escalation_priority(policy: dict[str, object] | None) -> AlertPriority | None:
    """Resolve the escalation priority, or ``None`` when no escalation applies.

    Escalation is opt-in via the schedule's escalation policy; the configured
    ``review_priority`` maps directly onto the alert priority (FR-021/FR-025).
    """
    if not policy:
        return None
    if not policy.get("escalate_after_deadline", True):
        return None
    raw = policy.get("review_priority", AlertPriority.PRIORITY.value)
    try:
        return AlertPriority(str(raw))
    except ValueError:
        return AlertPriority.PRIORITY


def _reminder_limits(schedule: FollowUpSchedule) -> tuple[int, int]:
    policy = schedule.reminder_policy or {}
    try:
        max_reminders = int(policy.get("max_reminders", 0) or 0)
    except (TypeError, ValueError):
        max_reminders = 0
    try:
        interval_hours = int(policy.get("interval_hours", 0) or 0)
    except (TypeError, ValueError):
        interval_hours = 0
    return max(0, max_reminders), max(1, interval_hours)


def _build_reason(schedule: FollowUpSchedule, instance: FollowUpInstance) -> str:
    label = follow_up_label(schedule.follow_up_type)
    return (
        f"{label} follow-up due {instance.due_date:%d %b %Y} received no valid response "
        f"by its deadline after {instance.reminder_count} reminder(s); flagged overdue "
        "for staff review."
    )


def _escalation_context(
    schedule: FollowUpSchedule, instance: FollowUpInstance
) -> dict[str, object]:
    return {
        "follow_up_type": schedule.follow_up_type.value,
        "due_date": instance.due_date.isoformat(),
        "response_deadline_at": (
            instance.response_deadline_at.isoformat()
            if instance.response_deadline_at is not None
            else None
        ),
        "reminders_sent": instance.reminder_count,
    }


async def _create_escalation(
    db: AsyncSession, schedule: FollowUpSchedule, instance: FollowUpInstance
) -> bool:
    """Raise a non-response alert for an overdue instance, once (idempotent)."""
    priority = escalation_priority(schedule.escalation_policy)
    if priority is None:
        return False
    existing = (
        (
            await db.execute(
                select(Alert.id).where(
                    Alert.follow_up_instance_id == instance.id,
                    Alert.alert_type == AlertType.NON_RESPONSE,
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return False
    db.add(
        Alert(
            patient_id=instance.patient_id,
            follow_up_instance_id=instance.id,
            alert_type=AlertType.NON_RESPONSE,
            priority=priority,
            status=AlertStatus.OPEN,
            assigned_to=instance.assigned_staff_id or schedule.responsible_staff_id,
            reason=_build_reason(schedule, instance),
            context=_escalation_context(schedule, instance),
        )
    )
    await db.flush()
    return True


async def _send_reminder(
    db: AsyncSession,
    schedule: FollowUpSchedule,
    instance: FollowUpInstance,
    *,
    interval_hours: int,
    now: datetime,
) -> bool:
    """Re-dispatch a reminder and start the next response window.

    Returns ``True`` only when the provider accepted the reminder; a rejected
    or undeliverable reminder returns ``False`` and never advances the reminder
    count or response deadline.
    """
    patient = await db.get(Patient, instance.patient_id)
    if patient is None or not patient.phone_number:
        await messaging_service.raise_delivery_failure(
            db, instance, "No WhatsApp number on record for this patient."
        )
        return False
    template = (
        await db.get(MessageTemplate, schedule.message_template_id)
        if schedule.message_template_id is not None
        else None
    )
    context = {"name": patient.full_name.split(" ")[0], "patient_name": patient.full_name}
    base = (
        whatsapp_client.render_template(template.body, context)
        if template is not None
        else _DEFAULT_CHECK_IN_BODY
    )
    ok = await messaging_service.send_follow_up_message(
        db, instance=instance, patient=patient, template=template, body=_REMINDER_PREFIX + base
    )
    if not ok:
        await messaging_service.raise_delivery_failure(
            db, instance, "The reminder message failed to send."
        )
        return False
    instance.reminder_count += 1
    instance.last_reminded_at = now
    instance.response_deadline_at = now + timedelta(hours=interval_hours)
    await db.flush()
    return True


async def process_non_response(db: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    """Advance pending follow-ups through reminders and overdue escalation.

    Idempotent and safe to run repeatedly: responding patients drop out of the
    pending set, reminders advance the response window, and an escalated alert
    is raised at most once per instance.
    """
    now = now or datetime.now(UTC)
    stmt = (
        select(FollowUpInstance)
        .where(
            FollowUpInstance.status.in_(_RESPONSE_PENDING),
            FollowUpInstance.response_deadline_at.isnot(None),
            FollowUpInstance.response_deadline_at <= now,
        )
        .order_by(FollowUpInstance.response_deadline_at.asc())
        .with_for_update(skip_locked=True)
    )
    instances = list((await db.execute(stmt)).scalars().all())

    reminders_sent = reminders_failed = marked_overdue = escalations_created = 0
    for instance in instances:
        schedule = await schedules_service.require_schedule(db, instance.schedule_id)
        max_reminders, interval_hours = _reminder_limits(schedule)
        decision = decide_non_response(
            deadline=instance.response_deadline_at,
            status=instance.status,
            reminder_count=instance.reminder_count,
            max_reminders=max_reminders,
            now=now,
        )
        if decision == "wait":
            continue
        if decision == "remind":
            eligible = await schedules_service.instance_is_eligible(db, instance, schedule)
            if not eligible:
                # Consent withdrawn / patient inactive before the reminder:
                # cancel rather than remind or escalate.
                instance.status = FollowUpInstanceStatus.SKIPPED
                instance.skip_reason = (
                    "Consent withdrawn, patient inactive, or schedule no longer "
                    "active before a reminder could be sent."
                )
                await db.flush()
                continue
            if await _send_reminder(db, schedule, instance, interval_hours=interval_hours, now=now):
                reminders_sent += 1
                continue
            # The reminder could not be delivered: record it as a delivery
            # failure, never as patient non-response (FR-027).
            instance.status = FollowUpInstanceStatus.FAILED
            reminders_failed += 1
            continue

        instance.status = FollowUpInstanceStatus.OVERDUE
        instance.overdue_at = now
        marked_overdue += 1
        if await _create_escalation(db, schedule, instance):
            escalations_created += 1

    await db.flush()
    return {
        "instances_scanned": len(instances),
        "reminders_sent": reminders_sent,
        "reminders_failed": reminders_failed,
        "marked_overdue": marked_overdue,
        "escalations_created": escalations_created,
    }
