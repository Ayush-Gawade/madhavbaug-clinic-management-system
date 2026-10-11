"""Authentication services: login, token issuance, refresh rotation, logout."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AuthenticationError
from app.core.security import (
    TokenError,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import RefreshToken, StaffUser
from app.schemas.auth import TokenPair
from app.services import users as users_service

# A pre-computed hash used to equalise timing when the email is unknown,
# reducing user-enumeration signal.
_DUMMY_HASH = hash_password("timing-equalisation-placeholder")


async def authenticate(db: AsyncSession, email: str, password: str) -> StaffUser:
    """Validate credentials and return the active staff user."""
    user = await users_service.get_by_email(db, email)
    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise AuthenticationError("Invalid email or password.")
    if not verify_password(password, user.hashed_password):
        raise AuthenticationError("Invalid email or password.")
    if not user.is_active:
        raise AuthenticationError("This account is inactive.")
    return user


def _new_refresh_row(
    user_id: uuid.UUID,
    *,
    user_agent: str | None,
    ip_address: str | None,
) -> tuple[str, RefreshToken]:
    token = create_token(str(user_id), token_type="refresh")
    payload = decode_token(token, expected_type="refresh")
    row = RefreshToken(
        user_id=user_id,
        jti=uuid.UUID(str(payload["jti"])),
        expires_at=datetime.fromtimestamp(float(payload["exp"]), tz=UTC),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    return token, row


async def issue_token_pair(
    db: AsyncSession,
    user: StaffUser,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenPair:
    """Issue a fresh access/refresh pair and persist the refresh token."""
    access_token = create_token(
        str(user.id),
        token_type="access",
        extra_claims={"role": user.role.value},
    )
    refresh_token, row = _new_refresh_row(user.id, user_agent=user_agent, ip_address=ip_address)
    db.add(row)
    user.last_login_at = datetime.now(UTC)
    await db.flush()
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


async def rotate_refresh_token(
    db: AsyncSession,
    refresh_token: str,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenPair:
    """Rotate a refresh token, revoking the old one and linking the replacement."""
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc

    jti = uuid.UUID(str(payload["jti"]))
    row = await db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
    if row is None or row.revoked_at is not None:
        raise AuthenticationError("Refresh token is invalid or has been revoked.")
    if row.expires_at <= datetime.now(UTC):
        raise AuthenticationError("Refresh token has expired.")

    user = await users_service.get_by_id(db, row.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("This account is unavailable.")

    access_token = create_token(
        str(user.id),
        token_type="access",
        extra_claims={"role": user.role.value},
    )
    new_refresh_token, new_row = _new_refresh_row(
        user.id, user_agent=user_agent, ip_address=ip_address
    )
    db.add(new_row)

    row.revoked_at = datetime.now(UTC)
    row.replaced_by_jti = new_row.jti
    await db.flush()

    return TokenPair(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


async def revoke_refresh_token(db: AsyncSession, refresh_token: str) -> None:
    """Revoke a refresh token (logout). Silently ignores unknown tokens."""
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except TokenError:
        return
    jti = uuid.UUID(str(payload["jti"]))
    row = await db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await db.flush()
