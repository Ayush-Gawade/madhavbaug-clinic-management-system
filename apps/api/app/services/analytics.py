"""Analytics and reporting services (PRD FR-028..FR-043).

Everything here is read-only aggregation over existing records. Where a figure is
derived rather than recorded (for example estimated treatment costs) the response
labels it explicitly so the UI never presents an estimate as settled revenue.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AIExtraction, AIExtractionStatus
from app.models.alerts import Alert, AlertPriority, AlertStatus
from app.models.clinical import (
    Observation,
    ObservationReviewStatus,
    ObservationSource,
    Patient,
    PatientCategory,
    PatientStatus,
)
from app.models.finance import (
    PatientTreatmentAssignment,
    Payment,
    PaymentType,
    Treatment,
    TreatmentAssignmentStatus,
)
from app.models.messaging import (
    DeliveryStatus,
    ExceptionStatus,
    MessageDirection,
    MessageException,
    MessageProcessingStatus,
    WhatsAppMessage,
)
from app.models.scheduling import FollowUpInstance, FollowUpInstanceStatus, FollowUpSchedule
from app.schemas.analytics import (
    AdherenceSummary,
    CategoryCount,
    ClinicOverview,
    DailyActionItem,
    DailyOperations,
    FinanceOverview,
    FinanceTreatmentLine,
    ObservationTrend,
    TrendPoint,
)
from app.services import finance as finance_service
from app.services import schedules as schedules_service

_PRIORITY_RANK: dict[AlertPriority, int] = {
    AlertPriority.URGENT: 0,
    AlertPriority.PRIORITY: 1,
    AlertPriority.ROUTINE: 2,
}

_AWAITING_STATUSES = (
    FollowUpInstanceStatus.SCHEDULED,
    FollowUpInstanceStatus.QUEUED,
    FollowUpInstanceStatus.SENT,
    FollowUpInstanceStatus.DELIVERED,
    FollowUpInstanceStatus.READ,
)


async def _count(db: AsyncSession, model: type, *filters: ColumnElement[bool]) -> int:
    stmt = select(func.count()).select_from(model)
    if filters:
        stmt = stmt.where(*filters)
    return int((await db.execute(stmt)).scalar_one())


# -- Clinic overview (FR-040) -------------------------------------------------


async def clinic_overview(db: AsyncSession) -> ClinicOverview:
    total_patients = await _count(db, Patient)
    active_patients = await _count(db, Patient, Patient.status == PatientStatus.ACTIVE)

    category_rows = (
        await db.execute(
            select(PatientCategory.category_type, func.count())
            .select_from(PatientCategory)
            .group_by(PatientCategory.category_type)
        )
    ).all()
    category_counts = [
        CategoryCount(category_type=category, count=int(count)) for category, count in category_rows
    ]

    day = await schedules_service.day_counts(db)

    failed_deliveries = await _count(
        db,
        WhatsAppMessage,
        WhatsAppMessage.direction == MessageDirection.OUTBOUND,
        WhatsAppMessage.delivery_status == DeliveryStatus.FAILED,
    )
    pending_clarifications = await _count(
        db,
        WhatsAppMessage,
        WhatsAppMessage.processing_status == MessageProcessingStatus.NEEDS_CLARIFICATION,
    )
    open_alerts = await _count(db, Alert, Alert.status == AlertStatus.OPEN)
    open_urgent_alerts = await _count(
        db,
        Alert,
        Alert.status == AlertStatus.OPEN,
        Alert.priority == AlertPriority.URGENT,
    )
    pending_observation_reviews = await _count(
        db, Observation, Observation.review_status == ObservationReviewStatus.PENDING
    )
    ai_needs_clarification = await _count(
        db, AIExtraction, AIExtraction.status == AIExtractionStatus.NEEDS_CLARIFICATION
    )
    open_message_exceptions = await _count(
        db, MessageException, MessageException.status == ExceptionStatus.OPEN
    )

    return ClinicOverview(
        total_patients=total_patients,
        active_patients=active_patients,
        category_counts=category_counts,
        follow_ups_due_today=int(day["due_today"]),
        follow_ups_completed_today=int(day["done_today"]),
        follow_ups_overdue=int(day["overdue"]),
        failed_deliveries=failed_deliveries,
        pending_clarifications=pending_clarifications,
        open_alerts=open_alerts,
        open_urgent_alerts=open_urgent_alerts,
        pending_observation_reviews=pending_observation_reviews,
        ai_needs_clarification=ai_needs_clarification,
        open_message_exceptions=open_message_exceptions,
    )


# -- Daily operations (FR-043) ------------------------------------------------


async def daily_operations(db: AsyncSession) -> DailyOperations:
    """Consolidated list of patients requiring action, ordered by priority (FR-043)."""
    reasons: dict[uuid.UUID, list[str]] = {}
    names: dict[uuid.UUID, str] = {}
    ranks: dict[uuid.UUID, int] = {}
    latest: dict[uuid.UUID, datetime] = {}

    def add(
        patient_id: uuid.UUID,
        patient_name: str,
        reason: str,
        priority: AlertPriority,
        when: datetime,
    ) -> None:
        bucket = reasons.setdefault(patient_id, [])
        if reason not in bucket:
            bucket.append(reason)
        names[patient_id] = patient_name
        ranks[patient_id] = min(ranks.get(patient_id, 99), _PRIORITY_RANK[priority])
        if patient_id not in latest or when > latest[patient_id]:
            latest[patient_id] = when

    overdue_rows = (
        await db.execute(
            select(FollowUpInstance, Patient, FollowUpSchedule)
            .join(Patient, Patient.id == FollowUpInstance.patient_id)
            .join(FollowUpSchedule, FollowUpSchedule.id == FollowUpInstance.schedule_id)
            .where(FollowUpInstance.status == FollowUpInstanceStatus.OVERDUE)
            .order_by(FollowUpInstance.due_at.asc())
            .limit(100)
        )
    ).all()
    for instance, patient, schedule in overdue_rows:
        add(
            patient.id,
            patient.full_name,
            f"Overdue {schedule.follow_up_type.value} check-in",
            AlertPriority.PRIORITY,
            instance.due_at or datetime.now(UTC),
        )

    alert_rows = (
        await db.execute(
            select(Alert, Patient)
            .join(Patient, Patient.id == Alert.patient_id)
            .where(Alert.status == AlertStatus.OPEN)
            .order_by(Alert.created_at.desc())
            .limit(100)
        )
    ).all()
    for alert, patient in alert_rows:
        add(patient.id, patient.full_name, alert.reason, alert.priority, alert.created_at)

    items = [
        DailyActionItem(
            patient_id=patient_id,
            patient_name=names[patient_id],
            reasons=reasons[patient_id],
            priority=_rank_priority(ranks[patient_id]),
            latest_activity=latest[patient_id],
        )
        for patient_id in reasons
    ]
    items.sort(key=lambda item: (_PRIORITY_RANK[item.priority], -item.latest_activity.timestamp()))
    return DailyOperations(generated_at=datetime.now(UTC), total=len(items), items=items)


def _rank_priority(rank: int) -> AlertPriority:
    for priority, value in _PRIORITY_RANK.items():
        if value == rank:
            return priority
    return AlertPriority.ROUTINE


# -- Adherence (FR-031) -------------------------------------------------------


async def adherence_summary(
    db: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    patient_id: uuid.UUID | None = None,
) -> AdherenceSummary:
    filters = [
        FollowUpInstance.due_date >= date_from,
        FollowUpInstance.due_date <= date_to,
    ]
    if patient_id is not None:
        filters.append(FollowUpInstance.patient_id == patient_id)

    rows = (
        await db.execute(
            select(FollowUpInstance.status, func.count())
            .select_from(FollowUpInstance)
            .where(*filters)
            .group_by(FollowUpInstance.status)
        )
    ).all()
    by_status = {status: int(count) for status, count in rows}

    scheduled_total = sum(by_status.values())
    completed = by_status.get(FollowUpInstanceStatus.RESPONDED, 0)
    overdue = by_status.get(FollowUpInstanceStatus.OVERDUE, 0)
    skipped = by_status.get(FollowUpInstanceStatus.SKIPPED, 0)
    failed = by_status.get(FollowUpInstanceStatus.FAILED, 0)
    awaiting = sum(by_status.get(status, 0) for status in _AWAITING_STATUSES)

    denominator = scheduled_total - skipped - failed
    rate = (
        (Decimal(completed) / Decimal(denominator) * Decimal("100"))
        if denominator > 0
        else Decimal("0")
    )
    return AdherenceSummary(
        date_from=date_from,
        date_to=date_to,
        scheduled_total=scheduled_total,
        completed=completed,
        overdue=overdue,
        skipped=skipped,
        failed_deliveries=failed,
        awaiting_response=awaiting,
        completion_rate_percent=rate.quantize(Decimal("0.01")),
        rate_definition=(
            "completed / (scheduled check-ins - skipped - failed deliveries). "
            "Unsubmitted check-ins are excluded from the numerator; provider "
            "delivery failures are counted separately from patient non-response."
        ),
    )


# -- Observation trends (FR-029, FR-030) --------------------------------------


def _bucket_start(value: date, granularity: str) -> date:
    if granularity == "week":
        return value - timedelta(days=value.weekday())
    if granularity == "month":
        return value.replace(day=1)
    return value


def _expected_buckets(date_from: date, date_to: date, granularity: str) -> list[date]:
    buckets: list[date] = []
    current = _bucket_start(date_from, granularity)
    end = _bucket_start(date_to, granularity)
    while current <= end:
        buckets.append(current)
        if granularity == "week":
            current += timedelta(days=7)
        elif granularity == "month":
            current = (current + timedelta(days=32)).replace(day=1)
        else:
            current += timedelta(days=1)
    return buckets


async def observation_trends(
    db: AsyncSession,
    *,
    patient_id: uuid.UUID,
    observation_type: str,
    granularity: str,
    date_from: date,
    date_to: date,
) -> ObservationTrend:
    rows = list(
        (
            await db.execute(
                select(Observation)
                .where(
                    Observation.patient_id == patient_id,
                    Observation.observation_type == observation_type,
                    func.date(Observation.observed_at) >= date_from,
                    func.date(Observation.observed_at) <= date_to,
                )
                .order_by(Observation.observed_at.asc())
            )
        )
        .scalars()
        .all()
    )

    grouped: dict[date, list[Observation]] = defaultdict(list)
    for observation in rows:
        grouped[_bucket_start(observation.observed_at.date(), granularity)].append(observation)

    points: list[TrendPoint] = []
    for bucket in sorted(grouped):
        group = grouped[bucket]
        values = [obs.value for obs in group if obs.value is not None]
        average = (
            (sum(values) / Decimal(len(values))).quantize(Decimal("0.01"))
            if values
            else Decimal("0")
        )
        latest = max(group, key=lambda obs: obs.observed_at)
        verified = sum(1 for obs in group if obs.source == ObservationSource.STAFF_ENTRY)
        points.append(
            TrendPoint(
                bucket=bucket,
                average_value=average,
                latest_value=latest.value,
                count=len(group),
                verified_count=verified,
                patient_reported_count=len(group) - verified,
            )
        )

    unit = rows[-1].unit if rows else None
    expected = _expected_buckets(date_from, date_to, granularity)
    missing = len([bucket for bucket in expected if bucket not in grouped])
    return ObservationTrend(
        patient_id=patient_id,
        observation_type=observation_type,
        unit=unit,
        granularity=granularity,
        date_from=date_from,
        date_to=date_to,
        points=points,
        missing_buckets=missing,
    )


# -- Finance overview (FR-042) ------------------------------------------------


async def finance_overview(db: AsyncSession) -> FinanceOverview:
    assignment_rows = (
        await db.execute(
            select(PatientTreatmentAssignment, Treatment)
            .join(Treatment, Treatment.id == PatientTreatmentAssignment.treatment_id)
            .where(PatientTreatmentAssignment.status == TreatmentAssignmentStatus.ACTIVE)
        )
    ).all()

    total_charges = Decimal("0.00")
    estimated_direct_costs = Decimal("0.00")
    estimated_contribution = Decimal("0.00")
    lines: dict[uuid.UUID, FinanceTreatmentLine] = {}
    for assignment, treatment in assignment_rows:
        result = finance_service.estimate_treatment(
            treatment, assignment.discount_percent or Decimal("0")
        )
        charge = result.estimated_revenue
        direct = (
            result.royalty + result.therapist_cost + result.material_cost + result.other_direct_cost
        )
        total_charges += charge
        estimated_direct_costs += direct
        estimated_contribution += result.contribution
        existing = lines.get(treatment.id)
        if existing is None:
            lines[treatment.id] = FinanceTreatmentLine(
                treatment_id=treatment.id,
                name=treatment.name,
                assignments=1,
                billed=charge,
                estimated_direct_costs=direct,
                estimated_contribution=result.contribution,
            )
        else:
            existing.assignments += 1
            existing.billed += charge
            existing.estimated_direct_costs += direct
            existing.estimated_contribution += result.contribution

    payment_rows = (
        await db.execute(
            select(Payment.payment_type, func.coalesce(func.sum(Payment.amount), 0)).group_by(
                Payment.payment_type
            )
        )
    ).all()
    by_type = dict(payment_rows)
    recorded_revenue = finance_service._money(by_type.get(PaymentType.PAYMENT, Decimal("0")))
    recorded_refunds = finance_service._money(by_type.get(PaymentType.REFUND, Decimal("0")))
    adjustments = finance_service._money(by_type.get(PaymentType.ADJUSTMENT, Decimal("0")))
    net_recorded = finance_service._money(recorded_revenue - recorded_refunds + adjustments)
    outstanding = finance_service._money(total_charges - net_recorded)
    margin = (
        finance_service._percent(estimated_contribution / total_charges * Decimal("100"))
        if total_charges > 0
        else Decimal("0")
    )

    return FinanceOverview(
        total_charges=finance_service._money(total_charges),
        recorded_revenue=recorded_revenue,
        recorded_refunds=recorded_refunds,
        net_recorded_revenue=net_recorded,
        outstanding=outstanding,
        estimated_direct_costs=finance_service._money(estimated_direct_costs),
        estimated_contribution=finance_service._money(estimated_contribution),
        estimated_contribution_margin_percent=margin,
        lines=sorted(lines.values(), key=lambda line: line.billed, reverse=True),
        notes=[
            "Recorded revenue, refunds and adjustments come from posted payments.",
            "Billed charges, direct costs and contribution are estimates based on the "
            "configured treatment cost model.",
            "Contribution excludes allocated fixed overheads; it is not total net profit.",
        ],
    )
