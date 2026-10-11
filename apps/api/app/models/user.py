"""Staff identity, roles and refresh-token models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StaffRole(enum.StrEnum):
    """Operational roles defined in PRD section 3."""

    OWNER = "owner"  # Clinic owner / administrator
    DOCTOR = "doctor"  # Practitioner
    DIETITIAN = "dietitian"  # Nutritionist
    RECEPTION = "reception"  # Patient coordinator
    FINANCE = "finance"  # Finance / clinic operations


class StaffUser(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An authenticated clinic staff member."""

    __tablename__ = "staff_users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[StaffRole] = mapped_column(
        Enum(
            StaffRole,
            name="staff_role",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<StaffUser {self.email} role={self.role.value}>"


class RefreshToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A persisted refresh token enabling rotation and revocation.

    Only the token ``jti`` is stored; the signed token itself is never kept.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_active", "user_id", "revoked_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("staff_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    jti: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_jti: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped[StaffUser] = relationship(back_populates="refresh_tokens")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<RefreshToken user={self.user_id} jti={self.jti}>"
