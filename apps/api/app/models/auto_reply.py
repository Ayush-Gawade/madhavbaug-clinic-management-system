"""AI auto-reply provenance.

One row per inbound message the auto-reply feature decided about. The UNIQUE
``source_message_id`` is the idempotency key: re-analysis or a retried worker
can never send the patient the same reply twice.

An auto-reply never decides care. It reports back what the existing rule engine
already concluded about a reading, and it records enough to audit the model,
prompt version and exact text that went out. Urgent findings additionally notify
the clinic's doctor over WhatsApp; ``doctor_notified_at`` makes that one-shot.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AutoReplyMode(enum.StrEnum):
    """Why the reply was generated."""

    SAFE_READING = "safe_reading"
    OUT_OF_RANGE_READING = "out_of_range_reading"
    CLARIFICATION = "clarification"


class AutoReplyStatus(enum.StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    #: Deliberately not sent (cooldown, toggle flipped off between analysis and
    #: delivery). The row still records the decision, so an urgent finding on the
    #: same message still reaches the doctor exactly once.
    SUPPRESSED = "suppressed"


def _enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    """Build a native PostgreSQL enum from a StrEnum."""
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class AutoReply(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The auto-reply generated for one inbound patient message."""

    __tablename__ = "auto_replies"
    __table_args__ = (
        Index("ix_auto_replies_patient", "patient_id"),
        Index("ix_auto_replies_status", "status"),
    )

    source_message_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("whatsapp_messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # idempotency: one reply per inbound message, ever
    )
    reply_message_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("whatsapp_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="SET NULL"),
        nullable=True,
    )
    mode: Mapped[AutoReplyMode] = mapped_column(
        _enum(AutoReplyMode, "auto_reply_mode"), nullable=False
    )
    status: Mapped[AutoReplyStatus] = mapped_column(
        _enum(AutoReplyStatus, "auto_reply_status"),
        nullable=False,
        default=AutoReplyStatus.PENDING,
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    generated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    doctor_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AutoReply {self.source_message_id} {self.mode} {self.status}>"
