"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.pagination import PageParams, page_params
from app.core.security import TokenError, decode_token
from app.db.session import get_db
from app.models.user import StaffRole, StaffUser
from app.services import users as users_service

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StaffUser:
    """Resolve the authenticated staff user from the bearer access token."""
    if credentials is None:
        raise AuthenticationError("Missing bearer token.")
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc

    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Token subject is invalid.") from exc

    user = await users_service.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("The account is unavailable.")
    return user


CurrentUser = Annotated[StaffUser, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
Pagination = Annotated[PageParams, Depends(page_params)]


def require_roles(*roles: StaffRole) -> Callable[[StaffUser], Awaitable[StaffUser]]:
    """Build a dependency that permits only the given roles."""
    allowed = set(roles)

    async def _dependency(user: CurrentUser) -> StaffUser:
        if user.role not in allowed:
            raise PermissionDeniedError()
        return user

    return _dependency


def client_context(request: Request) -> dict[str, str | None]:
    """Extract client metadata for audit and token records."""
    forwarded = request.headers.get("x-forwarded-for")
    ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else None)
    )
    return {"user_agent": request.headers.get("user-agent"), "ip_address": ip}
