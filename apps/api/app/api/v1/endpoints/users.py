"""Staff user administration endpoints (owner only)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DbSession, Pagination, require_roles
from app.core.pagination import Page
from app.models.user import StaffRole, StaffUser
from app.schemas.auth import StaffUserCreate, StaffUserRead, StaffUserUpdate
from app.services import audit as audit_service
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])

# Every endpoint here requires the owner/administrator role.
OwnerUser = Annotated[StaffUser, Depends(require_roles(StaffRole.OWNER))]


@router.post(
    "",
    response_model=StaffUserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a staff account",
)
async def create_user(
    payload: StaffUserCreate,
    db: DbSession,
    actor: OwnerUser,
) -> StaffUserRead:
    user = await users_service.create_user(db, payload)
    await audit_service.record_event(
        db,
        action="staff_user.create",
        entity_type="staff_user",
        entity_id=user.id,
        actor_id=actor.id,
        change_summary={"email": user.email, "role": user.role.value},
    )
    await db.flush()
    return StaffUserRead.model_validate(user)


@router.get("", response_model=Page[StaffUserRead], summary="List staff accounts")
async def list_users(db: DbSession, actor: OwnerUser, params: Pagination) -> Page[StaffUserRead]:
    users, total = await users_service.list_users(db, params)
    return Page.create(
        [StaffUserRead.model_validate(user) for user in users],
        total=total,
        page=params.page,
        size=params.size,
    )


@router.get("/{user_id}", response_model=StaffUserRead, summary="Get a staff account")
async def get_user(user_id: uuid.UUID, db: DbSession, actor: OwnerUser) -> StaffUserRead:
    user = await users_service.require_user(db, user_id)
    return StaffUserRead.model_validate(user)


@router.patch("/{user_id}", response_model=StaffUserRead, summary="Update a staff account")
async def update_user(
    user_id: uuid.UUID,
    payload: StaffUserUpdate,
    db: DbSession,
    actor: OwnerUser,
) -> StaffUserRead:
    user = await users_service.require_user(db, user_id)
    changes = payload.model_dump(exclude_unset=True, exclude={"password"})
    if "password" in payload.model_fields_set:
        changes["password"] = "***"
    await users_service.update_user(db, user, payload)
    await audit_service.record_event(
        db,
        action="staff_user.update",
        entity_type="staff_user",
        entity_id=user.id,
        actor_id=actor.id,
        change_summary={key: str(value) for key, value in changes.items()},
    )
    await db.flush()
    return StaffUserRead.model_validate(user)
