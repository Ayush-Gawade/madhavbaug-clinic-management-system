"""Pydantic schemas for analytics and reporting (PRD FR-028..FR-043)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.alerts import AlertPriority
from app.models.clinical import PatientCategoryType


class CategoryCount(BaseModel):
    category_type: PatientCategoryType
    count: int


class ClinicOverview(BaseModel):
    """Operational indicators for the clinic overview dashboard (FR-040)."""

    total_patients: int
    active_patients: int
    category_counts: list[CategoryCount]
    follow_ups_due_today: int
    follow_ups_completed_today: int
    follow_ups_overdue: int
    failed_deliveries: int
    pending_clarifications: int
    open_alerts: int
    open_urgent_alerts: int
    pending_observation_reviews: int
    ai_needs_clarification: int
    open_message_exceptions: int


class DailyActionItem(BaseModel):
    """A patient consolidated onto the daily action list (FR-043)."""

    patient_id: uuid.UUID
    patient_name: str
    reasons: list[str]
    priority: AlertPriority
    latest_activity: datetime


class DailyOperations(BaseModel):
    generated_at: datetime
    total: int
    items: list[DailyActionItem]


class AdherenceSummary(BaseModel):
    """Follow-up adherence with an explicit, declared denominator (FR-031)."""

    date_from: date
    date_to: date
    scheduled_total: int
    completed: int
    overdue: int
    skipped: int
    failed_deliveries: int
    awaiting_response: int
    completion_rate_percent: Decimal
    rate_definition: str


class TrendPoint(BaseModel):
    bucket: date
    average_value: Decimal
    latest_value: Decimal | None
    count: int
    verified_count: int
    patient_reported_count: int


class ObservationTrend(BaseModel):
    """Dated observation series for trend visualization (FR-029, FR-030)."""

    patient_id: uuid.UUID
    observation_type: str
    unit: str | None
    granularity: str
    date_from: date
    date_to: date
    points: list[TrendPoint]
    missing_buckets: int


class FinanceTreatmentLine(BaseModel):
    treatment_id: uuid.UUID
    name: str
    assignments: int
    billed: Decimal
    estimated_direct_costs: Decimal
    estimated_contribution: Decimal


class FinanceOverview(BaseModel):
    """Clinic-wide financial summary; recorded amounts vs estimates (FR-042)."""

    total_charges: Decimal
    recorded_revenue: Decimal
    recorded_refunds: Decimal
    net_recorded_revenue: Decimal
    outstanding: Decimal
    estimated_direct_costs: Decimal
    estimated_contribution: Decimal
    estimated_contribution_margin_percent: Decimal
    lines: list[FinanceTreatmentLine]
    notes: list[str]
