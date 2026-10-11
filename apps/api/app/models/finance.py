"""Financial data models: treatment catalog, assignments, payments."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TreatmentAssignmentStatus(enum.StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaymentType(enum.StrEnum):
    PAYMENT = "payment"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


class PaymentMethod(enum.StrEnum):
    CASH = "cash"
    CARD = "card"
    UPI = "upi"
    BANK_TRANSFER = "bank_transfer"
    CHEQUE = "cheque"
    OTHER = "other"


def _enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class Treatment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A treatment or package from the clinic catalog (PRD FR-006).

    Cost inputs are placeholders pending the clinic's approved cost model
    (PRD FR-034). All monetary columns are Numeric(12,2).
    """

    __tablename__ = "treatments"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    treatment_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    list_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    estimated_sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    royalty_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0"), nullable=False
    )
    therapist_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    material_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    other_direct_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    overhead_allocation: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    cost_effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PatientTreatmentAssignment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Linking a patient to a treatment with an applied discount (PRD data model T)."""

    __tablename__ = "patient_treatment_assignments"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    treatment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("treatments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[TreatmentAssignmentStatus] = mapped_column(
        _enum(TreatmentAssignmentStatus, "treatment_assignment_status"),
        default=TreatmentAssignmentStatus.ACTIVE,
        nullable=False,
    )
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    treatment: Mapped[Treatment] = relationship(lazy="selectin")


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An itemized payment, refund or adjustment (PRD FR-033).

    Payments are recorded against an explicit treatment where applicable. A
    lump-sum payment is never treated as proof that every treatment is settled.
    """

    __tablename__ = "payments"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    treatment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("treatments.id", ondelete="RESTRICT"),
        nullable=True,
    )
    payment_type: Mapped[PaymentType] = mapped_column(
        _enum(PaymentType, "payment_type"), default=PaymentType.PAYMENT, nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        _enum(PaymentMethod, "payment_method"), default=PaymentMethod.CASH, nullable=False
    )
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    related_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
    )
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )
