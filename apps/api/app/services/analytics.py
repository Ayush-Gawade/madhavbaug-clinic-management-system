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
from typing import Any

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AIExtraction, AIExtractionStatus
from app.models.alerts import Alert, AlertPriority, AlertStatus
from app.models.clinical import (
    Observation,
    ObservationReviewStatus,
    ObservationSource,
    Patient,
    PatientCategory,
    PatientCategoryType,
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
    MessagingOverview,
    ObservationTrend,
    OverviewMessage,
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


# -- Messaging overview (WhatsApp screen A) -----------------------------------


async def _resolve_patient_scope(
    db: AsyncSession,
    *,
    category: PatientCategoryType | None,
    doctor_id: uuid.UUID | None,
    patient_status: PatientStatus | None,
    date_from: date,
    date_to: date,
) -> list[uuid.UUID]:
    """Patient ids matching the overview filters (all patients when unfiltered)."""
    stmt = select(Patient.id)
    filters: list[ColumnElement[bool]] = []
    if patient_status is not None:
        filters.append(Patient.status == patient_status)
    if doctor_id is not None:
        filters.append(Patient.assigned_clinician_id == doctor_id)
    if category is not None:
        filters.append(
            Patient.id.in_(
                select(PatientCategory.patient_id).where(
                    PatientCategory.category_type == category,
                    or_(
                        PatientCategory.effective_from.is_(None),
                        PatientCategory.effective_from <= date_to,
                    ),
                    or_(
                        PatientCategory.effective_to.is_(None),
                        PatientCategory.effective_to >= date_from,
                    ),
                )
            )
        )
    if filters:
        stmt = stmt.where(*filters)
    return list((await db.execute(stmt)).scalars().all())


async def messaging_overview(
    db: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    category: PatientCategoryType | None = None,
    doctor_id: uuid.UUID | None = None,
    patient_status: PatientStatus | None = None,
) -> MessagingOverview:
    """WhatsApp traffic and review queues for a filtered patient scope (screen A)."""
    scoped = category is not None or doctor_id is not None or patient_status is not None
    scope_ids = await _resolve_patient_scope(
        db,
        category=category,
        doctor_id=doctor_id,
        patient_status=patient_status,
        date_from=date_from,
        date_to=date_to,
    )
    if scoped and not scope_ids:
        return MessagingOverview(
            date_from=date_from,
            date_to=date_to,
            patients_in_scope=0,
            messages_sent=0,
            replies_received=0,
            non_responders=0,
            delivery_failures=0,
            critical_alerts=0,
            pending_observation_reviews=0,
            ai_needs_clarification=0,
            open_message_exceptions=0,
            recent_messages=[],
        )

    async def scoped_count(stmt: Select[Any], scope_column: Any) -> int:
        if scoped:
            stmt = stmt.where(scope_column.in_(scope_ids))
        return int((await db.execute(stmt)).scalar_one())

    sent_stmt = (
        select(func.count())
        .select_from(WhatsAppMessage)
        .where(
            WhatsAppMessage.direction == MessageDirection.OUTBOUND,
            WhatsAppMessage.sent_at.is_not(None),
            func.date(WhatsAppMessage.sent_at) >= date_from,
            func.date(WhatsAppMessage.sent_at) <= date_to,
        )
    )
    messages_sent = await scoped_count(sent_stmt, WhatsAppMessage.patient_id)

    replies_stmt = (
        select(func.count())
        .select_from(WhatsAppMessage)
        .where(
            WhatsAppMessage.direction == MessageDirection.INBOUND,
            WhatsAppMessage.received_at.is_not(None),
            func.date(WhatsAppMessage.received_at) >= date_from,
            func.date(WhatsAppMessage.received_at) <= date_to,
        )
    )
    replies_received = await scoped_count(replies_stmt, WhatsAppMessage.patient_id)

    failures_stmt = (
        select(func.count())
        .select_from(WhatsAppMessage)
        .where(
            WhatsAppMessage.direction == MessageDirection.OUTBOUND,
            WhatsAppMessage.delivery_status == DeliveryStatus.FAILED,
            func.date(func.coalesce(WhatsAppMessage.sent_at, WhatsAppMessage.created_at))
            >= date_from,
            func.date(func.coalesce(WhatsAppMessage.sent_at, WhatsAppMessage.created_at))
            <= date_to,
        )
    )
    delivery_failures = await scoped_count(failures_stmt, WhatsAppMessage.patient_id)

    non_responders_stmt = (
        select(func.count(func.distinct(FollowUpInstance.patient_id)))
        .select_from(FollowUpInstance)
        .where(FollowUpInstance.status.in_((*_AWAITING_STATUSES, FollowUpInstanceStatus.OVERDUE)))
    )
    non_responders = await scoped_count(non_responders_stmt, FollowUpInstance.patient_id)

    critical_stmt = (
        select(func.count())
        .select_from(Alert)
        .where(Alert.status == AlertStatus.OPEN, Alert.priority == AlertPriority.URGENT)
    )
    critical_alerts = await scoped_count(critical_stmt, Alert.patient_id)

    reviews_stmt = (
        select(func.count())
        .select_from(Observation)
        .where(Observation.review_status == ObservationReviewStatus.PENDING)
    )
    pending_observation_reviews = await scoped_count(reviews_stmt, Observation.patient_id)

    ai_stmt = (
        select(func.count())
        .select_from(AIExtraction)
        .where(AIExtraction.status == AIExtractionStatus.NEEDS_CLARIFICATION)
    )
    ai_needs_clarification = await scoped_count(ai_stmt, AIExtraction.patient_id)

    exceptions_stmt = (
        select(func.count())
        .select_from(MessageException)
        .where(MessageException.status == ExceptionStatus.OPEN)
    )
    open_message_exceptions = await scoped_count(exceptions_stmt, MessageException.patient_id)

    occurred = func.coalesce(
        WhatsAppMessage.sent_at,
        WhatsAppMessage.received_at,
        WhatsAppMessage.created_at,
    )
    recent_stmt = (
        select(WhatsAppMessage, Patient.full_name)
        .outerjoin(Patient, Patient.id == WhatsAppMessage.patient_id)
        .where(
            func.date(occurred) >= date_from,
            func.date(occurred) <= date_to,
        )
        .order_by(occurred.desc())
        .limit(10)
    )
    if scoped:
        recent_stmt = recent_stmt.where(WhatsAppMessage.patient_id.in_(scope_ids))
    recent_rows = (await db.execute(recent_stmt)).all()
    recent_messages = [
        OverviewMessage(
            id=message.id,
            patient_id=message.patient_id,
            patient_name=name,
            direction=message.direction,
            message_type=message.message_type,
            text_body=message.text_body,
            media_mime_type=message.media_mime_type,
            delivery_status=message.delivery_status,
            occurred_at=message.sent_at or message.received_at or message.created_at,
        )
        for message, name in recent_rows
    ]

    patients_in_scope = len(scope_ids) if scoped else await _count(db, Patient)
    return MessagingOverview(
        date_from=date_from,
        date_to=date_to,
        patients_in_scope=patients_in_scope,
        messages_sent=messages_sent,
        replies_received=replies_received,
        non_responders=non_responders,
        delivery_failures=delivery_failures,
        critical_alerts=critical_alerts,
        pending_observation_reviews=pending_observation_reviews,
        ai_needs_clarification=ai_needs_clarification,
        open_message_exceptions=open_message_exceptions,
        recent_messages=recent_messages,
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
