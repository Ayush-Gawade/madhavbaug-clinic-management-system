"""Follow-up scheduling, operations queue and message template endpoints."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession, Pagination, require_roles
from app.core.pagination import Page
from app.models.scheduling import FollowUpInstanceStatus, ScheduleStatus
from app.models.user import StaffRole, StaffUser
from app.schemas.scheduling import (
    FollowUpDayCount,
    InstanceAcknowledgeRequest,
    InstanceAssignRequest,
    InstanceRead,
    InstanceResolveRequest,
    MaterializeResult,
    NonResponseResult,
    ProcessDueResult,
    ScheduleCreate,
    ScheduleRead,
    ScheduleUpdate,
    TemplateCreate,
    TemplateRead,
    TemplateUpdate,
)
from app.services import audit as audit_service
from app.services import non_response as non_response_service
from app.services import schedules as schedule_service

router = APIRouter(tags=["scheduling"])

ClinicalSchedule = Annotated[
    StaffUser,
    Depends(
        require_roles(StaffRole.OWNER, StaffRole.DOCTOR, StaffRole.DIETITIAN, StaffRole.RECEPTION)
    ),
]
TemplateManager = Annotated[
    StaffUser,
    Depends(require_roles(StaffRole.OWNER, StaffRole.DOCTOR, StaffRole.DIETITIAN)),
]


async def _audit(
    db: AsyncSession,
    actor: StaffUser,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    details: dict[str, Any],
) -> None:
    await audit_service.record_event(
        db,
        actor_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        change_summary=details,
    )


@router.post("/schedules", response_model=ScheduleRead, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    payload: ScheduleCreate, db: DbSession, actor: ClinicalSchedule
) -> ScheduleRead:
    schedule = await schedule_service.create_schedule(db, payload, actor)
    await _audit(
        db,
        actor,
        "schedule.created",
        "follow_up_schedule",
        schedule.id,
        {
            "patient_id": str(schedule.patient_id),
            "follow_up_type": schedule.follow_up_type,
            "recurrence_rule": schedule.recurrence_rule,
        },
    )
    return ScheduleRead.model_validate(schedule)


@router.get("/schedules", response_model=Page[ScheduleRead])
async def list_schedules(
    db: DbSession,
    actor: ClinicalSchedule,
    pagination: Pagination,
    patient_id: uuid.UUID | None = None,
    status_: Annotated[ScheduleStatus | None, Query(alias="status")] = None,
) -> Page[ScheduleRead]:
    schedules, total = await schedule_service.list_schedules(
        db, patient_id=patient_id, status=status_, pagination=pagination
    )
    return Page[ScheduleRead].create(
        [ScheduleRead.model_validate(s) for s in schedules],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.get("/schedules/{schedule_id}", response_model=ScheduleRead)
async def get_schedule(
    schedule_id: uuid.UUID, db: DbSession, actor: ClinicalSchedule
) -> ScheduleRead:
    schedule = await schedule_service.require_schedule(db, schedule_id)
    return ScheduleRead.model_validate(schedule)


@router.patch("/schedules/{schedule_id}", response_model=ScheduleRead)
async def update_schedule(
    schedule_id: uuid.UUID,
    payload: ScheduleUpdate,
    db: DbSession,
    actor: ClinicalSchedule,
) -> ScheduleRead:
    schedule = await schedule_service.update_schedule(db, schedule_id, payload)
    await _audit(
        db,
        actor,
        "schedule.updated",
        "follow_up_schedule",
        schedule.id,
        {"updates": payload.model_dump(exclude_unset=True)},
    )
    return ScheduleRead.model_validate(schedule)


@router.post("/schedules/{schedule_id}/materialize", response_model=MaterializeResult)
async def materialize_schedule(
    schedule_id: uuid.UUID, db: DbSession, actor: ClinicalSchedule
) -> MaterializeResult:
    result = await schedule_service.materialize_instances(
        db, schedule_id=schedule_id, horizon_days=7
    )
    await _audit(
        db,
        actor,
        "schedule.materialized",
        "follow_up_schedule",
        schedule_id,
        {"instances_created": result["instances_created"]},
    )
    return MaterializeResult(**result)


@router.post("/schedules/process-due", response_model=ProcessDueResult)
async def process_due(db: DbSession, actor: ClinicalSchedule) -> ProcessDueResult:
    result = await schedule_service.process_due_instances(db)
    await _audit(
        db,
        actor,
        "follow_up.dispatch_run",
        "system",
        uuid.uuid4(),
        {"eligible_to_send": result["eligible_to_send"]},
    )
    return ProcessDueResult(**result)


@router.post("/schedules/process-non-response", response_model=NonResponseResult)
async def process_non_response(db: DbSession, actor: ClinicalSchedule) -> NonResponseResult:
    result = await non_response_service.process_non_response(db)
    await _audit(
        db,
        actor,
        "follow_up.non_response_run",
        "system",
        uuid.uuid4(),
        {
            "reminders_sent": result["reminders_sent"],
            "marked_overdue": result["marked_overdue"],
        },
    )
    return NonResponseResult(**result)


@router.get("/instances", response_model=Page[InstanceRead])
async def list_instances(
    db: DbSession,
    actor: ClinicalSchedule,
    pagination: Pagination,
    status_: Annotated[FollowUpInstanceStatus | None, Query(alias="status")] = None,
    patient_id: uuid.UUID | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
) -> Page[InstanceRead]:
    instances, total = await schedule_service.list_instances(
        db,
        status=status_,
        patient_id=patient_id,
        due_from=due_from,
        due_to=due_to,
        pagination=pagination,
    )
    return Page[InstanceRead].create(
        [InstanceRead.model_validate(i) for i in instances],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.post("/instances/{instance_id}/acknowledge", response_model=InstanceRead)
async def acknowledge_instance(
    instance_id: uuid.UUID,
    payload: InstanceAcknowledgeRequest,
    db: DbSession,
    actor: ClinicalSchedule,
) -> InstanceRead:
    instance = await schedule_service.acknowledge_instance(db, instance_id, actor=actor)
    await _audit(
        db,
        actor,
        "follow_up.acknowledged",
        "follow_up_instance",
        instance.id,
        {"notes": payload.notes},
    )
    return InstanceRead.model_validate(instance)


@router.post("/instances/{instance_id}/assign", response_model=InstanceRead)
async def assign_instance(
    instance_id: uuid.UUID,
    payload: InstanceAssignRequest,
    db: DbSession,
    actor: ClinicalSchedule,
) -> InstanceRead:
    instance = await schedule_service.assign_instance(db, instance_id, staff_id=payload.staff_id)
    await _audit(
        db,
        actor,
        "follow_up.assigned",
        "follow_up_instance",
        instance.id,
        {"staff_id": str(payload.staff_id), "notes": payload.notes},
    )
    return InstanceRead.model_validate(instance)


@router.post("/instances/{instance_id}/resolve", response_model=InstanceRead)
async def resolve_instance(
    instance_id: uuid.UUID,
    payload: InstanceResolveRequest,
    db: DbSession,
    actor: ClinicalSchedule,
) -> InstanceRead:
    instance = await schedule_service.resolve_instance(db, instance_id, actor=actor)
    await _audit(
        db,
        actor,
        "follow_up.resolved",
        "follow_up_instance",
        instance.id,
        {"notes": payload.notes},
    )
    return InstanceRead.model_validate(instance)


@router.get("/follow-ups/day-count", response_model=FollowUpDayCount)
async def follow_up_day_count(db: DbSession, actor: ClinicalSchedule) -> FollowUpDayCount:
    counts = await schedule_service.day_counts(db)
    return FollowUpDayCount(**counts)


@router.post(
    "/messages/templates", response_model=TemplateRead, status_code=status.HTTP_201_CREATED
)
async def create_template(
    payload: TemplateCreate, db: DbSession, actor: TemplateManager
) -> TemplateRead:
    template = await schedule_service.create_template(db, payload)
    return TemplateRead.model_validate(template)


@router.get("/messages/templates", response_model=list[TemplateRead])
async def list_templates(
    db: DbSession, actor: CurrentUser, active_only: bool = True
) -> list[TemplateRead]:
    templates = await schedule_service.list_templates(db, active_only=active_only)
    return [TemplateRead.model_validate(t) for t in templates]


@router.patch("/messages/templates/{template_id}", response_model=TemplateRead)
async def update_template(
    template_id: uuid.UUID,
    payload: TemplateUpdate,
    db: DbSession,
    actor: TemplateManager,
) -> TemplateRead:
    template = await schedule_service.update_template(db, template_id, payload)
    return TemplateRead.model_validate(template)
