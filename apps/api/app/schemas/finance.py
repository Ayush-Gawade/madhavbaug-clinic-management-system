"""Financial module schemas: treatments, assignments, payments, estimator."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.finance import (
    PaymentMethod,
    PaymentType,
    TreatmentAssignmentStatus,
)

# -- Treatment catalog --------------------------------------------------------


class TreatmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    treatment_code: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    service_category: str | None = Field(default=None, max_length=100)
    list_price: Decimal = Field(ge=0)
    estimated_sessions: int | None = Field(default=None, ge=1)
    royalty_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    therapist_cost: Decimal = Field(default=Decimal("0"), ge=0)
    material_cost: Decimal = Field(default=Decimal("0"), ge=0)
    other_direct_cost: Decimal = Field(default=Decimal("0"), ge=0)
    overhead_allocation: Decimal = Field(default=Decimal("0"), ge=0)
    cost_effective_from: date | None = None
    is_active: bool = True

    @field_validator("treatment_code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class TreatmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    service_category: str | None = Field(default=None, max_length=100)
    list_price: Decimal | None = Field(default=None, ge=0)
    estimated_sessions: int | None = Field(default=None, ge=1)
    royalty_percent: Decimal | None = Field(default=None, ge=0, le=100)
    therapist_cost: Decimal | None = Field(default=None, ge=0)
    material_cost: Decimal | None = Field(default=None, ge=0)
    other_direct_cost: Decimal | None = Field(default=None, ge=0)
    overhead_allocation: Decimal | None = Field(default=None, ge=0)
    cost_effective_from: date | None = None
    is_active: bool | None = None


class TreatmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    treatment_code: str
    description: str | None
    service_category: str | None
    list_price: Decimal
    estimated_sessions: int | None
    royalty_percent: Decimal
    therapist_cost: Decimal
    material_cost: Decimal
    other_direct_cost: Decimal
    overhead_allocation: Decimal
    cost_effective_from: date | None
    is_active: bool


# -- Assignments --------------------------------------------------------------


class TreatmentAssign(BaseModel):
    treatment_id: uuid.UUID
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    start_date: date | None = None
    end_date: date | None = None
    status: TreatmentAssignmentStatus = TreatmentAssignmentStatus.ACTIVE


class PatientTreatmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    treatment_id: uuid.UUID
    status: TreatmentAssignmentStatus
    discount_percent: Decimal | None
    start_date: date | None
    end_date: date | None
    assigned_by: uuid.UUID | None
    treatment: TreatmentRead | None = None


# -- Payments -----------------------------------------------------------------


class PaymentCreate(BaseModel):
    treatment_id: uuid.UUID | None = None
    payment_type: PaymentType = PaymentType.PAYMENT
    amount: Decimal = Field(gt=0)
    payment_date: datetime | None = None
    payment_method: PaymentMethod = PaymentMethod.CASH
    reference: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=500)
    related_payment_id: uuid.UUID | None = None


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    treatment_id: uuid.UUID | None
    payment_type: PaymentType
    amount: Decimal
    payment_date: datetime
    payment_method: PaymentMethod
    reference: str | None
    notes: str | None
    recorded_by: uuid.UUID | None


# -- Summary ------------------------------------------------------------------


class FinanceLine(BaseModel):
    treatment_id: uuid.UUID
    name: str
    list_price: Decimal
    discount_percent: Decimal | None
    charge: Decimal


class FinanceSummary(BaseModel):
    total_charges: Decimal
    total_paid: Decimal
    outstanding: Decimal
    lines: list[FinanceLine]
    recent_payments: list[PaymentRead]


# -- Estimator -----------------------------------------------------------------


class EstimateRequest(BaseModel):
    treatment_id: uuid.UUID
    discount_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)


class EstimateResult(BaseModel):
    treatment_id: uuid.UUID
    name: str
    treatment_code: str
    list_price: Decimal
    discount_percent: Decimal
    estimated_revenue: Decimal
    royalty: Decimal
    therapist_cost: Decimal
    material_cost: Decimal
    other_direct_cost: Decimal
    overhead_allocation: Decimal
    total_direct_cost: Decimal
    contribution: Decimal
    contribution_margin_percent: Decimal
    allocated_net_profit: Decimal
    min_contribution_margin: Decimal
    max_allowable_discount_percent: Decimal
    official_max_discount_percent: Decimal
    violates_boundary: bool
    warnings: list[str]
