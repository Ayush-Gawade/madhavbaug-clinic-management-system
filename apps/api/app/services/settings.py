"""Database-backed clinic settings.

A curated registry of runtime-tunable product switches. The registry is the
source of truth for the *shape* of each setting — type, default and human
description — so the Settings screen can render what it may write and an
unknown or wrongly-typed key can never be persisted.

Infrastructure concerns stay in the environment (``AI_ENABLED``,
``WHATSAPP_ENABLED``, ``OPENAI_API_KEY`` …). Nothing here can widen a blast
radius: the values are product behaviour, not credentials or access control.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationError
from app.models.settings import AppSetting

SETTING_AI_AUTOREPLY_ENABLED = "ai_autoreply_enabled"
SETTING_AI_AUTOREPLY_DOCTOR_PHONE = "ai_autoreply_doctor_phone"
SETTING_AI_AUTOREPLY_DOCTOR_TEMPLATE = "ai_autoreply_doctor_template"

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
#: Meta's own rule for template names: lowercase, digits, underscores.
_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]{1,64}$")


@dataclass(frozen=True)
class SettingSpec:
    """What a setting is, before any row exists."""

    key: str
    default: Any
    description: str
    value_type: type
    normalize: Callable[[Any], Any]
    validate: Callable[[Any], None]


def _require_bool(value: Any) -> None:
    if not isinstance(value, bool):
        raise ValidationError("Expected true or false.")


def _passthrough(value: Any) -> Any:
    """Hand the raw value straight to its validator (no truthiness coercion)."""
    return value


def _require_str(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("Expected a non-empty string.")


def _normalise_phone(value: str) -> str:
    return re.sub(r"[\s\-().]", "", value)


def _validate_e164(value: str) -> None:
    if not _E164_RE.match(value):
        raise ValidationError("Phone number must be in international format, e.g. +919359883349.")


def _normalise_template_name(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _validate_template_name(value: Any) -> None:
    """An empty name is a real answer: the template is simply not configured yet."""
    if value == "":
        return
    if not isinstance(value, str) or not _TEMPLATE_NAME_RE.match(value):
        raise ValidationError(
            "Template name must be lowercase letters, digits and underscores only, "
            "e.g. urgent_reading_alert."
        )


REGISTRY: dict[str, SettingSpec] = {
    spec.key: spec
    for spec in (
        SettingSpec(
            key=SETTING_AI_AUTOREPLY_ENABLED,
            default=False,
            description=(
                "Let the assistant reply to patient WhatsApp messages automatically. "
                "Requires AI extraction to be enabled."
            ),
            value_type=bool,
            normalize=_passthrough,
            validate=_require_bool,
        ),
        SettingSpec(
            key=SETTING_AI_AUTOREPLY_DOCTOR_PHONE,
            default="+919359883349",
            description="Doctor's WhatsApp number notified when a critical reading arrives.",
            value_type=str,
            normalize=_normalise_phone,
            validate=_validate_e164,
        ),
        SettingSpec(
            key=SETTING_AI_AUTOREPLY_DOCTOR_TEMPLATE,
            default="",
            description=(
                "Name of the approved WhatsApp template used to page the doctor, e.g. "
                "urgent_reading_alert. Must be created in Meta Business Manager first. "
                "Leave empty to send free-form text, which Meta only accepts within 24 "
                "hours of the doctor's last message to the clinic."
            ),
            value_type=str,
            normalize=_normalise_template_name,
            validate=_validate_template_name,
        ),
    )
}


def describe_settings() -> list[dict[str, Any]]:
    """Machine-readable catalogue of every setting, for the Settings screen."""
    return [
        {
            "key": spec.key,
            "default": spec.default,
            "description": spec.description,
            "type": "boolean" if spec.value_type is bool else "string",
        }
        for spec in REGISTRY.values()
    ]


def _spec(key: str) -> SettingSpec:
    spec = REGISTRY.get(key)
    if spec is None:
        raise ValidationError(f"Unknown setting: {key}.")
    return spec


def _normalised(key: str, value: Any) -> Any:
    spec = _spec(key)
    try:
        candidate = spec.normalize(value)
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid value for {key}.") from None
    spec.validate(candidate)
    return candidate


async def _stored(db: AsyncSession) -> dict[str, AppSetting]:
    rows = (await db.execute(select(AppSetting))).scalars().all()
    return {row.key: row for row in rows}


async def get_settings(db: AsyncSession) -> dict[str, Any]:
    """Every registered key with its stored value, falling back to the default."""
    stored = await _stored(db)
    return {
        key: stored[key].value if key in stored else spec.default for key, spec in REGISTRY.items()
    }


async def list_settings(db: AsyncSession) -> list[dict[str, Any]]:
    """The Settings screen payload: value, default, description and provenance."""
    stored = await _stored(db)
    view: list[dict[str, Any]] = []
    for key, spec in REGISTRY.items():
        row = stored.get(key)
        view.append(
            {
                "key": key,
                "value": spec.default if row is None else row.value,
                "default": spec.default,
                "description": spec.description,
                "type": "boolean" if spec.value_type is bool else "string",
                "updated_by": None if row is None else row.updated_by,
                "updated_at": None if row is None else row.updated_at,
            }
        )
    return view


async def get_setting(db: AsyncSession, key: str) -> Any:
    spec = _spec(key)
    value = await db.scalar(select(AppSetting.value).where(AppSetting.key == key))
    return spec.default if value is None else value


async def set_setting(
    db: AsyncSession,
    key: str,
    value: Any,
    *,
    actor_id: uuid.UUID | None = None,
) -> Any:
    """Validate and upsert one setting. Caller owns the transaction."""
    spec = _spec(key)
    stored_value = _normalised(key, value)

    row = await db.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
    if row is None:
        db.add(
            AppSetting(
                key=key,
                value=stored_value,
                description=spec.description,
                updated_by=actor_id,
            )
        )
    else:
        row.value = stored_value
        row.updated_by = actor_id
    await db.flush()
    return stored_value


# -- Auto-reply helpers -------------------------------------------------------


async def is_auto_reply_enabled(db: AsyncSession) -> bool:
    """Whether the auto-reply feature may run for an inbound message."""
    return bool(await get_setting(db, SETTING_AI_AUTOREPLY_ENABLED))


async def auto_reply_doctor_phone(db: AsyncSession) -> str:
    return str(await get_setting(db, SETTING_AI_AUTOREPLY_DOCTOR_PHONE))


async def auto_reply_doctor_template(db: AsyncSession) -> str:
    """Configured template name for the doctor page; empty when unset."""
    return str(await get_setting(db, SETTING_AI_AUTOREPLY_DOCTOR_TEMPLATE)).strip()
