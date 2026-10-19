"""Pydantic schemas for the runtime settings screen."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SettingRead(BaseModel):
    """One setting as shown on the Settings screen."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    value: Any
    default: Any
    description: str
    type: Literal["boolean", "string"]
    updated_by: uuid.UUID | None = None
    updated_at: datetime | None = None


class SettingUpdate(BaseModel):
    value: Any = Field(..., description="New value; type is validated server-side.")


class SettingsRead(BaseModel):
    settings: list[SettingRead]
