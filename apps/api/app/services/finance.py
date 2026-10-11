"""Finance services: catalog, assignments, payments, estimator (PRD FR-033..FR-038)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.models.finance import (
    PatientTreatmentAssignment,
    Payment,
    PaymentType,
    Treatment,
    TreatmentAssignmentStatus,
)
from app.models.user import StaffRole, StaffUser
from app.schemas.finance import (
    EstimateRequest,
    EstimateResult,
    FinanceLine,
    FinanceSummary,
    PaymentCreate,
    PaymentRead,
    TreatmentAssign,
    TreatmentCreate,
    TreatmentUpdate,
)


def _money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _percent(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


# -- Estimate / boundary math ------------------------------------------------


def _boundary_quantities(treatment: Treatment) -> tuple[Decimal, Decimal]:
    """Return (r_min_allowed, d_max_allowed) under the configured boundaries."""
    royalty_rate = _percent(treatment.royalty_percent) / Decimal("100")
    fixed_direct = (
        _money(treatment.therapist_cost)
        + _money(treatment.material_cost)
        + _money(treatment.other_direct_cost)
    )
    overhead = _money(treatment.overhead_allocation)
    margin = Decimal(str(settings.finance_min_contribution_margin))
    min_profit = _money(settings.finance_min_profit)

    r_min = Decimal("0")
    denominator_margin = Decimal("1") - royalty_rate - margin
    if denominator_margin > 0:
        r_min = max(r_min, _money(fixed_direct / denominator_margin))
    denominator_profit = Decimal("1") - royalty_rate
    if denominator_profit > 0:
        r_min = max(r_min, _money((fixed_direct + overhead + min_profit) / denominator_profit))

    list_price = _money(treatment.list_price)
    d_max = Decimal("1")
    if list_price > 0 and r_min > 0:
        d_max = Decimal("1") - _money(r_min / list_price)
        d_max = max(Decimal("0"), d_max)

    official_max = min(d_max, _percent(settings.finance_max_discount_default))
    return r_min, min(d_max, official_max)


def estimate_treatment(treatment: Treatment, discount_percent: Decimal) -> EstimateResult:
    """Compute the financial outcome of a proposed discount on a treatment."""
    list_price = _money(treatment.list_price)
    discount = _percent(discount_percent) / Decimal("100")
    revenue = _money(list_price * (Decimal("1") - discount))
    royalty = _money(revenue * _percent(treatment.royalty_percent) / Decimal("100"))
    therapist = _money(treatment.therapist_cost)
    material = _money(treatment.material_cost)
    other = _money(treatment.other_direct_cost)
    overhead = _money(treatment.overhead_allocation)
    direct_cost = royalty + therapist + material + other
    contribution = revenue - direct_cost
    margin = (contribution / revenue * Decimal("100")) if revenue > 0 else Decimal("0")

    r_min, d_max = _boundary_quantities(treatment)
    violates = (
        revenue < r_min or discount_percent > _percent(settings.finance_max_discount_default) * 100
    )

    warnings: list[str] = []
    if violates:
        warnings.append(
            "The proposed discount breaches the configured minimum profitability boundary."
        )

    return EstimateResult(
        treatment_id=treatment.id,
        name=treatment.name,
        treatment_code=treatment.treatment_code,
        list_price=list_price,
        discount_percent=_percent(discount_percent),
        estimated_revenue=revenue,
        royalty=royalty,
        therapist_cost=therapist,
        material_cost=material,
        other_direct_cost=other,
        overhead_allocation=overhead,
        total_direct_cost=direct_cost + overhead,
        contribution=_money(contribution),
        contribution_margin_percent=_percent(margin),
        allocated_net_profit=_money(contribution - overhead),
        min_contribution_margin=_percent(settings.finance_min_contribution_margin * 100),
        max_allowable_discount_percent=_percent(d_max * 100),
        official_max_discount_percent=_percent(
            min(d_max, _percent(settings.finance_max_discount_default)) * 100
        ),
        violates_boundary=violates,
        warnings=warnings,
    )


async def require_estimate(db: AsyncSession, request: EstimateRequest) -> EstimateResult:
    treatment = await require_treatment(db, request.treatment_id)
    return estimate_treatment(treatment, request.discount_percent)


def check_discount_authorization(actor: StaffUser, discount_percent: Decimal | None) -> None:
    """Reject discounts above the clinic default unless the owner overrides (FR-038)."""
    if discount_percent is None:
        return
    max_default = _percent(settings.finance_max_discount_default * 100)
    if discount_percent > max_default and actor.role != StaffRole.OWNER:
        raise PermissionDeniedError(f"Discounts above {max_default}% require owner authorization.")


# -- Treatment catalog --------------------------------------------------------


async def create_treatment(db: AsyncSession, data: TreatmentCreate) -> Treatment:
    existing = await db.scalar(
        select(Treatment).where(Treatment.treatment_code == data.treatment_code.strip().upper())
    )
    if existing is not None:
        raise ConflictError("A treatment with this code already exists.")
    treatment = Treatment(**data.model_dump())
    db.add(treatment)
    await db.flush()
    return treatment


async def require_treatment(db: AsyncSession, treatment_id: uuid.UUID) -> Treatment:
    treatment = await db.get(Treatment, treatment_id)
    if treatment is None:
        raise NotFoundError("Treatment not found.")
    return treatment


async def update_treatment(
    db: AsyncSession, treatment: Treatment, data: TreatmentUpdate
) -> Treatment:
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(treatment, field, value)
    await db.flush()
    return treatment


async def list_treatments(db: AsyncSession, *, active_only: bool = True) -> list[Treatment]:
    query = select(Treatment).order_by(Treatment.name.asc())
    if active_only:
        query = query.where(Treatment.is_active.is_(True))
    result = await db.execute(query)
    return list(result.scalars().all())


# -- Assignments ---------------------------------------------------------------


async def assign_treatment(
    db: AsyncSession, patient_id: uuid.UUID, data: TreatmentAssign, actor: StaffUser
) -> PatientTreatmentAssignment:
    treatment = await require_treatment(db, data.treatment_id)
    if not treatment.is_active:
        raise ConflictError("This treatment is inactive and cannot be assigned.")
    check_discount_authorization(actor, data.discount_percent)

    active = await db.scalar(
        select(func.count())
        .select_from(PatientTreatmentAssignment)
        .where(
            PatientTreatmentAssignment.patient_id == patient_id,
            PatientTreatmentAssignment.treatment_id == data.treatment_id,
            PatientTreatmentAssignment.status == TreatmentAssignmentStatus.ACTIVE,
        )
    )
    if active:
        raise ConflictError("This patient already has an active assignment for this treatment.")

    assignment = PatientTreatmentAssignment(
        patient_id=patient_id,
        treatment_id=data.treatment_id,
        status=data.status,
        discount_percent=data.discount_percent,
        start_date=data.start_date,
        end_date=data.end_date,
        assigned_by=actor.id,
    )
    db.add(assignment)
    await db.flush()
    return assignment


async def list_assignments(
    db: AsyncSession, patient_id: uuid.UUID
) -> list[PatientTreatmentAssignment]:
    result = await db.execute(
        select(PatientTreatmentAssignment)
        .where(PatientTreatmentAssignment.patient_id == patient_id)
        .order_by(PatientTreatmentAssignment.created_at.desc())
    )
    return list(result.scalars().all())


# -- Payments ------------------------------------------------------------------


async def record_payment(
    db: AsyncSession, patient_id: uuid.UUID, data: PaymentCreate, actor: StaffUser
) -> Payment:
    if data.treatment_id is not None:
        await require_treatment(db, data.treatment_id)

    related: Payment | None = None
    if data.related_payment_id is not None:
        related = await db.get(Payment, data.related_payment_id)
        if related is None:
            raise NotFoundError("Related payment not found.")

    if data.payment_type == PaymentType.REFUND:
        if related is None:
            raise ValidationError(
                "A refund must reference the original payment via related_payment_id."
            )
        if related.patient_id != patient_id:
            raise ConflictError("The related payment belongs to a different patient.")
        if related.payment_type != PaymentType.PAYMENT:
            raise ConflictError("A refund must reference an original payment, not another refund.")
        already_refunded = (
            await db.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.related_payment_id == related.id,
                    Payment.payment_type == PaymentType.REFUND,
                )
            )
        ).scalar_one()
        remaining = _money(related.amount) - _money(already_refunded)
        if _money(data.amount) > remaining:
            raise ConflictError(
                f"Refund exceeds the refundable balance of {remaining} for this payment."
            )
    elif related is not None:
        raise ValidationError("Only refunds may reference an earlier payment.")

    payment = Payment(
        patient_id=patient_id,
        treatment_id=data.treatment_id,
        payment_type=data.payment_type,
        amount=_money(data.amount),
        payment_date=data.payment_date or datetime.now(UTC),
        payment_method=data.payment_method,
        reference=data.reference,
        notes=data.notes,
        related_payment_id=data.related_payment_id,
        recorded_by=actor.id,
    )
    db.add(payment)
    await db.flush()
    return payment


async def list_payments(db: AsyncSession, patient_id: uuid.UUID) -> list[Payment]:
    result = await db.execute(
        select(Payment)
        .where(Payment.patient_id == patient_id)
        .order_by(Payment.payment_date.desc())
    )
    return list(result.scalars().all())


# -- Summary -------------------------------------------------------------------


async def finance_summary(db: AsyncSession, patient_id: uuid.UUID) -> FinanceSummary:
    assignments = await list_assignments(db, patient_id)
    payments = await list_payments(db, patient_id)

    lines: list[FinanceLine] = []
    total_charges = Decimal("0.00")
    for assignment in assignments:
        if assignment.status != TreatmentAssignmentStatus.ACTIVE:
            continue
        treatment = await require_treatment(db, assignment.treatment_id)
        discount = _percent(assignment.discount_percent or 0) / Decimal("100")
        charge = _money(_money(treatment.list_price) * (Decimal("1") - discount))
        total_charges += charge
        lines.append(
            FinanceLine(
                treatment_id=treatment.id,
                name=treatment.name,
                list_price=_money(treatment.list_price),
                discount_percent=assignment.discount_percent,
                charge=charge,
            )
        )

    total_paid = sum(
        (_money(p.amount) if p.payment_type == PaymentType.PAYMENT else -_money(p.amount))
        for p in payments
    )
    total_paid = _money(total_paid)
    outstanding = _money(total_charges - total_paid)

    return FinanceSummary(
        total_charges=_money(total_charges),
        total_paid=total_paid,
        outstanding=outstanding,
        lines=lines,
        recent_payments=[PaymentRead.model_validate(p) for p in payments[:20]],
    )
