"""Database-backed runtime settings.

Clinic-tunable switches live in the database rather than the environment so a
clinician can flip them from the Settings screen without editing ``.env`` or
restarting the API. Env vars still govern hard infrastructure concerns
(``AI_ENABLED``, ``WHATSAPP_ENABLED`` …); this table only carries *product*
toggles that are safe to change at runtime.

Values are JSONB because a key may hold a boolean, a string or a small object.
``key`` is unique so a setting is a single, idempotently seedable row.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AppSetting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One clinic-tunable key/value pair."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    #: Registry prose, not a label. ``TEXT``: settings descriptions are written
    #: in code and a 255-character ceiling turns documentation into a bug.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AppSetting {self.key}={self.value!r}>"
