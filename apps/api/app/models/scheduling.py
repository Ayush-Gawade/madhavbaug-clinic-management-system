"""Scheduling and messaging data models.

A schedule is a recurring rule for a single patient (PRD section 6.2, schema
section E); an instance is one concrete occurrence of that rule (section F).
Message templates hold approved outbound content that schedules reference.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.clinical import Patient


class FollowUpType(enum.StrEnum):
    MEAL_CHECK_IN = "meal_check_in"
    WEIGHT = "weight"
    BLOOD_GLUCOSE = "blood_glucose"
    BLOOD_PRESSURE = "blood_pressure"
    OBSERVATION = "observation"
    TREATMENT_ADHERENCE = "treatment_adherence"


class ScheduleStatus(enum.StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class FollowUpInstanceStatus(enum.StrEnum):
    SCHEDULED = "scheduled"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    RESPONDED = "responded"
    OVERDUE = "overdue"
    SKIPPED = "skipped"


class RecurrenceFreq(enum.StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class TemplateCategory(enum.StrEnum):
    SCHEDULED_CHECK_IN = "scheduled_check_in"
    REMINDER = "reminder"
    ACKNOWLEDGEMENT = "acknowledgement"
    CLARIFICATION_REQUEST = "clarification_request"
    HUMAN_ASSISTANCE = "human_assistance"


def _enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    """Build a native PostgreSQL enum from a StrEnum."""
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class MessageTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An approved outbound message template referenced by schedules."""

    __tablename__ = "message_templates"
    __table_args__ = (Index("ix_message_templates_code", "code"),)

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[TemplateCategory] = mapped_column(
        _enum(TemplateCategory, "template_category"), nullable=False
    )
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class FollowUpSchedule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A recurring follow-up rule configured for one patient."""

    __tablename__ = "follow_up_schedules"
    __table_args__ = (Index("ix_follow_up_schedules_patient", "patient_id"),)

    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    care_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("care_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    follow_up_type: Mapped[FollowUpType] = mapped_column(
        _enum(FollowUpType, "follow_up_type"), nullable=False
    )
    recurrence_rule: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    scheduled_local_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
    message_template_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("message_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_deadline_hours: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    reminder_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    escalation_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ScheduleStatus] = mapped_column(
        _enum(ScheduleStatus, "schedule_status"),
        default=ScheduleStatus.ACTIVE,
        nullable=False,
    )
    active_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    active_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsible_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    patient: Mapped[Patient] = relationship(lazy="selectin")
    instances: Mapped[list[FollowUpInstance]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<FollowUpSchedule {self.patient_id} {self.follow_up_type}>"


class FollowUpInstance(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single concrete occurrence of a follow-up schedule."""

    __tablename__ = "follow_up_instances"
    __table_args__ = (
        Index("ix_follow_up_instances_due_at", "due_at"),
        Index("ix_follow_up_instances_status", "status"),
        UniqueConstraint(
            "schedule_id",
            "due_date",
            name="uq_follow_up_instances_schedule_id_due_date",
        ),
    )

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("follow_up_schedules.id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[FollowUpInstanceStatus] = mapped_column(
        _enum(FollowUpInstanceStatus, "follow_up_instance_status"),
        default=FollowUpInstanceStatus.SCHEDULED,
        nullable=False,
    )
    reminder_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reminded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    overdue_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    schedule: Mapped[FollowUpSchedule] = relationship(back_populates="instances", lazy="selectin")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<FollowUpInstance {self.due_date:%Y-%m-%d} {self.status}>"
