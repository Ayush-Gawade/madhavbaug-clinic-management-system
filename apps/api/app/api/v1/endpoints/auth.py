"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentUser, DbSession, client_context
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    StaffUserRead,
    TokenPair,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair, summary="Authenticate a staff user")
async def login(
    payload: LoginRequest,
    request: Request,
    db: DbSession,
) -> TokenPair:
    user = await auth_service.authenticate(db, payload.email, payload.password)
    return await auth_service.issue_token_pair(db, user, **client_context(request))


@router.post("/refresh", response_model=TokenPair, summary="Rotate a refresh token")
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: DbSession,
) -> TokenPair:
    return await auth_service.rotate_refresh_token(
        db, payload.refresh_token, **client_context(request)
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a refresh token",
)
async def logout(payload: RefreshRequest, db: DbSession) -> Response:
    await auth_service.revoke_refresh_token(db, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=StaffUserRead, summary="Current staff user")
async def me(user: CurrentUser) -> StaffUserRead:
    return StaffUserRead.model_validate(user)
