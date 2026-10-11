"""Staff user management services."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.core.security import hash_password
from app.models.user import StaffUser
from app.schemas.auth import StaffUserCreate, StaffUserUpdate


async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> StaffUser | None:
    return await db.get(StaffUser, user_id)


async def get_by_email(db: AsyncSession, email: str) -> StaffUser | None:
    result = await db.execute(select(StaffUser).where(StaffUser.email == email.lower()))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, data: StaffUserCreate) -> StaffUser:
    email = data.email.lower()
    if await get_by_email(db, email) is not None:
        raise ConflictError("A staff account with this email already exists.")

    user = StaffUser(
        email=email,
        full_name=data.full_name,
        role=data.role,
        is_active=data.is_active,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    await db.flush()
    return user


async def update_user(db: AsyncSession, user: StaffUser, data: StaffUserUpdate) -> StaffUser:
    changes = data.model_dump(exclude_unset=True)
    if "password" in changes:
        password = changes.pop("password")
        if password is not None:
            user.hashed_password = hash_password(password)
    if "email" in changes:  # email is immutable in this update schema
        changes.pop("email")
    for field, value in changes.items():
        setattr(user, field, value)
    await db.flush()
    return user


async def list_users(db: AsyncSession, params: PageParams) -> tuple[list[StaffUser], int]:
    total = await db.scalar(select(func.count()).select_from(StaffUser))
    result = await db.execute(
        select(StaffUser)
        .order_by(StaffUser.created_at.desc())
        .offset(params.offset)
        .limit(params.limit)
    )
    return list(result.scalars().all()), int(total or 0)


async def require_user(db: AsyncSession, user_id: uuid.UUID) -> StaffUser:
    user = await get_by_id(db, user_id)
    if user is None:
        raise NotFoundError("Staff account not found.")
    return user
