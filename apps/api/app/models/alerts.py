"""Rule-engine and alert models.

Safety rules are configurable, versioned and audited (PRD FR-019/020, 7.2).
A rule violation creates a dated alert carrying the triggering value, units and
rule version (FR-019). Alerts move through an explicit review lifecycle with an
append-only clinician-action history (FR-026, data model K).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RuleMetric(enum.StrEnum):
    BLOOD_GLUCOSE = "blood_glucose"
    WEIGHT = "weight"
    SYSTOLIC = "systolic"
    DIASTOLIC = "diastolic"


class RuleComparator(enum.StrEnum):
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


class AlertPriority(enum.StrEnum):
    ROUTINE = "routine"
    PRIORITY = "priority"
    URGENT = "urgent"


class AlertStatus(enum.StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class AlertType(enum.StrEnum):
    THRESHOLD = "threshold"
    NON_RESPONSE = "non_response"
    DELIVERY_FAILURE = "delivery_failure"
    CLARIFICATION = "clarification"
    MANUAL = "manual"


class ClinicianActionType(enum.StrEnum):
    ACKNOWLEDGE = "acknowledge"
    ASSIGN = "assign"
    ESCALATE = "escalate"
    RESOLVE = "resolve"
    DISMISS = "dismiss"
    COMMENT = "comment"


def _enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    """Build a native PostgreSQL enum."""
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class SafetyRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A versioned, deterministic numeric safety rule (PRD FR-019, FR-020).

    A logical rule is identified by ``rule_key``; a new threshold is published as
    a new ``version`` row with the previous row deactivated, so alerts can always
    cite the exact version that produced them.
    """

    __tablename__ = "safety_rules"
    __table_args__ = (
        UniqueConstraint("rule_key", "version", name="uq_safety_rules_rule_key_version"),
        Index("ix_safety_rules_metric", "metric"),
        Index("ix_safety_rules_active", "is_active"),
    )

    rule_key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    metric: Mapped[RuleMetric] = mapped_column(_enum(RuleMetric, "rule_metric"), nullable=False)
    comparator: Mapped[RuleComparator] = mapped_column(
        _enum(RuleComparator, "rule_comparator"), nullable=False
    )
    threshold: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[AlertPriority] = mapped_column(
        _enum(AlertPriority, "alert_priority"), nullable=False
    )
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )


class Alert(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A dated alert raised by a rule violation or workflow condition."""

    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_priority", "priority"),
        Index("ix_alerts_patient", "patient_id"),
        Index("ix_alerts_created", "created_at"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    observation_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("observations.id", ondelete="SET NULL"), nullable=True
    )
    follow_up_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("follow_up_instances.id", ondelete="SET NULL"),
        nullable=True,
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("safety_rules.id", ondelete="SET NULL"), nullable=True
    )
    rule_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alert_type: Mapped[AlertType] = mapped_column(
        _enum(AlertType, "alert_type"), default=AlertType.THRESHOLD, nullable=False
    )
    metric: Mapped[str | None] = mapped_column(String(32), nullable=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    priority: Mapped[AlertPriority] = mapped_column(
        _enum(AlertPriority, "alert_priority"), default=AlertPriority.ROUTINE, nullable=False
    )
    status: Mapped[AlertStatus] = mapped_column(
        _enum(AlertStatus, "alert_status"), default=AlertStatus.OPEN, nullable=False
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
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
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    actions: Mapped[list[ClinicianAction]] = relationship(
        back_populates="alert", cascade="all, delete-orphan", lazy="selectin"
    )


class ClinicianAction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An append-only staff action taken on an alert (PRD FR-026, data model)."""

    __tablename__ = "clinician_actions"
    __table_args__ = (Index("ix_clinician_actions_alert", "alert_id"),)

    alert_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True
    )
    action_type: Mapped[ClinicianActionType] = mapped_column(
        _enum(ClinicianActionType, "clinician_action_type"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    alert: Mapped[Alert] = relationship(back_populates="actions")
