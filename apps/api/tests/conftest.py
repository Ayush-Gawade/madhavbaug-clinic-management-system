"""Shared pytest fixtures.

Integration fixtures provision a dedicated test database (``TEST_DATABASE_URL``)
and skip gracefully when it is unavailable, so pure unit tests always run.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# Import models so metadata is fully populated before create_all.
import app.models  # noqa: F401  (imported for side effects)
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.user import StaffRole
from app.schemas.auth import StaffUserCreate
from app.services import users as users_service


def _test_database_url() -> str:
    return settings.test_database_url or settings.sqlalchemy_database_uri


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    """Create a fresh schema on the test database (skips if unreachable)."""
    test_engine = create_async_engine(_test_database_url(), poolclass=NullPool)
    try:
        async with test_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
    except Exception as exc:  # pragma: no cover - depends on infra availability
        await test_engine.dispose()
        pytest.skip(f"test database unavailable: {type(exc).__name__}: {exc}")
    try:
        yield test_engine
    finally:
        await test_engine.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    """An HTTP client bound to the app with an overridden database session."""

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
    app.dependency_overrides.clear()


@pytest.fixture
def unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


@pytest.fixture(autouse=True)
def _allow_unsigned_webhooks_in_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests post unsigned webhooks in dry-run; production forbids this."""
    monkeypatch.setattr(settings, "webhook_allow_unsigned", True)


async def create_staff(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    email: str,
    role: StaffRole = StaffRole.OWNER,
    password: str = "strong-password-123",
) -> uuid.UUID:
    """Helper to persist an active staff account and return its id."""
    async with session_factory() as session:
        user = await users_service.create_user(
            session,
            StaffUserCreate(email=email, full_name="Test User", role=role, password=password),
        )
        await session.commit()
        return user.id


@pytest.fixture
def staff_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[..., Awaitable[uuid.UUID]]:
    """Returns an async callable creating a staff account."""

    async def _factory(
        *,
        email: str,
        role: StaffRole = StaffRole.OWNER,
        password: str = "strong-password-123",
    ) -> uuid.UUID:
        return await create_staff(session_factory, email=email, role=role, password=password)

    return _factory
