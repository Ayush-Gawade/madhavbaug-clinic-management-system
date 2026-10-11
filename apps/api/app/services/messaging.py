"""WhatsApp messaging workflow: outbound dispatch and inbound processing.

Outbound: due follow-up instances that passed the scheduling eligibility check
are rendered and sent, then tracked with delivery events. Inbound: verified
webhook envelopes are deduplicated, matched to a patient and an open follow-up
instance, and stored; un-matchable items go to the staff exception queue.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.models.alerts import Alert, AlertPriority, AlertStatus, AlertType
from app.models.clinical import Patient
from app.models.messaging import (
    DeliveryStatus,
    ExceptionReason,
    ExceptionStatus,
    MessageDeliveryEvent,
    MessageDirection,
    MessageException,
    MessageProcessingStatus,
    MessageType,
    WebhookEvent,
    WebhookProcessingStatus,
    WhatsAppMessage,
)
from app.models.scheduling import (
    FollowUpInstance,
    FollowUpInstanceStatus,
    FollowUpSchedule,
    MessageTemplate,
)
from app.models.user import StaffUser
from app.services import ai as ai_service
from app.services import ai_queue
from app.services import schedules as schedules_service
from app.services import whatsapp as whatsapp_client

_OPEN_INSTANCE_STATUSES = (
    FollowUpInstanceStatus.QUEUED,
    FollowUpInstanceStatus.SENT,
    FollowUpInstanceStatus.DELIVERED,
    FollowUpInstanceStatus.READ,
)

_DELIVERY_STATUS_MAP = {
    "sent": DeliveryStatus.SENT,
    "delivered": DeliveryStatus.DELIVERED,
    "read": DeliveryStatus.READ,
    "failed": DeliveryStatus.FAILED,
}


async def _match_patients(db: AsyncSession, phone: str | None) -> list[Patient]:
    """Return every patient whose number could be the sender.

    Matching tolerates formatting and country-code differences by comparing the
    last ten digits. When the tolerant match is not unique, an exact normalized
    match is preferred; anything still tied stays ambiguous and is returned
    unresolved so the caller can quarantine it rather than guess.
    """
    digits = whatsapp_client.normalize_phone(phone)
    if not digits:
        return []
    last10 = digits[-10:]
    stmt = select(Patient).where(
        Patient.phone_number.isnot(None),
        func.right(func.regexp_replace(Patient.phone_number, r"\D", "", "g"), 10) == last10,
    )
    candidates = list((await db.execute(stmt)).scalars().all())
    if len(candidates) <= 1:
        return candidates
    exact = [p for p in candidates if whatsapp_client.normalize_phone(p.phone_number) == digits]
    return exact or candidates


async def _open_instance(db: AsyncSession, patient_id: uuid.UUID) -> FollowUpInstance | None:
    stmt = (
        select(FollowUpInstance)
        .where(
            FollowUpInstance.patient_id == patient_id,
            FollowUpInstance.status.in_(_OPEN_INSTANCE_STATUSES),
        )
        .order_by(FollowUpInstance.due_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def send_follow_up_message(
    db: AsyncSession,
    *,
    instance: FollowUpInstance,
    patient: Patient,
    template: MessageTemplate | None,
    body: str,
) -> bool:
    """Send a follow-up text message and persist it with a delivery event.

    Shared by first dispatch and reminders so both record identical outbound
    rows.     Returns whether the provider accepted the message.
    """
    if not patient.phone_number:
        return False
    result = await whatsapp_client.send_text_message(patient.phone_number, body)
    now = datetime.now(UTC)
    message = WhatsAppMessage(
        patient_id=patient.id,
        follow_up_instance_id=instance.id,
        direction=MessageDirection.OUTBOUND,
        provider_message_id=result.provider_message_id,
        message_type=MessageType.TEXT,
        to_phone=patient.phone_number,
        text_body=body,
        template_code=template.code if template else None,
        delivery_status=DeliveryStatus.SENT if result.ok else DeliveryStatus.FAILED,
        processing_status=MessageProcessingStatus.PROCESSED,
        error_code=result.error_code,
        error_message=result.error_message,
        sent_at=now,
    )
    db.add(message)
    await db.flush()
    db.add(
        MessageDeliveryEvent(
            message_id=message.id,
            status=message.delivery_status or DeliveryStatus.PENDING,
            occurred_at=now,
            payload={"dry_run": result.dry_run},
        )
    )
    return result.ok


async def raise_delivery_failure(db: AsyncSession, instance: FollowUpInstance, reason: str) -> None:
    """Surface a delivery failure distinctly from patient non-response (FR-027).

    At most one delivery-failure alert is raised per instance so repeated failed
    sends never spam the queue.
    """
    existing = (
        (
            await db.execute(
                select(Alert.id).where(
                    Alert.follow_up_instance_id == instance.id,
                    Alert.alert_type == AlertType.DELIVERY_FAILURE,
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return
    db.add(
        Alert(
            patient_id=instance.patient_id,
            follow_up_instance_id=instance.id,
            alert_type=AlertType.DELIVERY_FAILURE,
            priority=AlertPriority.PRIORITY,
            status=AlertStatus.OPEN,
            reason=reason,
        )
    )
    await db.flush()


async def dispatch_outbound(db: AsyncSession, *, limit: int = 100) -> dict[str, int]:
    """Send QUEUED follow-up instances and record message + delivery rows.

    Rows are claimed with ``FOR UPDATE SKIP LOCKED`` so two dispatchers running
    concurrently (the Beat schedule and a manual ``POST /messages/dispatch``)
    never send the same instance twice.
    """
    stmt = (
        select(FollowUpInstance)
        .where(FollowUpInstance.status == FollowUpInstanceStatus.QUEUED)
        .order_by(FollowUpInstance.due_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    instances = list((await db.execute(stmt)).scalars().all())

    sent = failed = skipped = 0
    for instance in instances:
        # Re-check eligibility at the moment of sending: consent may have been
        # withdrawn, or the patient deactivated, while the instance sat queued.
        schedule = await db.get(FollowUpSchedule, instance.schedule_id)
        if schedule is None or not await schedules_service.instance_is_eligible(
            db, instance, schedule
        ):
            instance.status = FollowUpInstanceStatus.SKIPPED
            instance.skip_reason = (
                "Consent withdrawn, patient inactive, or schedule no longer active at send time."
            )
            skipped += 1
            continue

        patient = await db.get(Patient, instance.patient_id)
        if patient is None or not patient.phone_number:
            instance.status = FollowUpInstanceStatus.FAILED
            await raise_delivery_failure(
                db, instance, "No WhatsApp number on record for this patient."
            )
            skipped += 1
            continue

        template = (
            await db.get(MessageTemplate, schedule.message_template_id)
            if schedule.message_template_id is not None
            else None
        )
        context = {"name": patient.full_name.split(" ")[0], "patient_name": patient.full_name}
        body = (
            whatsapp_client.render_template(template.body, context)
            if template
            else ("It is time for your scheduled check-in. Please share your update.")
        )

        ok = await send_follow_up_message(
            db, instance=instance, patient=patient, template=template, body=body
        )
        if ok:
            instance.status = FollowUpInstanceStatus.SENT
            instance.sent_at = datetime.now(UTC)
            sent += 1
        else:
            instance.status = FollowUpInstanceStatus.FAILED
            await raise_delivery_failure(
                db, instance, "The messaging provider rejected the outbound message."
            )
            failed += 1

    await db.flush()
    return {"sent": sent, "failed": failed, "held": skipped, "scanned": len(instances)}


async def _store_inbound(
    db: AsyncSession, event: whatsapp_client.MessageEvent
) -> tuple[WhatsAppMessage, bool, FollowUpInstance | None]:
    """Store an inbound message once; returns (message, created, instance)."""
    if event.provider_message_id:
        existing = await db.execute(
            select(WhatsAppMessage).where(
                WhatsAppMessage.provider_message_id == event.provider_message_id,
                WhatsAppMessage.direction == MessageDirection.INBOUND,
            )
        )
        found = existing.scalars().first()
        if found is not None:
            return found, False, None

    matches = await _match_patients(db, event.from_phone)
    patient = matches[0] if len(matches) == 1 else None
    ambiguous = len(matches) > 1
    instance: FollowUpInstance | None = None
    processing = MessageProcessingStatus.UNASSIGNED
    if patient is not None:
        instance = await _open_instance(db, patient.id)
        processing = MessageProcessingStatus.PROCESSED

    try:
        message_type = MessageType(event.message_type)
    except ValueError:
        message_type = MessageType.UNSUPPORTED

    message = WhatsAppMessage(
        patient_id=patient.id if patient else None,
        follow_up_instance_id=instance.id if instance else None,
        direction=MessageDirection.INBOUND,
        provider_message_id=event.provider_message_id or None,
        message_type=message_type,
        from_phone=event.from_phone,
        text_body=event.text or event.media_caption,
        media_reference=event.media_id,
        media_mime_type=event.media_mime_type,
        processing_status=processing,
        provider_timestamp=event.timestamp,
        received_at=event.timestamp or datetime.now(UTC),
    )
    db.add(message)

    if instance is not None:
        instance.status = FollowUpInstanceStatus.RESPONDED
        instance.completed_at = datetime.now(UTC)

    await db.flush()

    if ambiguous:
        db.add(
            MessageException(
                reason=ExceptionReason.AMBIGUOUS_SENDER,
                details={
                    "from_phone": event.from_phone,
                    "message_type": event.message_type,
                    "candidate_patient_ids": [str(p.id) for p in matches],
                },
            )
        )
        await db.flush()
    elif patient is not None:
        if settings.ai_processing_mode == "deferred":
            # Off the request path: the worker retries until the row commits.
            ai_queue.enqueue_inbound_analysis(message.id)
        else:
            await ai_service.analyze_inbound(db, message, patient, instance)
    else:
        db.add(
            MessageException(
                reason=ExceptionReason.UNKNOWN_SENDER,
                details={"from_phone": event.from_phone, "message_type": event.message_type},
            )
        )
        await db.flush()
    return message, True, instance


async def apply_status_event(db: AsyncSession, event: whatsapp_client.StatusEvent) -> bool:
    """Apply a provider delivery-status update to the matching outbound message."""
    status = _DELIVERY_STATUS_MAP.get(event.status)
    if status is None or not event.provider_message_id:
        return False
    result = await db.execute(
        select(WhatsAppMessage).where(
            WhatsAppMessage.provider_message_id == event.provider_message_id,
            WhatsAppMessage.direction == MessageDirection.OUTBOUND,
        )
    )
    message = result.scalars().first()
    if message is None:
        return False
    message.delivery_status = status
    if event.error_code:
        message.error_code = event.error_code
        message.error_message = event.error_message
    db.add(
        MessageDeliveryEvent(
            message_id=message.id,
            status=status,
            provider_status_code=event.error_code,
            occurred_at=event.timestamp or datetime.now(UTC),
            payload=event.raw,
        )
    )
    await db.flush()

    # A provider delivery failure is not a patient non-response: reconcile the
    # linked follow-up and surface a distinct alert instead of leaving it SENT.
    if status == DeliveryStatus.FAILED and message.follow_up_instance_id is not None:
        instance = await db.get(FollowUpInstance, message.follow_up_instance_id)
        if instance is not None and instance.status in _OPEN_INSTANCE_STATUSES:
            instance.status = FollowUpInstanceStatus.FAILED
            await raise_delivery_failure(
                db,
                instance,
                event.error_message or "The messaging provider reported a delivery failure.",
            )
    return True


async def process_webhook(
    db: AsyncSession, payload: dict[str, Any], raw_body: bytes, signature_verified: bool
) -> dict[str, int]:
    """Idempotently process one webhook delivery and its contained events."""
    provider_event_id = hashlib.sha256(raw_body).hexdigest()[:40]
    existing = await db.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == provider_event_id)
    )
    if existing.scalars().first() is not None:
        return {"duplicate": 1, "messages": 0, "statuses": 0}

    event = WebhookEvent(
        provider_event_id=provider_event_id,
        event_type="whatsapp",
        signature_verified=signature_verified,
        payload=payload,
    )
    db.add(event)
    await db.flush()

    messages, statuses = whatsapp_client.parse_webhook(payload)
    created_messages = 0
    for message_event in messages:
        _, created, _ = await _store_inbound(db, message_event)
        created_messages += int(created)

    applied_statuses = 0
    for status_event in statuses:
        applied_statuses += int(await apply_status_event(db, status_event))

    event.processing_status = WebhookProcessingStatus.PROCESSED
    await db.flush()
    return {
        "duplicate": 0,
        "messages": created_messages,
        "statuses": applied_statuses,
    }


async def list_conversation(
    db: AsyncSession, patient_id: uuid.UUID, pagination: PageParams
) -> tuple[list[WhatsAppMessage], int]:
    stmt = select(WhatsAppMessage).where(WhatsAppMessage.patient_id == patient_id)
    total = (
        await db.execute(
            select(func.count())
            .select_from(WhatsAppMessage)
            .where(WhatsAppMessage.patient_id == patient_id)
        )
    ).scalar_one()
    rows = list(
        (
            await db.execute(
                stmt.order_by(WhatsAppMessage.created_at.desc())
                .offset(pagination.offset)
                .limit(pagination.limit)
            )
        )
        .scalars()
        .all()
    )
    return rows, total


async def list_exceptions(
    db: AsyncSession, *, status: ExceptionStatus | None, pagination: PageParams
) -> tuple[list[MessageException], int]:
    stmt = select(MessageException)
    count_stmt = select(func.count()).select_from(MessageException)
    if status is not None:
        stmt = stmt.where(MessageException.status == status)
        count_stmt = count_stmt.where(MessageException.status == status)
    total = (await db.execute(count_stmt)).scalar_one()
    rows = list(
        (
            await db.execute(
                stmt.order_by(MessageException.created_at.desc())
                .offset(pagination.offset)
                .limit(pagination.limit)
            )
        )
        .scalars()
        .all()
    )
    return rows, total


async def resolve_exception(
    db: AsyncSession,
    exception_id: uuid.UUID,
    *,
    actor: StaffUser,
    resolved: bool,
    notes: str | None,
) -> MessageException:
    exception = await db.get(MessageException, exception_id)
    if exception is None:
        raise NotFoundError("Exception not found.")
    if exception.status != ExceptionStatus.OPEN:
        raise ConflictError("This exception has already been handled.")
    exception.status = ExceptionStatus.RESOLVED if resolved else ExceptionStatus.DISMISSED
    exception.resolved_by = actor.id
    exception.resolved_at = datetime.now(UTC)
    exception.resolution_notes = notes
    await db.flush()
    await db.refresh(exception)
    return exception
