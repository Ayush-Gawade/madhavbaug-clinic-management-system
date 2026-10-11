"""Pydantic schemas for AI extraction provenance."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.ai import AIExtractionModality, AIExtractionStatus


class AIExtractionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID | None
    message_id: uuid.UUID | None
    modality: AIExtractionModality
    model: str
    prompt_version: str
    status: AIExtractionStatus
    intent: str | None
    confidence: Decimal | None
    needs_clarification: bool
    clarification_question: str | None
    extracted: dict[str, Any] | None
    error_message: str | None
    observations_created: int
    created_at: datetime
