"""WhatsApp webhook, manual dispatch and conversation/exception endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.api.deps import DbSession, Pagination, require_roles
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from app.core.pagination import Page
from app.models.clinical import Patient
from app.models.messaging import (
    DeliveryStatus,
    ExceptionStatus,
    MessageDirection,
)
from app.models.user import StaffRole, StaffUser
from app.schemas.messaging import (
    DispatchResult,
    ExceptionResolve,
    ManualReplyCreate,
    MessageExceptionRead,
    MessageRead,
    WebhookResult,
)
from app.services import audit as audit_service
from app.services import messaging as messaging_service
from app.services import schedules as schedules_service
from app.services import whatsapp as whatsapp_client

router = APIRouter(tags=["messaging"])

MessagingStaff = Annotated[
    StaffUser,
    Depends(
        require_roles(StaffRole.OWNER, StaffRole.DOCTOR, StaffRole.DIETITIAN, StaffRole.RECEPTION)
    ),
]


@router.get("/whatsapp/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> PlainTextResponse:
    challenge = whatsapp_client.verify_webhook_challenge(hub_mode, hub_verify_token, hub_challenge)
    if challenge is None:
        raise ValidationError("Webhook verification failed.")
    return PlainTextResponse(hub_challenge or "")


@router.post("/whatsapp/webhook", response_model=WebhookResult)
async def receive_webhook(request: Request, db: DbSession) -> WebhookResult:
    raw_body = await request.body()
    signature = request.headers.get("x-hub-signature-256")
    signature_verified = whatsapp_client.verify_signature(raw_body, signature)
    if not signature_verified and whatsapp_client.webhook_signature_required():
        raise PermissionDeniedError("The webhook signature could not be verified.")

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise ValidationError("Malformed webhook payload.") from exc

    result = await messaging_service.process_webhook(
        db, payload, raw_body, signature_verified=signature_verified
    )
    return WebhookResult(**result)


@router.post("/messages/dispatch", response_model=DispatchResult)
async def dispatch_messages(db: DbSession, actor: MessagingStaff) -> DispatchResult:
    result = await messaging_service.dispatch_outbound(db)
    await audit_service.record_event(
        db,
        actor_id=actor.id,
        action="messages.dispatch_run",
        entity_type="system",
        entity_id=uuid.uuid4(),
        change_summary=result,
    )
    return DispatchResult(**result)


@router.get("/patients/{patient_id}/messages", response_model=Page[MessageRead])
async def list_patient_messages(
    patient_id: uuid.UUID, db: DbSession, actor: MessagingStaff, pagination: Pagination
) -> Page[MessageRead]:
    messages, total = await messaging_service.list_conversation(db, patient_id, pagination)
    return Page[MessageRead].create(
        [MessageRead.model_validate(m) for m in messages],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.get(
    "/messages",
    response_model=Page[MessageRead],
    summary="Clinic-wide message list (direction, delivery status, date and text filters)",
)
async def list_all_messages(
    db: DbSession,
    actor: MessagingStaff,
    pagination: Pagination,
    direction: MessageDirection | None = None,
    delivery_status: DeliveryStatus | None = None,
    patient_id: uuid.UUID | None = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    search: Annotated[str | None, Query(min_length=1)] = None,
) -> Page[MessageRead]:
    messages, total = await messaging_service.list_messages(
        db,
        direction=direction,
        delivery_status=delivery_status,
        patient_id=patient_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
        pagination=pagination,
    )
    return Page[MessageRead].create(
        [MessageRead.model_validate(m) for m in messages],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.get("/messages/exceptions", response_model=Page[MessageExceptionRead])
async def list_exceptions(
    db: DbSession,
    actor: MessagingStaff,
    pagination: Pagination,
    status_: Annotated[ExceptionStatus | None, Query(alias="status")] = None,
) -> Page[MessageExceptionRead]:
    exceptions, total = await messaging_service.list_exceptions(
        db, status=status_, pagination=pagination
    )
    return Page[MessageExceptionRead].create(
        [MessageExceptionRead.model_validate(e) for e in exceptions],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.post(
    "/messages/reply",
    response_model=MessageRead,
    summary="Send a manual staff reply (free text inside the 24h window, template outside it)",
)
async def send_manual_reply(
    payload: ManualReplyCreate,
    db: DbSession,
    actor: MessagingStaff,
) -> MessageRead:
    patient = await db.get(Patient, payload.patient_id)
    if patient is None:
        raise NotFoundError("Patient not found.")
    template = None
    if payload.template_id is not None:
        template = await schedules_service.require_template(db, payload.template_id)
    message = await messaging_service.send_manual_reply(
        db,
        patient=patient,
        body=payload.body,
        template=template,
        instance_id=payload.instance_id,
    )
    await audit_service.record_event(
        db,
        actor_id=actor.id,
        action="message.reply_sent",
        entity_type="patient",
        entity_id=patient.id,
        change_summary={
            "message_id": str(message.id),
            "message_type": message.message_type,
            "delivery_status": str(message.delivery_status),
        },
    )
    return MessageRead.model_validate(message)


@router.post(
    "/messages/exceptions/{exception_id}/resolve",
    response_model=MessageExceptionRead,
    status_code=status.HTTP_200_OK,
)
async def resolve_exception(
    exception_id: uuid.UUID,
    payload: ExceptionResolve,
    db: DbSession,
    actor: MessagingStaff,
) -> MessageExceptionRead:
    exception = await messaging_service.resolve_exception(
        db, exception_id, actor=actor, resolved=payload.resolved, notes=payload.notes
    )
    await audit_service.record_event(
        db,
        actor_id=actor.id,
        action="message_exception.resolved",
        entity_type="message_exception",
        entity_id=exception.id,
        change_summary={"resolved": payload.resolved},
    )
    return MessageExceptionRead.model_validate(exception)
