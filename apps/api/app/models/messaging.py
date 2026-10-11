"""WhatsApp messaging data models.

Inbound and outbound messages share one event model but keep their direction
and separate processing/delivery statuses distinct (PRD schema section G).
Raw webhook envelopes are stored verbatim for idempotency and audit.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MessageDirection(enum.StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageType(enum.StrEnum):
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"
    TEMPLATE = "template"
    INTERACTIVE = "interactive"
    UNSUPPORTED = "unsupported"


class DeliveryStatus(enum.StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class MessageProcessingStatus(enum.StrEnum):
    RECEIVED = "received"
    QUEUED = "queued"
    PROCESSING = "processing"
    PROCESSED = "processed"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNASSIGNED = "unassigned"
    FAILED = "failed"


class WebhookProcessingStatus(enum.StrEnum):
    RECEIVED = "received"
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    INVALID_SIGNATURE = "invalid_signature"
    FAILED = "failed"


class ExceptionStatus(enum.StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ExceptionReason(enum.StrEnum):
    UNKNOWN_SENDER = "unknown_sender"
    AMBIGUOUS_SENDER = "ambiguous_sender"
    NO_MATCHING_FOLLOW_UP = "no_matching_follow_up"
    AMBIGUOUS_FOLLOW_UP = "ambiguous_follow_up"
    UNSUPPORTED_TYPE = "unsupported_type"
    PROCESSING_ERROR = "processing_error"


def _enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    """Build a native PostgreSQL enum from a StrEnum."""
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class WebhookEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One raw provider webhook delivery, deduplicated by provider event id."""

    __tablename__ = "webhook_events"
    __table_args__ = (Index("ix_webhook_events_provider_event_id", "provider_event_id"),)

    provider_event_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    signature_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processing_status: Mapped[WebhookProcessingStatus] = mapped_column(
        _enum(WebhookProcessingStatus, "webhook_processing_status"),
        default=WebhookProcessingStatus.RECEIVED,
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class WhatsAppMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single inbound or outbound WhatsApp message."""

    __tablename__ = "whatsapp_messages"
    __table_args__ = (
        Index("ix_whatsapp_messages_patient", "patient_id"),
        Index("ix_whatsapp_messages_provider_id", "provider_message_id"),
    )

    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True
    )
    follow_up_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("follow_up_instances.id", ondelete="SET NULL"),
        nullable=True,
    )
    direction: Mapped[MessageDirection] = mapped_column(
        _enum(MessageDirection, "message_direction"), nullable=False
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message_type: Mapped[MessageType] = mapped_column(
        _enum(MessageType, "message_type"), default=MessageType.TEXT, nullable=False
    )
    from_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    text_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    media_mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    template_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivery_status: Mapped[DeliveryStatus | None] = mapped_column(
        _enum(DeliveryStatus, "delivery_status"), nullable=True
    )
    processing_status: Mapped[MessageProcessingStatus] = mapped_column(
        _enum(MessageProcessingStatus, "message_processing_status"),
        default=MessageProcessingStatus.RECEIVED,
        nullable=False,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    delivery_events: Mapped[list[MessageDeliveryEvent]] = relationship(
        back_populates="message", cascade="all, delete-orphan", lazy="selectin"
    )


class MessageDeliveryEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Append-only provider delivery-status transition for a message."""

    __tablename__ = "message_delivery_events"
    __table_args__ = (Index("ix_message_delivery_events_message", "message_id"),)

    message_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("whatsapp_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        _enum(DeliveryStatus, "delivery_status"), nullable=False
    )
    provider_status_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    message: Mapped[WhatsAppMessage] = relationship(back_populates="delivery_events")


class MessageException(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An inbound item that could not be confidently associated or processed."""

    __tablename__ = "message_exceptions"
    __table_args__ = (Index("ix_message_exceptions_status", "status"),)

    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("whatsapp_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[ExceptionReason] = mapped_column(
        _enum(ExceptionReason, "exception_reason"), nullable=False
    )
    status: Mapped[ExceptionStatus] = mapped_column(
        _enum(ExceptionStatus, "exception_status"),
        default=ExceptionStatus.OPEN,
        nullable=False,
    )
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
