"""Pydantic schemas for WhatsApp messaging."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.messaging import (
    DeliveryStatus,
    ExceptionReason,
    ExceptionStatus,
    MessageDirection,
    MessageProcessingStatus,
    MessageType,
)
from app.services import media as media_service


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID | None
    follow_up_instance_id: uuid.UUID | None
    direction: MessageDirection
    provider_message_id: str | None
    message_type: MessageType
    from_phone: str | None
    to_phone: str | None
    text_body: str | None
    media_reference: str | None
    media_mime_type: str | None
    template_code: str | None
    delivery_status: DeliveryStatus | None
    processing_status: MessageProcessingStatus
    error_code: str | None
    error_message: str | None
    provider_timestamp: datetime | None
    sent_at: datetime | None
    received_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def media_url(self) -> str | None:
        """A signed, expiring URL when this message carries stored media."""
        if not self.media_mime_type:
            return None
        return media_service.media_url(self.id)


class MessageExceptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID | None
    message_id: uuid.UUID | None
    reason: ExceptionReason
    status: ExceptionStatus
    details: dict[str, Any] | None
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    resolution_notes: str | None
    created_at: datetime
    updated_at: datetime


class ExceptionResolve(BaseModel):
    resolved: bool = True
    notes: str | None = Field(default=None, max_length=2000)


class DispatchResult(BaseModel):
    sent: int
    failed: int
    held: int
    scanned: int


class WebhookResult(BaseModel):
    duplicate: int
    messages: int
    statuses: int
