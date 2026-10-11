"""Patient and clinical workflow endpoints.

Patient and clinical records are accessible to owner, reception and clinical
staff (doctor, dietitian). Finance staff never see clinical detail endpoints.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, Pagination, require_roles
from app.core.pagination import Page
from app.models.clinical import PatientCategoryType, PatientStatus
from app.models.user import StaffRole, StaffUser
from app.schemas.patient import (
    CarePlanCreate,
    CarePlanRead,
    CategoryAssign,
    ConsentCreate,
    ConsentRead,
    ObservationCreate,
    ObservationRead,
    PatientCategoryRead,
    PatientCreate,
    PatientRead,
    PatientUpdate,
    TimelineEvent,
)
from app.services import audit as audit_service
from app.services import patients as patients_service

router = APIRouter(prefix="/patients", tags=["patients"])

ClinicalStaff = Annotated[
    StaffUser,
    Depends(
        require_roles(
            StaffRole.OWNER,
            StaffRole.DOCTOR,
            StaffRole.DIETITIAN,
            StaffRole.RECEPTION,
        )
    ),
]


async def _audit(
    db: AsyncSession,
    actor: StaffUser,
    action: str,
    patient_id: uuid.UUID,
    details: dict[str, Any] | None = None,
) -> None:
    await audit_service.record_event(
        db,
        action=action,
        entity_type="patient",
        entity_id=patient_id,
        actor_id=actor.id,
        change_summary=details,
    )


@router.post(
    "",
    response_model=PatientRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new patient",
)
async def create_patient(
    payload: PatientCreate, db: DbSession, actor: ClinicalStaff
) -> PatientRead:
    patient = await patients_service.create_patient(db, payload)
    await _audit(db, actor, "patient.create", patient.id, {"internal_id": patient.internal_id})
    await db.flush()
    return PatientRead.model_validate(patient)


@router.get("", response_model=Page[PatientRead], summary="List / search patients")
async def list_patients(
    db: DbSession,
    actor: ClinicalStaff,
    params: Pagination,
    search: Annotated[str | None, Query(max_length=255)] = None,
    category: Annotated[
        PatientCategoryType | None, Query(description="Filter by category type")
    ] = None,
    status_filter: Annotated[
        PatientStatus | None, Query(alias="status", description="Filter by patient status")
    ] = None,
    assigned_clinician_id: uuid.UUID | None = None,
) -> Page[PatientRead]:
    patients, total = await patients_service.list_patients(
        db,
        params,
        search=search,
        category=category,
        status=status_filter,
        assigned_clinician_id=assigned_clinician_id,
    )
    return Page.create(
        [PatientRead.model_validate(p) for p in patients],
        total=total,
        page=params.page,
        size=params.size,
    )


@router.get("/{patient_id}", response_model=PatientRead, summary="Get a patient")
async def get_patient(patient_id: uuid.UUID, db: DbSession, actor: ClinicalStaff) -> PatientRead:
    patient = await patients_service.require_patient(db, patient_id)
    return PatientRead.model_validate(patient)


@router.patch("/{patient_id}", response_model=PatientRead, summary="Update a patient")
async def update_patient(
    patient_id: uuid.UUID,
    payload: PatientUpdate,
    db: DbSession,
    actor: ClinicalStaff,
) -> PatientRead:
    patient = await patients_service.require_patient(db, patient_id)
    changes = payload.model_dump(exclude_unset=True)
    patient = await patients_service.update_patient(db, patient, payload, actor)
    await _audit(db, actor, "patient.update", patient.id, {k: str(v) for k, v in changes.items()})
    await db.flush()
    await db.refresh(patient)
    return PatientRead.model_validate(patient)


@router.post(
    "/{patient_id}/categories",
    response_model=PatientCategoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a category to a patient",
)
async def assign_category(
    patient_id: uuid.UUID,
    payload: CategoryAssign,
    db: DbSession,
    actor: ClinicalStaff,
) -> PatientCategoryRead:
    patient = await patients_service.require_patient(db, patient_id)
    category = await patients_service.assign_category(db, patient, payload, actor)
    await _audit(
        db,
        actor,
        "patient.category.assign",
        patient.id,
        {"category_type": category.category_type.value},
    )
    await db.flush()
    return PatientCategoryRead.model_validate(category)


@router.get(
    "/{patient_id}/categories",
    response_model=list[PatientCategoryRead],
    summary="List a patient's categories",
)
async def list_categories(
    patient_id: uuid.UUID, db: DbSession, actor: ClinicalStaff
) -> list[PatientCategoryRead]:
    patient = await patients_service.require_patient(db, patient_id)
    return [
        PatientCategoryRead.model_validate(category)
        for category in await patients_service.list_categories(db, patient)
    ]


@router.post(
    "/{patient_id}/consents",
    response_model=ConsentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a patient consent",
)
async def add_consent(
    patient_id: uuid.UUID,
    payload: ConsentCreate,
    db: DbSession,
    actor: ClinicalStaff,
) -> ConsentRead:
    patient = await patients_service.require_patient(db, patient_id)
    consent = await patients_service.add_consent(db, patient, payload, actor)
    await _audit(
        db, actor, "patient.consent.add", patient.id, {"consent_type": consent.consent_type.value}
    )
    await db.flush()
    return ConsentRead.model_validate(consent)


@router.get(
    "/{patient_id}/consents",
    response_model=list[ConsentRead],
    summary="List a patient's consents",
)
async def list_consents(
    patient_id: uuid.UUID, db: DbSession, actor: ClinicalStaff
) -> list[ConsentRead]:
    patient = await patients_service.require_patient(db, patient_id)
    consents = await patients_service.list_consents(db, patient)
    return [ConsentRead.model_validate(c) for c in consents]


@router.post(
    "/{patient_id}/consents/{consent_id}/withdraw",
    response_model=ConsentRead,
    summary="Withdraw a patient consent",
)
async def withdraw_consent(
    patient_id: uuid.UUID,
    consent_id: uuid.UUID,
    db: DbSession,
    actor: ClinicalStaff,
) -> ConsentRead:
    patient = await patients_service.require_patient(db, patient_id)
    consent = await patients_service.withdraw_consent(db, patient, consent_id, actor)
    await _audit(
        db,
        actor,
        "patient.consent.withdraw",
        patient.id,
        {"consent_type": consent.consent_type.value},
    )
    await db.flush()
    return ConsentRead.model_validate(consent)


@router.post(
    "/{patient_id}/observations",
    response_model=ObservationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a patient observation (append-only)",
)
async def add_observation(
    patient_id: uuid.UUID,
    payload: ObservationCreate,
    db: DbSession,
    actor: ClinicalStaff,
) -> ObservationRead:
    patient = await patients_service.require_patient(db, patient_id)
    observation = await patients_service.add_observation(db, patient, payload, actor)
    await _audit(
        db,
        actor,
        "patient.observation.add",
        patient.id,
        {"observation_type": observation.observation_type},
    )
    await db.flush()
    return ObservationRead.model_validate(observation)


@router.get(
    "/{patient_id}/observations",
    response_model=Page[ObservationRead],
    summary="List a patient's observations (newest first)",
)
async def list_observations(
    patient_id: uuid.UUID,
    db: DbSession,
    actor: ClinicalStaff,
    params: Pagination,
) -> Page[ObservationRead]:
    patient = await patients_service.require_patient(db, patient_id)
    observations, total = await patients_service.list_observations(db, patient, params)
    return Page.create(
        [ObservationRead.model_validate(o) for o in observations],
        total=total,
        page=params.page,
        size=params.size,
    )


@router.post(
    "/{patient_id}/care-plans",
    response_model=CarePlanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new versioned care plan",
)
async def create_care_plan(
    patient_id: uuid.UUID,
    payload: CarePlanCreate,
    db: DbSession,
    actor: ClinicalStaff,
) -> CarePlanRead:
    patient = await patients_service.require_patient(db, patient_id)
    care_plan = await patients_service.create_care_plan(db, patient, payload, actor)
    await _audit(
        db,
        actor,
        "patient.care_plan.create",
        patient.id,
        {"version": care_plan.version, "status": care_plan.status.value},
    )
    await db.flush()
    return CarePlanRead.model_validate(care_plan)


@router.get(
    "/{patient_id}/care-plans",
    response_model=list[CarePlanRead],
    summary="List a patient's care plans (newest version first)",
)
async def list_care_plans(
    patient_id: uuid.UUID, db: DbSession, actor: ClinicalStaff
) -> list[CarePlanRead]:
    patient = await patients_service.require_patient(db, patient_id)
    return [
        CarePlanRead.model_validate(plan)
        for plan in await patients_service.list_care_plans(db, patient)
    ]


@router.get(
    "/{patient_id}/timeline",
    response_model=list[TimelineEvent],
    summary="Patient activity timeline (newest first)",
)
async def get_timeline(
    patient_id: uuid.UUID, db: DbSession, actor: ClinicalStaff
) -> list[TimelineEvent]:
    patient = await patients_service.require_patient(db, patient_id)
    return await patients_service.list_timeline(db, patient)
