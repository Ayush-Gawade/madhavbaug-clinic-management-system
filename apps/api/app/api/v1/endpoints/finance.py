"""Financial endpoints: treatments, estimator, assignments, payments, summaries."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, require_roles
from app.api.v1.endpoints.patients import ClinicalStaff
from app.models.user import StaffRole, StaffUser
from app.schemas.finance import (
    EstimateRequest,
    EstimateResult,
    FinanceSummary,
    PatientTreatmentRead,
    PaymentCreate,
    PaymentRead,
    TreatmentAssign,
    TreatmentCreate,
    TreatmentRead,
    TreatmentUpdate,
)
from app.services import audit as audit_service
from app.services import finance as finance_service
from app.services import patients as patients_service

router = APIRouter(tags=["finance"])

# Authorized to configure pricing/costs and use the estimator (PRD FR-034).
FinanceConfig = Annotated[
    StaffUser,
    Depends(require_roles(StaffRole.OWNER, StaffRole.FINANCE)),
]
# Authorized to touch payments and summaries (reception records intake payments).
FinanceTouchers = Annotated[
    StaffUser,
    Depends(require_roles(StaffRole.OWNER, StaffRole.FINANCE, StaffRole.RECEPTION)),
]
# May read the treatment catalog (pricing transparency for clinical staff).
TreatmentReader = Annotated[
    StaffUser,
    Depends(
        require_roles(
            StaffRole.OWNER,
            StaffRole.FINANCE,
            StaffRole.RECEPTION,
            StaffRole.DOCTOR,
            StaffRole.DIETITIAN,
        )
    ),
]


async def _audit(
    db: AsyncSession,
    actor: StaffUser,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    details: dict[str, object],
) -> None:
    await audit_service.record_event(
        db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor.id,
        change_summary=details,
    )


# -- Treatment catalog --------------------------------------------------------


@router.post(
    "/treatments",
    response_model=TreatmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a treatment or package",
)
async def create_treatment(
    payload: TreatmentCreate, db: DbSession, actor: FinanceConfig
) -> TreatmentRead:
    treatment = await finance_service.create_treatment(db, payload)
    await _audit(
        db, actor, "treatment.create", "treatment", treatment.id, {"code": treatment.treatment_code}
    )
    await db.flush()
    return TreatmentRead.model_validate(treatment)


@router.get("/treatments", response_model=list[TreatmentRead], summary="List treatments")
async def list_treatments(
    db: DbSession,
    actor: TreatmentReader,
    active_only: Annotated[bool, Query()] = True,
) -> list[TreatmentRead]:
    treatments = await finance_service.list_treatments(db, active_only=active_only)
    return [TreatmentRead.model_validate(t) for t in treatments]


@router.get("/treatments/{treatment_id}", response_model=TreatmentRead, summary="Get a treatment")
async def get_treatment(
    treatment_id: uuid.UUID, db: DbSession, actor: TreatmentReader
) -> TreatmentRead:
    treatment = await finance_service.require_treatment(db, treatment_id)
    return TreatmentRead.model_validate(treatment)


@router.patch(
    "/treatments/{treatment_id}",
    response_model=TreatmentRead,
    summary="Update a treatment",
)
async def update_treatment(
    treatment_id: uuid.UUID,
    payload: TreatmentUpdate,
    db: DbSession,
    actor: FinanceConfig,
) -> TreatmentRead:
    treatment = await finance_service.require_treatment(db, treatment_id)
    changes = payload.model_dump(exclude_unset=True)
    treatment = await finance_service.update_treatment(db, treatment, payload)
    await _audit(
        db,
        actor,
        "treatment.update",
        "treatment",
        treatment.id,
        {k: str(v) for k, v in changes.items()},
    )
    await db.flush()
    return TreatmentRead.model_validate(treatment)


# -- Estimator ----------------------------------------------------------------


@router.post("/estimator", response_model=EstimateResult, summary="Estimate a discounted treatment")
async def estimate(payload: EstimateRequest, db: DbSession, actor: FinanceConfig) -> EstimateResult:
    return await finance_service.require_estimate(db, payload)


# -- Patient assignments ------------------------------------------------------


@router.post(
    "/patients/{patient_id}/treatments",
    response_model=PatientTreatmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a treatment to a patient",
)
async def assign_treatment(
    patient_id: uuid.UUID,
    payload: TreatmentAssign,
    db: DbSession,
    actor: ClinicalStaff,
) -> PatientTreatmentRead:
    patient = await patients_service.require_patient(db, patient_id)
    assignment = await finance_service.assign_treatment(db, patient.id, payload, actor)
    await _audit(
        db,
        actor,
        "patient.treatment.assign",
        "patient",
        patient.id,
        {
            "treatment_id": str(assignment.treatment_id),
            "discount_percent": str(assignment.discount_percent),
        },
    )
    await db.flush()
    await db.refresh(assignment, attribute_names=["treatment"])
    return PatientTreatmentRead.model_validate(assignment)


@router.get(
    "/patients/{patient_id}/treatments",
    response_model=list[PatientTreatmentRead],
    summary="List a patient's treatment assignments",
)
async def list_assignments(
    patient_id: uuid.UUID, db: DbSession, actor: ClinicalStaff
) -> list[PatientTreatmentRead]:
    patient = await patients_service.require_patient(db, patient_id)
    assignments = await finance_service.list_assignments(db, patient.id)
    return [PatientTreatmentRead.model_validate(a) for a in assignments]


# -- Payments -----------------------------------------------------------------


@router.post(
    "/patients/{patient_id}/payments",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record an itemized payment",
)
async def record_payment(
    patient_id: uuid.UUID,
    payload: PaymentCreate,
    db: DbSession,
    actor: FinanceTouchers,
) -> PaymentRead:
    patient = await patients_service.require_patient(db, patient_id)
    payment = await finance_service.record_payment(db, patient.id, payload, actor)
    await _audit(
        db,
        actor,
        "patient.payment.record",
        "patient",
        patient.id,
        {"amount": str(payment.amount), "type": payment.payment_type.value},
    )
    await db.flush()
    return PaymentRead.model_validate(payment)


@router.get(
    "/patients/{patient_id}/payments",
    response_model=list[PaymentRead],
    summary="List a patient's payments (newest first)",
)
async def list_payments(
    patient_id: uuid.UUID, db: DbSession, actor: FinanceTouchers
) -> list[PaymentRead]:
    patient = await patients_service.require_patient(db, patient_id)
    payments = await finance_service.list_payments(db, patient.id)
    return [PaymentRead.model_validate(p) for p in payments]


# -- Summary ------------------------------------------------------------------


@router.get(
    "/patients/{patient_id}/finance",
    response_model=FinanceSummary,
    summary="Patient financial summary (charges, payments, balance)",
)
async def finance_summary(
    patient_id: uuid.UUID, db: DbSession, actor: FinanceTouchers
) -> FinanceSummary:
    patient = await patients_service.require_patient(db, patient_id)
    return await finance_service.finance_summary(db, patient.id)
