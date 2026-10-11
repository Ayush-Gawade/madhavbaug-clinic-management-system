"""Patient and clinical workflow services."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.models.clinical import (
    CarePlan,
    CarePlanStatus,
    ConsentRecord,
    ConsentStatus,
    ConsentType,
    Observation,
    Patient,
    PatientCategory,
    PatientCategoryType,
    PatientStatus,
)
from app.models.user import StaffUser
from app.schemas.patient import (
    CarePlanCreate,
    CategoryAssign,
    ConsentCreate,
    ObservationCreate,
    PatientCreate,
    PatientUpdate,
    TimelineEvent,
)
from app.services import rule_engine


def _make_internal_id() -> str:
    """Generate a human-friendly unique internal patient identifier."""
    return f"MB-{uuid.uuid4().hex[:10].upper()}"


async def get_by_id(db: AsyncSession, patient_id: uuid.UUID) -> Patient | None:
    return await db.get(Patient, patient_id)


async def require_patient(db: AsyncSession, patient_id: uuid.UUID) -> Patient:
    patient = await get_by_id(db, patient_id)
    if patient is None:
        raise NotFoundError("Patient not found.")
    return patient


async def create_patient(db: AsyncSession, data: PatientCreate) -> Patient:
    patient = Patient(
        internal_id=_make_internal_id(),
        full_name=data.full_name,
        phone_number=data.phone_number,
        preferred_language=data.preferred_language,
        date_of_onboarding=data.date_of_onboarding,
        assigned_clinician_id=data.assigned_clinician_id,
        status=data.status,
        dietary_restrictions=data.dietary_restrictions,
        communication_preferences=data.communication_preferences,
    )
    db.add(patient)
    await db.flush()
    for category_type in data.categories:
        db.add(
            PatientCategory(
                patient_id=patient.id,
                category_type=category_type,
                assigned_by=data.assigned_clinician_id,
            )
        )
    await db.flush()
    await db.refresh(patient, attribute_names=["categories"])
    return patient


async def update_patient(
    db: AsyncSession, patient: Patient, data: PatientUpdate, actor: StaffUser
) -> Patient:
    changes = data.model_dump(exclude_unset=True)
    if "phone_number" in changes and changes["phone_number"] == "":
        changes["phone_number"] = None
    for field, value in changes.items():
        setattr(patient, field, value)
    return patient


async def list_patients(
    db: AsyncSession,
    params: PageParams,
    search: str | None = None,
    category: PatientCategoryType | None = None,
    status: PatientStatus | None = None,
    assigned_clinician_id: uuid.UUID | None = None,
) -> tuple[list[Patient], int]:
    query = select(Patient)
    count_query = select(func.count()).select_from(Patient)

    filters = []
    if search:
        pattern = f"%{search.lower()}%"
        filters.append(
            or_(
                func.lower(Patient.full_name).like(pattern),
                func.lower(Patient.internal_id).like(pattern),
                func.lower(func.coalesce(Patient.phone_number, "")).like(pattern),
            )
        )
    if status is not None:
        filters.append(Patient.status == status)
    if category is not None:
        query = query.join(PatientCategory).where(PatientCategory.category_type == category)
        count_query = (
            select(func.count(func.distinct(Patient.id)))
            .select_from(Patient)
            .join(PatientCategory)
            .where(PatientCategory.category_type == category)
        )
    if assigned_clinician_id is not None:
        filters.append(Patient.assigned_clinician_id == assigned_clinician_id)

    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    total = await db.scalar(count_query)
    result = await db.execute(
        query.order_by(Patient.created_at.desc()).offset(params.offset).limit(params.limit)
    )
    return list(result.scalars().all()), int(total or 0)


# -- Categories --------------------------------------------------------------


async def assign_category(
    db: AsyncSession, patient: Patient, data: CategoryAssign, actor: StaffUser
) -> PatientCategory:
    existing = await _get_category(db, patient.id, data.category_type)
    if existing is not None:
        if existing.effective_to is None:
            raise ConflictError(
                f"This patient is already assigned to the {data.category_type.value} category."
            )
        existing.effective_to = None
        existing.effective_from = data.effective_from
        existing.assigned_by = actor.id
        await db.flush()
        return existing

    category = PatientCategory(
        patient_id=patient.id,
        category_type=data.category_type,
        effective_from=data.effective_from,
        effective_to=data.effective_to,
        assigned_by=actor.id,
    )
    db.add(category)
    await db.flush()
    return category


async def _get_category(
    db: AsyncSession, patient_id: uuid.UUID, category_type: PatientCategoryType
) -> PatientCategory | None:
    result = await db.execute(
        select(PatientCategory).where(
            PatientCategory.patient_id == patient_id,
            PatientCategory.category_type == category_type,
        )
    )
    return result.scalar_one_or_none()


async def list_categories(db: AsyncSession, patient: Patient) -> list[PatientCategory]:
    return list(patient.categories)


# -- Consent ----------------------------------------------------------------


async def add_consent(
    db: AsyncSession, patient: Patient, data: ConsentCreate, actor: StaffUser
) -> ConsentRecord:
    consent = ConsentRecord(
        patient_id=patient.id,
        consent_type=data.consent_type,
        purpose=data.purpose,
        evidence_reference=data.evidence_reference,
        recorded_by=actor.id,
    )
    db.add(consent)
    await db.flush()
    return consent


async def list_consents(db: AsyncSession, patient: Patient) -> list[ConsentRecord]:
    return list(patient.consents)


async def withdraw_consent(
    db: AsyncSession, patient: Patient, consent_id: uuid.UUID, actor: StaffUser
) -> ConsentRecord:
    consent = next((c for c in patient.consents if c.id == consent_id), None)
    if consent is None:
        raise NotFoundError("Consent record not found.")
    if consent.status == ConsentStatus.WITHDRAWN:
        raise ConflictError("This consent has already been withdrawn.")
    consent.status = ConsentStatus.WITHDRAWN
    consent.withdrawn_at = datetime.now(UTC)
    return consent


# -- Observations ------------------------------------------------------------


async def add_observation(
    db: AsyncSession, patient: Patient, data: ObservationCreate, actor: StaffUser
) -> Observation:
    observation = Observation(
        patient_id=patient.id,
        observation_type=data.observation_type,
        value=data.value,
        unit=data.unit,
        observed_at=data.observed_at,
        source=data.source,
        measurement_context=data.measurement_context,
        recorded_by=actor.id,
    )
    db.add(observation)
    await db.flush()
    await rule_engine.evaluate_observation(db, observation)
    return observation


async def list_observations(
    db: AsyncSession, patient: Patient, params: PageParams
) -> tuple[list[Observation], int]:
    result = await db.execute(
        select(Observation)
        .where(Observation.patient_id == patient.id)
        .order_by(Observation.observed_at.desc())
        .offset(params.offset)
        .limit(params.limit)
    )
    total = await db.scalar(
        select(func.count()).select_from(Observation).where(Observation.patient_id == patient.id)
    )
    return list(result.scalars().all()), int(total or 0)


# -- Care plans --------------------------------------------------------------


async def create_care_plan(
    db: AsyncSession, patient: Patient, data: CarePlanCreate, actor: StaffUser
) -> CarePlan:
    max_version = await db.scalar(
        select(func.max(CarePlan.version)).where(CarePlan.patient_id == patient.id)
    )
    version = int(max_version or 0) + 1
    care_plan = CarePlan(
        patient_id=patient.id,
        version=version,
        status=data.status,
        effective_from=data.effective_from,
        effective_to=data.effective_to,
        plan_reference=data.plan_reference,
        content=data.content,
        approved_by=actor.id,
        approval_timestamp=datetime.now(UTC) if data.status == CarePlanStatus.ACTIVE else None,
    )
    if data.status == CarePlanStatus.ACTIVE:
        archived = await db.scalars(
            select(CarePlan).where(
                CarePlan.patient_id == patient.id,
                CarePlan.status == CarePlanStatus.ACTIVE,
            )
        )
        for plan in archived:
            plan.status = CarePlanStatus.ARCHIVED
    db.add(care_plan)
    await db.flush()
    return care_plan


async def list_care_plans(db: AsyncSession, patient: Patient) -> list[CarePlan]:
    result = await db.execute(
        select(CarePlan).where(CarePlan.patient_id == patient.id).order_by(CarePlan.version.desc())
    )
    return list(result.scalars().all())


# -- Timeline ----------------------------------------------------------------

_TIMELINE_LIMIT = 200


async def list_timeline(db: AsyncSession, patient: Patient) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []

    observations = await db.scalars(
        select(Observation)
        .where(Observation.patient_id == patient.id)
        .order_by(Observation.observed_at.desc())
        .limit(_TIMELINE_LIMIT)
    )
    for obs in observations:
        value = f" {obs.value} {obs.unit}".rstrip() if obs.value is not None else ""
        events.append(
            TimelineEvent(
                event_type="observation",
                entity_id=str(obs.id),
                occurred_at=obs.observed_at,
                summary=f"{obs.observation_type.replace('_', ' ').title()}:{value}",
                payload={
                    "observation_type": obs.observation_type,
                    "value": str(obs.value) if obs.value is not None else None,
                    "unit": obs.unit,
                    "source": obs.source.value,
                    "validation_status": obs.validation_status.value,
                },
            )
        )

    care_plans = await db.scalars(
        select(CarePlan)
        .where(CarePlan.patient_id == patient.id)
        .order_by(CarePlan.created_at.desc())
        .limit(_TIMELINE_LIMIT)
    )
    for plan in care_plans:
        events.append(
            TimelineEvent(
                event_type="care_plan",
                entity_id=str(plan.id),
                occurred_at=plan.approval_timestamp or plan.created_at,
                summary=f"Care plan v{plan.version} {plan.status.value}",
                payload={"version": plan.version, "status": plan.status.value},
            )
        )

    categories = await db.scalars(
        select(PatientCategory)
        .where(PatientCategory.patient_id == patient.id)
        .order_by(PatientCategory.created_at.desc())
        .limit(_TIMELINE_LIMIT)
    )
    for category in categories:
        events.append(
            TimelineEvent(
                event_type="category",
                entity_id=str(category.id),
                occurred_at=category.created_at,
                summary=f"Assigned to {category.category_type.value} category",
                payload={"category_type": category.category_type.value},
            )
        )

    consents = await db.scalars(
        select(ConsentRecord)
        .where(ConsentRecord.patient_id == patient.id)
        .order_by(ConsentRecord.captured_at.desc())
        .limit(_TIMELINE_LIMIT)
    )
    for consent in consents:
        consent_type = consent.consent_type.value.replace("_", " ").title()
        events.append(
            TimelineEvent(
                event_type="consent",
                entity_id=str(consent.id),
                occurred_at=consent.captured_at,
                summary=f"{consent_type} consent {consent.status.value}",
                payload={
                    "consent_type": consent.consent_type.value,
                    "status": consent.status.value,
                },
            )
        )

    events.sort(key=lambda event: event.occurred_at, reverse=True)
    return events[:_TIMELINE_LIMIT]


def active_category_types(patient: Patient) -> set[PatientCategoryType]:
    """Distinct category types the patient is currently active in for software gating."""
    return {c.category_type for c in patient.categories if c.effective_to is None}


def has_active_consent(
    patient: Patient, consent_type: ConsentType = ConsentType.COMMUNICATION
) -> bool:
    return any(
        c.consent_type == consent_type and c.status == ConsentStatus.ACTIVE
        for c in patient.consents
    )
