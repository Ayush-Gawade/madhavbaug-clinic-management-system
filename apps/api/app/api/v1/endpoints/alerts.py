"""Alert queue, clinician actions and safety-rule management endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, Pagination, require_roles
from app.core.errors import NotFoundError
from app.core.pagination import Page
from app.models.alerts import AlertPriority, AlertStatus
from app.models.user import StaffRole, StaffUser
from app.schemas.alerts import (
    AlertActionRequest,
    AlertAssignRequest,
    AlertDetailRead,
    AlertRead,
    AlertSummary,
    ClinicianActionRead,
    SafetyRuleCreate,
    SafetyRuleRead,
)
from app.services import alerts as alerts_service
from app.services import audit as audit_service
from app.services import rule_engine

router = APIRouter(tags=["alerts"])

ClinicalStaff = Annotated[
    StaffUser,
    Depends(
        require_roles(StaffRole.OWNER, StaffRole.DOCTOR, StaffRole.DIETITIAN, StaffRole.RECEPTION)
    ),
]
RuleManager = Annotated[StaffUser, Depends(require_roles(StaffRole.OWNER, StaffRole.DOCTOR))]


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


# -- Alert queue -------------------------------------------------------------


@router.get("/alerts/summary", response_model=AlertSummary)
async def get_alert_summary(
    db: DbSession,
    actor: ClinicalStaff,
    patient_id: uuid.UUID | None = None,
) -> AlertSummary:
    return AlertSummary(**await alerts_service.alert_summary(db, patient_id=patient_id))


@router.get("/alerts", response_model=Page[AlertRead])
async def list_alerts(
    db: DbSession,
    actor: ClinicalStaff,
    pagination: Pagination,
    status_: Annotated[AlertStatus | None, Query(alias="status")] = None,
    priority: AlertPriority | None = None,
    patient_id: uuid.UUID | None = None,
    assigned_to: uuid.UUID | None = None,
) -> Page[AlertRead]:
    alerts, total = await alerts_service.list_alerts(
        db,
        status=status_,
        priority=priority,
        patient_id=patient_id,
        assigned_to=assigned_to,
        pagination=pagination,
    )
    return Page[AlertRead].create(
        [AlertRead.model_validate(a) for a in alerts],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.get("/alerts/{alert_id}", response_model=AlertDetailRead)
async def get_alert(alert_id: uuid.UUID, db: DbSession, actor: ClinicalStaff) -> AlertDetailRead:
    alert = await alerts_service.require_alert(db, alert_id)
    actions = await alerts_service.list_actions(db, alert.id)
    detail = AlertDetailRead.model_validate(alert)
    detail.actions = [ClinicianActionRead.model_validate(a) for a in actions]
    return detail


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertRead)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    payload: AlertActionRequest,
    db: DbSession,
    actor: ClinicalStaff,
) -> AlertRead:
    alert = await alerts_service.require_alert(db, alert_id)
    alert = await alerts_service.acknowledge(db, alert, actor=actor, notes=payload.notes)
    await _audit(db, actor, "alert.acknowledged", "alert", alert.id)
    return AlertRead.model_validate(alert)


@router.post("/alerts/{alert_id}/assign", response_model=AlertRead)
async def assign_alert(
    alert_id: uuid.UUID,
    payload: AlertAssignRequest,
    db: DbSession,
    actor: ClinicalStaff,
) -> AlertRead:
    alert = await alerts_service.require_alert(db, alert_id)
    alert = await alerts_service.assign(
        db, alert, actor=actor, assignee_id=payload.assignee_id, notes=payload.notes
    )
    await _audit(
        db, actor, "alert.assigned", "alert", alert.id, {"assignee_id": str(payload.assignee_id)}
    )
    return AlertRead.model_validate(alert)


@router.post("/alerts/{alert_id}/escalate", response_model=AlertRead)
async def escalate_alert(
    alert_id: uuid.UUID,
    payload: AlertActionRequest,
    db: DbSession,
    actor: ClinicalStaff,
) -> AlertRead:
    alert = await alerts_service.require_alert(db, alert_id)
    alert = await alerts_service.escalate(db, alert, actor=actor, notes=payload.notes)
    await _audit(db, actor, "alert.escalated", "alert", alert.id)
    return AlertRead.model_validate(alert)


@router.post("/alerts/{alert_id}/resolve", response_model=AlertRead)
async def resolve_alert(
    alert_id: uuid.UUID,
    payload: AlertActionRequest,
    db: DbSession,
    actor: ClinicalStaff,
) -> AlertRead:
    alert = await alerts_service.require_alert(db, alert_id)
    alert = await alerts_service.resolve(db, alert, actor=actor, notes=payload.notes)
    await _audit(db, actor, "alert.resolved", "alert", alert.id)
    return AlertRead.model_validate(alert)


@router.post("/alerts/{alert_id}/dismiss", response_model=AlertRead)
async def dismiss_alert(
    alert_id: uuid.UUID,
    payload: AlertActionRequest,
    db: DbSession,
    actor: ClinicalStaff,
) -> AlertRead:
    alert = await alerts_service.require_alert(db, alert_id)
    alert = await alerts_service.dismiss(db, alert, actor=actor, notes=payload.notes)
    await _audit(db, actor, "alert.dismissed", "alert", alert.id)
    return AlertRead.model_validate(alert)


# -- Safety rules ------------------------------------------------------------


@router.get("/safety-rules", response_model=list[SafetyRuleRead])
async def list_safety_rules(
    db: DbSession,
    actor: ClinicalStaff,
    active_only: bool = True,
) -> list[SafetyRuleRead]:
    rules = await rule_engine.list_rules(db, active_only=active_only)
    return [SafetyRuleRead.model_validate(rule) for rule in rules]


@router.post("/safety-rules", response_model=SafetyRuleRead, status_code=status.HTTP_201_CREATED)
async def create_safety_rule(
    payload: SafetyRuleCreate, db: DbSession, actor: RuleManager
) -> SafetyRuleRead:
    rule = await rule_engine.create_rule(
        db,
        rule_key=payload.rule_key,
        metric=payload.metric,
        comparator=payload.comparator,
        threshold=payload.threshold,
        unit=payload.unit,
        priority=payload.priority,
        description=payload.description,
        context=payload.context,
        actor_id=actor.id,
    )
    await _audit(
        db,
        actor,
        "safety_rule.published",
        "safety_rule",
        rule.id,
        {"rule_key": rule.rule_key, "version": rule.version, "metric": rule.metric.value},
    )
    return SafetyRuleRead.model_validate(rule)


@router.post("/safety-rules/{rule_id}/deactivate", response_model=SafetyRuleRead)
async def deactivate_safety_rule(
    rule_id: uuid.UUID, db: DbSession, actor: RuleManager
) -> SafetyRuleRead:
    rule = await rule_engine.deactivate_rule(db, rule_id)
    if rule is None:
        raise NotFoundError("Safety rule not found.")
    await _audit(db, actor, "safety_rule.deactivated", "safety_rule", rule.id)
    return SafetyRuleRead.model_validate(rule)
