"""Pydantic schemas for the scheduling module."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.scheduling import (
    FollowUpInstanceStatus,
    FollowUpType,
    ScheduleStatus,
    TemplateCategory,
)

RecurrenceFreqIn = Literal["daily", "weekly", "monthly"]


class RecurrenceRule(BaseModel):
    """Validated recurrence rule payload (see services.recurrence)."""

    freq: RecurrenceFreqIn
    interval: int | None = None
    on_weekdays: list[int] | None = Field(default=None, min_length=1, max_length=7)
    day_of_month: int | None = Field(default=None, ge=1, le=31)

    @model_validator(mode="after")
    def _validate_shape(self) -> RecurrenceRule:
        if self.freq == "daily" and (self.interval is None or self.interval < 1):
            raise ValueError("daily recurrence requires interval >= 1")
        if self.freq == "weekly" and not self.on_weekdays:
            raise ValueError("weekly recurrence requires on_weekdays")
        if self.freq == "monthly" and self.day_of_month is None:
            raise ValueError("monthly recurrence requires day_of_month")
        return self


class ReminderPolicy(BaseModel):
    max_reminders: int = Field(default=1, ge=0, le=10)
    interval_hours: int = Field(default=6, ge=1, le=72)


class EscalationPolicy(BaseModel):
    escalate_after_deadline: bool = True
    review_priority: Literal["routine", "priority", "urgent"] = "priority"


class ScheduleCreate(BaseModel):
    patient_id: uuid.UUID
    care_plan_id: uuid.UUID | None = None
    follow_up_type: FollowUpType
    recurrence_rule: RecurrenceRule
    scheduled_local_time: time | None = None
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    message_template_id: uuid.UUID | None = None
    response_deadline_hours: int = Field(default=12, ge=1, le=168)
    reminder_policy: ReminderPolicy | None = None
    escalation_policy: EscalationPolicy | None = None
    status: ScheduleStatus = ScheduleStatus.ACTIVE
    active_from: date | None = None
    active_to: date | None = None
    responsible_staff_id: uuid.UUID | None = None
    message_body: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _validate_range(self) -> ScheduleCreate:
        if self.active_from and self.active_to and self.active_from > self.active_to:
            raise ValueError("active_from must be on or before active_to")
        return self


class ScheduleUpdate(BaseModel):
    status: ScheduleStatus | None = None
    scheduled_local_time: time | None = None
    message_template_id: uuid.UUID | None = None
    message_body: str | None = Field(default=None, max_length=4000)
    response_deadline_hours: int | None = Field(default=None, ge=1, le=168)
    reminder_policy: ReminderPolicy | None = None
    escalation_policy: EscalationPolicy | None = None
    active_from: date | None = None
    active_to: date | None = None
    responsible_staff_id: uuid.UUID | None = None


class ScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    care_plan_id: uuid.UUID | None
    follow_up_type: FollowUpType
    recurrence_rule: dict[str, Any]
    scheduled_local_time: time | None
    timezone: str
    message_template_id: uuid.UUID | None
    message_body: str | None
    response_deadline_hours: int
    reminder_policy: dict[str, Any] | None
    escalation_policy: dict[str, Any] | None
    status: ScheduleStatus
    active_from: date | None
    active_to: date | None
    responsible_staff_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class InstanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    schedule_id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str | None = None
    due_date: date
    due_at: datetime
    sent_at: datetime | None
    response_deadline_at: datetime | None
    status: FollowUpInstanceStatus
    reminder_count: int
    last_reminded_at: datetime | None
    overdue_at: datetime | None
    completed_at: datetime | None
    skip_reason: str | None
    assigned_staff_id: uuid.UUID | None
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None


class MaterializeResult(BaseModel):
    schedule_id: uuid.UUID | None
    instances_created: int
    horizon_days: int
    schedule_count: int


class ProcessDueResult(BaseModel):
    eligible_to_send: int
    skipped_consent: int
    instances_scanned: int


class NonResponseResult(BaseModel):
    instances_scanned: int
    reminders_sent: int
    reminders_failed: int = 0
    marked_overdue: int
    escalations_created: int


class InstanceAcknowledgeRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)


class InstanceAssignRequest(BaseModel):
    staff_id: uuid.UUID
    notes: str | None = Field(default=None, max_length=1000)


class InstanceResolveRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)


class TemplateCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=255)
    category: TemplateCategory
    language: str = Field(default="en", max_length=16)
    body: str = Field(min_length=1, max_length=4000)
    is_active: bool = True
    approved: bool = False


class TemplateUpdate(BaseModel):
    body: str | None = Field(default=None, min_length=1, max_length=4000)
    is_active: bool | None = None
    approved: bool | None = None


class TemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    category: TemplateCategory
    language: str
    body: str
    is_active: bool
    approved: bool
    created_at: datetime
    updated_at: datetime


class FollowUpDayCount(BaseModel):
    due_today: int
    overdue: int
    done_today: int
    patients_due_today: int
    patients_overdue: int
