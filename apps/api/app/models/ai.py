"""AI extraction provenance models.

The AI layer may extract structured data from a patient's message, but it never
decides care and never silently alters a plan (PRD FR-018, FR-020). Every model
invocation is recorded here so a reading can always be traced back to the model,
prompt version and raw response that produced it.
"""

from __future__ import annotations

import enum
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AIExtractionModality(enum.StrEnum):
    TEXT = "text"
    VISION = "vision"


class AIExtractionStatus(enum.StrEnum):
    SUCCEEDED = "succeeded"
    NEEDS_CLARIFICATION = "needs_clarification"
    SKIPPED = "skipped"
    FAILED = "failed"


def _enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    """Build a native PostgreSQL enum from a StrEnum."""
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class AIExtraction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One AI analysis of a single inbound message (provenance record)."""

    __tablename__ = "ai_extractions"
    __table_args__ = (
        Index("ix_ai_extractions_patient", "patient_id"),
        Index("ix_ai_extractions_message", "message_id"),
        Index("ix_ai_extractions_status", "status"),
    )

    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("whatsapp_messages.id", ondelete="SET NULL"), nullable=True
    )
    modality: Mapped[AIExtractionModality] = mapped_column(
        _enum(AIExtractionModality, "ai_extraction_modality"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[AIExtractionStatus] = mapped_column(
        _enum(AIExtractionStatus, "ai_extraction_status"), nullable=False
    )
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    needs_clarification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    clarification_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    observations_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
