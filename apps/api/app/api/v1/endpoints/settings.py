"""Runtime settings: read and flip clinic-tunable switches."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbSession, require_roles
from app.core.errors import NotFoundError
from app.models.user import StaffRole, StaffUser
from app.schemas.settings import SettingRead, SettingsRead, SettingUpdate
from app.services import audit as audit_service
from app.services import settings as settings_service

router = APIRouter(tags=["settings"])

#: Writing is limited to the roles that already own safety rules — a toggle is
#: as consequential as a threshold.
SettingManager = Annotated[StaffUser, Depends(require_roles(StaffRole.OWNER, StaffRole.DOCTOR))]


@router.get("/settings", response_model=SettingsRead)
async def list_settings(db: DbSession, actor: CurrentUser) -> SettingsRead:
    """Every registered setting with its stored value (falls back to default)."""
    rows = await settings_service.list_settings(db)
    return SettingsRead(settings=[SettingRead(**row) for row in rows])


@router.put("/settings/{key}", response_model=SettingRead)
async def update_setting(
    key: str,
    payload: SettingUpdate,
    db: DbSession,
    actor: SettingManager,
) -> SettingRead:
    await settings_service.set_setting(db, key, payload.value, actor_id=actor.id)
    await audit_service.record_event(
        db,
        actor_id=actor.id,
        action="setting.updated",
        entity_type="app_setting",
        entity_id=key,
        change_summary={"key": key, "value": payload.value},
    )
    for row in await settings_service.list_settings(db):
        if row["key"] == key:
            return SettingRead(**row)
    raise NotFoundError("Setting not found.")
