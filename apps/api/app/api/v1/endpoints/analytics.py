"""Analytics endpoints: overview, operations, adherence, trends, finances (FR-028..FR-043)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, require_roles
from app.api.v1.endpoints.patients import ClinicalStaff
from app.core.config import settings
from app.models.user import StaffRole, StaffUser
from app.schemas.analytics import (
    AdherenceSummary,
    ClinicOverview,
    DailyOperations,
    FinanceOverview,
    ObservationTrend,
)
from app.services import analytics as analytics_service
from app.services import patients as patients_service

router = APIRouter(tags=["analytics"], prefix="/analytics")

# Finance analytics are restricted to owner + finance (clinical staff excluded).
FinanceViewer = Annotated[
    StaffUser,
    Depends(require_roles(StaffRole.OWNER, StaffRole.FINANCE)),
]

_DEFAULT_TREND_DAYS = {"day": 90, "week": 180, "month": 365}


def _today() -> date:
    return datetime.now(ZoneInfo(settings.app_timezone)).date()


@router.get("/overview", response_model=ClinicOverview, summary="Clinic-wide overview counts")
async def clinic_overview(db: DbSession, actor: ClinicalStaff) -> ClinicOverview:
    return await analytics_service.clinic_overview(db)


@router.get(
    "/operations",
    response_model=DailyOperations,
    summary="Patients requiring action today (overdue follow-ups + open alerts)",
)
async def daily_operations(db: DbSession, actor: ClinicalStaff) -> DailyOperations:
    return await analytics_service.daily_operations(db)


@router.get(
    "/adherence",
    response_model=AdherenceSummary,
    summary="Follow-up adherence summary for a date range",
)
async def adherence(
    db: DbSession,
    actor: ClinicalStaff,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    patient_id: Annotated[uuid.UUID | None, Query()] = None,
) -> AdherenceSummary:
    resolved_to = date_to or _today()
    resolved_from = date_from or (resolved_to - timedelta(days=30))
    return await analytics_service.adherence_summary(
        db, date_from=resolved_from, date_to=resolved_to, patient_id=patient_id
    )


@router.get(
    "/patients/{patient_id}/trends",
    response_model=ObservationTrend,
    summary="Curated observation trend series for a patient",
)
async def observation_trends(
    patient_id: uuid.UUID,
    db: DbSession,
    actor: ClinicalStaff,
    observation_type: Annotated[str, Query(min_length=1)],
    granularity: Annotated[str, Query(pattern="^(day|week|month)$")] = "day",
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> ObservationTrend:
    patient = await patients_service.require_patient(db, patient_id)
    resolved_to = date_to or _today()
    resolved_from = date_from or (resolved_to - timedelta(days=_DEFAULT_TREND_DAYS[granularity]))
    return await analytics_service.observation_trends(
        db,
        patient_id=patient.id,
        observation_type=observation_type,
        granularity=granularity,
        date_from=resolved_from,
        date_to=resolved_to,
    )


@router.get(
    "/finance",
    response_model=FinanceOverview,
    summary="Clinic-wide financial overview (recorded vs estimated)",
)
async def finance_overview(db: DbSession, actor: FinanceViewer) -> FinanceOverview:
    return await analytics_service.finance_overview(db)
