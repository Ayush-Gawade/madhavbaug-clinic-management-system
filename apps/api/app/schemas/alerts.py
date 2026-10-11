"""Pydantic schemas for the rule engine and alert queue."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.alerts import (
    AlertPriority,
    AlertStatus,
    AlertType,
    ClinicianActionType,
    RuleComparator,
    RuleMetric,
)


class SafetyRuleCreate(BaseModel):
    rule_key: str = Field(min_length=2, max_length=64)
    metric: RuleMetric
    comparator: RuleComparator
    threshold: Decimal
    unit: str = Field(min_length=1, max_length=20)
    priority: AlertPriority
    description: str | None = Field(default=None, max_length=255)
    context: dict[str, Any] | None = None


class SafetyRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rule_key: str
    version: int
    metric: RuleMetric
    comparator: RuleComparator
    threshold: Decimal
    unit: str
    priority: AlertPriority
    context: dict[str, Any] | None
    description: str | None
    is_active: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ClinicianActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alert_id: uuid.UUID
    patient_id: uuid.UUID | None
    action_type: ClinicianActionType
    actor_id: uuid.UUID | None
    from_status: str | None
    to_status: str | None
    notes: str | None
    occurred_at: datetime


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    observation_id: uuid.UUID | None
    follow_up_instance_id: uuid.UUID | None
    rule_id: uuid.UUID | None
    rule_version: int | None
    metric: str | None
    value: Decimal | None
    unit: str | None
    alert_type: AlertType
    priority: AlertPriority
    status: AlertStatus
    reason: str
    context: dict[str, Any] | None
    assigned_to: uuid.UUID | None
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    resolution_notes: str | None
    created_at: datetime
    updated_at: datetime


class AlertDetailRead(AlertRead):
    actions: list[ClinicianActionRead] = Field(default_factory=list)


class AlertSummary(BaseModel):
    open: int
    acknowledged: int
    resolved: int
    dismissed: int
    open_total: int
    open_urgent: int
    open_priority: int
    open_routine: int


class AlertActionRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class AlertAssignRequest(BaseModel):
    assignee_id: uuid.UUID
    notes: str | None = Field(default=None, max_length=2000)
