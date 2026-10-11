"""WhatsApp webhook, manual dispatch and conversation/exception endpoints."""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.api.deps import DbSession, Pagination, require_roles
from app.core.errors import PermissionDeniedError, ValidationError
from app.core.pagination import Page
from app.models.messaging import ExceptionStatus
from app.models.user import StaffRole, StaffUser
from app.schemas.messaging import (
    DispatchResult,
    ExceptionResolve,
    MessageExceptionRead,
    MessageRead,
    WebhookResult,
)
from app.services import audit as audit_service
from app.services import messaging as messaging_service
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
