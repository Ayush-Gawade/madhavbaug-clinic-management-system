"""AI extraction review endpoints (provenance, clarifications, manual re-run)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, Pagination, require_roles
from app.core.errors import NotFoundError
from app.core.pagination import Page
from app.models.user import StaffRole, StaffUser
from app.schemas.ai import AIExtractionRead
from app.services import ai as ai_service
from app.services import audit as audit_service

router = APIRouter(tags=["ai"])

ClinicalStaff = Annotated[
    StaffUser,
    Depends(
        require_roles(StaffRole.OWNER, StaffRole.DOCTOR, StaffRole.DIETITIAN, StaffRole.RECEPTION)
    ),
]


@router.get("/patients/{patient_id}/ai-extractions", response_model=Page[AIExtractionRead])
async def list_patient_extractions(
    patient_id: uuid.UUID, db: DbSession, actor: ClinicalStaff, pagination: Pagination
) -> Page[AIExtractionRead]:
    extractions, total = await ai_service.list_extractions(db, patient_id, pagination)
    return Page[AIExtractionRead].create(
        [AIExtractionRead.model_validate(item) for item in extractions],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.get("/ai-extractions/{extraction_id}", response_model=AIExtractionRead)
async def get_ai_extraction(
    extraction_id: uuid.UUID, db: DbSession, actor: ClinicalStaff
) -> AIExtractionRead:
    extraction = await ai_service.get_extraction(db, extraction_id)
    if extraction is None:
        raise NotFoundError("AI extraction not found.")
    return AIExtractionRead.model_validate(extraction)


@router.post("/messages/{message_id}/analyze", response_model=AIExtractionRead)
async def analyze_message(
    message_id: uuid.UUID,
    db: DbSession,
    actor: Annotated[
        StaffUser, Depends(require_roles(StaffRole.OWNER, StaffRole.DOCTOR, StaffRole.DIETITIAN))
    ],
) -> AIExtractionRead:
    extraction = await ai_service.reanalyze(db, message_id)
    if extraction is None:
        raise NotFoundError("Message not found or is not linked to a patient.")
    await _audit(
        db, actor, "ai.analyzed", "ai_extraction", extraction.id, {"message_id": str(message_id)}
    )
    return AIExtractionRead.model_validate(extraction)


async def _audit(
    db: AsyncSession,
    actor: StaffUser,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    details: dict[str, Any] | None = None,
) -> None:
    await audit_service.record_event(
        db,
        actor_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        change_summary=details,
    )
