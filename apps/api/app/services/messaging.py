"""WhatsApp messaging workflow: outbound dispatch and inbound processing.

Outbound: due follow-up instances that passed the scheduling eligibility check
are rendered and sent, then tracked with delivery events. Inbound: verified
webhook envelopes are deduplicated, matched to a patient and an open follow-up
instance, and stored; un-matchable items go to the staff exception queue.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
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
from app.services import ai_queue, media_queue
from app.services import schedules as schedules_service
from app.services import whatsapp as whatsapp_client

_OPEN_INSTANCE_STATUSES = (
    FollowUpInstanceStatus.QUEUED,
    FollowUpInstanceStatus.SENT,
    FollowUpInstanceStatus.DELIVERED,
    FollowUpInstanceStatus.READ,
)

_DEFAULT_CHECK_IN_BODY = "It is time for your scheduled check-in. Please share your update."

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


def template_context(patient: Patient) -> dict[str, str]:
    """Placeholder values shared by text rendering and template sends.

    Both named (``{{name}}``) and 1-based positional (``{{1}}``) placeholders are
    populated so a stored body works whether it mirrors the Meta template's
    numbered variables or uses friendlier names.
    """
    first_name = patient.full_name.split(" ")[0] if patient.full_name else ""
    return {
        "name": first_name,
        "patient_name": patient.full_name,
        "1": first_name,
        "2": patient.full_name,
    }


async def _last_inbound_at(db: AsyncSession, patient_id: uuid.UUID) -> datetime | None:
    """When the patient last messaged us, used to decide the send mode."""
    stmt = select(
        func.max(func.coalesce(WhatsAppMessage.received_at, WhatsAppMessage.created_at))
    ).where(
        WhatsAppMessage.patient_id == patient_id,
        WhatsAppMessage.direction == MessageDirection.INBOUND,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _within_session_window(db: AsyncSession, patient_id: uuid.UUID) -> bool:
    """Whether a free-form (text) reply is allowed for this patient right now.

    Meta permits free-form messages only within 24 hours of the patient's last
    inbound message; outside that window a business-initiated message must use an
    approved template.
    """
    last_inbound = await _last_inbound_at(db, patient_id)
    if last_inbound is None:
        return False
    window = timedelta(hours=settings.whatsapp_session_window_hours)
    return datetime.now(UTC) - last_inbound < window


async def send_follow_up_message(
    db: AsyncSession,
    *,
    instance: FollowUpInstance,
    patient: Patient,
    template: MessageTemplate | None,
    body: str,
    context: dict[str, str] | None = None,
) -> bool:
    """Send a follow-up message and persist it with a delivery event.

    Inside the Meta 24-hour customer-service window (or when window enforcement
    is disabled) the rendered ``body`` is sent as free-form text. Outside the
    window, enforcement requires an approved, active template: the template is
    sent with positional parameters derived from ``context``. A missing or
    unapproved template is recorded as a delivery failure rather than sending
    text Meta would reject.

    Shared by first dispatch and reminders so both record identical outbound
    rows. Returns whether the provider accepted the message.
    """
    if not patient.phone_number:
        return False
    context = context or {}
    requires_template = settings.whatsapp_enforce_session_window and not (
        await _within_session_window(db, patient.id)
    )
    if requires_template:
        if template is None or not template.approved or not template.is_active:
            result = whatsapp_client.SendResult(
                ok=False,
                error_code="template_required",
                error_message=(
                    "Outside the 24-hour session window Meta requires an approved, "
                    "active template; none is configured for this follow-up."
                ),
            )
        else:
            result = await whatsapp_client.send_template_message(
                patient.phone_number,
                template.name,
                template.language,
                whatsapp_client.build_template_parameters(template.body, context),
            )
    else:
        result = await whatsapp_client.send_text_message(patient.phone_number, body)
    now = datetime.now(UTC)
    message = WhatsAppMessage(
        patient_id=patient.id,
        follow_up_instance_id=instance.id,
        direction=MessageDirection.OUTBOUND,
        provider_message_id=result.provider_message_id,
        message_type=MessageType.TEMPLATE if requires_template else MessageType.TEXT,
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


async def send_manual_reply(
    db: AsyncSession,
    *,
    patient: Patient,
    body: str | None,
    template: MessageTemplate | None,
    instance_id: uuid.UUID | None = None,
) -> WhatsAppMessage:
    """Send a manual staff reply and persist the outbound message row.

    Inside the Meta 24-hour session window (or when enforcement is disabled)
    the free-form ``body`` is sent as text. Outside the window Meta requires an
    approved, active template, so the caller must provide one; a missing body or
    template raises ``ValidationError`` with code ``session_window_required`` so
    the UI can prompt staff to switch to a template.
    """
    if not patient.phone_number:
        raise ValidationError("This patient has no WhatsApp number on record.")

    now = datetime.now(UTC)
    context = template_context(patient)

    if template is not None:
        if not template.approved or not template.is_active:
            raise ValidationError("Only approved, active templates can be sent.")
        result = await whatsapp_client.send_template_message(
            patient.phone_number,
            template.name,
            template.language,
            whatsapp_client.build_template_parameters(template.body, context),
        )
        message_type = MessageType.TEMPLATE
        message_body = whatsapp_client.render_template(template.body, context)
        template_code = template.code
    else:
        if settings.whatsapp_enforce_session_window and not await _within_session_window(
            db, patient.id
        ):
            raise ValidationError(
                "Outside the 24-hour session window Meta does not allow free-form "
                "messages. Send an approved template instead.",
                code="session_window_required",
            )
        if not body or not body.strip():
            raise ValidationError("A reply body is required.")
        result = await whatsapp_client.send_text_message(patient.phone_number, body)
        message_type = MessageType.TEXT
        message_body = body
        template_code = None

    message = WhatsAppMessage(
        patient_id=patient.id,
        follow_up_instance_id=instance_id,
        direction=MessageDirection.OUTBOUND,
        provider_message_id=result.provider_message_id,
        message_type=message_type,
        to_phone=patient.phone_number,
        text_body=message_body,
        template_code=template_code,
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
            payload={"dry_run": result.dry_run, "manual": True},
        )
    )
    return message


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
        context = template_context(patient)
        body = (
            whatsapp_client.render_template(template.body, context)
            if template
            else (schedule.message_body or _DEFAULT_CHECK_IN_BODY)
        )

        ok = await send_follow_up_message(
            db, instance=instance, patient=patient, template=template, body=body, context=context
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

    # Persist media bytes off the request path; dry-run and AI-only deployments
    # skip this because there is nothing to download.
    if settings.whatsapp_enabled and message.media_reference and message.media_mime_type:
        media_queue.enqueue_inbound_media(message.id)
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


async def list_messages(
    db: AsyncSession,
    *,
    direction: MessageDirection | None = None,
    delivery_status: DeliveryStatus | None = None,
    patient_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    pagination: PageParams,
) -> tuple[list[WhatsAppMessage], int]:
    """Clinic-wide message list with transport/search filters (screens C and D)."""
    filters: list[Any] = []
    if direction is not None:
        filters.append(WhatsAppMessage.direction == direction)
    if delivery_status is not None:
        filters.append(WhatsAppMessage.delivery_status == delivery_status)
    if patient_id is not None:
        filters.append(WhatsAppMessage.patient_id == patient_id)
    if search:
        filters.append(WhatsAppMessage.text_body.ilike(f"%{search}%"))

    occurred = func.coalesce(
        WhatsAppMessage.sent_at,
        WhatsAppMessage.received_at,
        WhatsAppMessage.created_at,
    )
    if date_from is not None:
        filters.append(func.date(occurred) >= date_from)
    if date_to is not None:
        filters.append(func.date(occurred) <= date_to)

    stmt = select(WhatsAppMessage)
    count_stmt = select(func.count()).select_from(WhatsAppMessage)
    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = (await db.execute(count_stmt)).scalar_one()
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


async def list_inbox_threads(
    db: AsyncSession, pagination: PageParams
) -> tuple[list[dict[str, Any]], int]:
    """One row per patient with inbound activity, newest conversation first.

    The replies inbox groups inbound messages by patient so a patient who writes
    several times appears once, with the number of inbound messages alongside.
    """
    occurred = func.coalesce(WhatsAppMessage.received_at, WhatsAppMessage.created_at)
    filters = [
        WhatsAppMessage.direction == MessageDirection.INBOUND,
        WhatsAppMessage.patient_id.is_not(None),
    ]

    threads = (
        select(
            WhatsAppMessage.patient_id.label("patient_id"),
            func.max(occurred).label("latest_at"),
            func.count().label("inbound_count"),
        )
        .where(*filters)
        .group_by(WhatsAppMessage.patient_id)
        .subquery()
    )
    total = int((await db.execute(select(func.count()).select_from(threads))).scalar_one())

    page_rows = (
        await db.execute(
            select(threads.c.patient_id, threads.c.latest_at, threads.c.inbound_count)
            .order_by(threads.c.latest_at.desc())
            .offset(pagination.offset)
            .limit(pagination.limit)
        )
    ).all()
    if not page_rows:
        return [], total

    patient_ids = [row.patient_id for row in page_rows]
    names = dict(
        (
            await db.execute(
                select(Patient.id, Patient.full_name).where(Patient.id.in_(patient_ids))
            )
        ).all()
    )

    latest_stmt = (
        select(WhatsAppMessage)
        .join(
            threads,
            (WhatsAppMessage.patient_id == threads.c.patient_id)
            & (occurred == threads.c.latest_at),
        )
        .where(*filters, WhatsAppMessage.patient_id.in_(patient_ids))
        .order_by(occurred.desc())
    )
    latest_by_patient: dict[uuid.UUID, WhatsAppMessage] = {}
    for candidate in (await db.execute(latest_stmt)).scalars().all():
        if candidate.patient_id is not None:
            latest_by_patient.setdefault(candidate.patient_id, candidate)

    threads_out: list[dict[str, Any]] = []
    for row in page_rows:
        latest = latest_by_patient.get(row.patient_id)
        threads_out.append(
            {
                "patient_id": row.patient_id,
                "patient_name": names.get(row.patient_id),
                "latest_message_id": latest.id if latest else None,
                "latest_direction": latest.direction if latest else None,
                "latest_text_body": latest.text_body if latest else None,
                "latest_media_mime_type": latest.media_mime_type if latest else None,
                "latest_at": row.latest_at,
                "inbound_count": int(row.inbound_count),
            }
        )
    return threads_out, total


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
