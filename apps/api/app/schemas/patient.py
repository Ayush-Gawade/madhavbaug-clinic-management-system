"""Patient and clinical workflow schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.clinical import (
    CarePlanStatus,
    ConsentStatus,
    ConsentType,
    ObservationReviewStatus,
    ObservationSource,
    ObservationValidationStatus,
    PatientCategoryType,
    PatientStatus,
)

# -- Patient ----------------------------------------------------------------


class PatientCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_type: PatientCategoryType
    effective_from: date | None
    effective_to: date | None
    assigned_by: uuid.UUID | None


class PatientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    internal_id: str
    full_name: str
    phone_number: str | None
    preferred_language: str
    date_of_onboarding: date | None
    assigned_clinician_id: uuid.UUID | None
    status: PatientStatus
    dietary_restrictions: dict[str, Any] | None
    communication_preferences: dict[str, Any] | None
    categories: list[PatientCategoryRead]
    created_at: datetime
    updated_at: datetime


class PatientCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    phone_number: str | None = Field(default=None, max_length=32)
    preferred_language: str = Field(default="en", max_length=16)
    date_of_onboarding: date | None = None
    assigned_clinician_id: uuid.UUID | None = None
    status: PatientStatus = PatientStatus.ACTIVE
    dietary_restrictions: dict[str, Any] | None = None
    communication_preferences: dict[str, Any] | None = None
    categories: list[PatientCategoryType] = Field(default_factory=list)

    @field_validator("phone_number")
    @classmethod
    def _strip_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class PatientUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone_number: str | None = Field(default=None, max_length=32)
    preferred_language: str | None = Field(default=None, max_length=16)
    date_of_onboarding: date | None = None
    assigned_clinician_id: uuid.UUID | None = None
    status: PatientStatus | None = None
    dietary_restrictions: dict[str, Any] | None = None
    communication_preferences: dict[str, Any] | None = None

    @field_validator("phone_number")
    @classmethod
    def _strip_phone2(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


# -- Categories -------------------------------------------------------------


class CategoryAssign(BaseModel):
    category_type: PatientCategoryType
    effective_from: date | None = None
    effective_to: date | None = None


# -- Consent ----------------------------------------------------------------


class ConsentCreate(BaseModel):
    consent_type: ConsentType
    purpose: str = Field(min_length=1, max_length=255)
    evidence_reference: str | None = Field(default=None, max_length=255)


class ConsentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    consent_type: ConsentType
    purpose: str
    status: ConsentStatus
    captured_at: datetime
    withdrawn_at: datetime | None
    evidence_reference: str | None
    recorded_by: uuid.UUID | None


# -- Observations -----------------------------------------------------------


class ObservationCreate(BaseModel):
    observation_type: str = Field(min_length=1, max_length=50)
    value: Decimal | None = None
    unit: str | None = Field(default=None, max_length=20)
    observed_at: datetime
    source: ObservationSource = ObservationSource.STAFF_ENTRY
    measurement_context: dict[str, Any] | None = None

    @field_validator("observed_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone offset.")
        return value


class ObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    observation_type: str
    value: Decimal | None
    unit: str | None
    observed_at: datetime
    reported_at: datetime
    source: ObservationSource
    measurement_context: dict[str, Any] | None
    validation_status: ObservationValidationStatus
    review_status: ObservationReviewStatus
    recorded_by: uuid.UUID | None
    ai_extraction_id: uuid.UUID | None = None


# -- Care plans -------------------------------------------------------------


class CarePlanCreate(BaseModel):
    status: CarePlanStatus = CarePlanStatus.ACTIVE
    effective_from: date | None = None
    effective_to: date | None = None
    plan_reference: str | None = Field(default=None, max_length=255)
    content: dict[str, Any] | None = None


class CarePlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    status: CarePlanStatus
    effective_from: date | None
    effective_to: date | None
    approved_by: uuid.UUID | None
    approval_timestamp: datetime | None
    plan_reference: str | None
    content: dict[str, Any] | None
    created_at: datetime


# -- Timeline ---------------------------------------------------------------

TimelineEventType = Literal[
    "observation",
    "care_plan",
    "category",
    "consent",
]


class TimelineEvent(BaseModel):
    event_type: TimelineEventType
    entity_id: str
    occurred_at: datetime
    summary: str
    payload: dict[str, Any]
