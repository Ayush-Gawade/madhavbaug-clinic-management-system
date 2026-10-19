"""Integration tests for the runtime settings screen (PostgreSQL)."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.audit import AuditEvent
from app.models.settings import AppSetting
from app.models.user import StaffRole

pytestmark = pytest.mark.integration

API = "/api/v1"
PASSWORD = "strong-password-123"


@pytest.fixture(autouse=True)
async def _reset_settings(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """The schema is session-scoped and shared; every test starts at defaults."""
    async with session_factory() as session:
        await session.execute(delete(AppSetting))
        await session.commit()


async def _login(client, email: str) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def _headers(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _catalogue(client, headers: dict[str, str]) -> dict[str, dict]:
    response = await client.get(f"{API}/settings", headers=headers)
    assert response.status_code == 200, response.text
    return {item["key"]: item for item in response.json()["settings"]}


async def test_catalogue_returns_registered_keys_with_defaults(client, staff_factory, unique_email):
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))

    settings = await _catalogue(client, headers)

    assert set(settings) == {"ai_autoreply_enabled", "ai_autoreply_doctor_phone"}
    enabled = settings["ai_autoreply_enabled"]
    assert enabled["value"] is False
    assert enabled["default"] is False
    assert enabled["type"] == "boolean"
    assert enabled["updated_at"] is None
    assert settings["ai_autoreply_doctor_phone"]["value"] == "+919359883349"


async def test_owner_can_switch_auto_reply_on(client, staff_factory, unique_email):
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))

    flipped = await client.put(
        f"{API}/settings/ai_autoreply_enabled", headers=headers, json={"value": True}
    )
    assert flipped.status_code == 200, flipped.text
    assert flipped.json()["value"] is True
    assert flipped.json()["updated_at"] is not None

    reloaded = await _catalogue(client, headers)
    assert reloaded["ai_autoreply_enabled"]["value"] is True

    turned_off = await client.put(
        f"{API}/settings/ai_autoreply_enabled", headers=headers, json={"value": False}
    )
    assert turned_off.status_code == 200, turned_off.text
    assert turned_off.json()["value"] is False


async def test_doctor_can_change_settings(client, staff_factory, unique_email):
    await staff_factory(email=unique_email, role=StaffRole.DOCTOR)
    headers = _headers(await _login(client, unique_email))

    response = await client.put(
        f"{API}/settings/ai_autoreply_doctor_phone",
        headers=headers,
        json={"value": "+91 98765 43210"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["value"] == "+919876543210"


async def test_reception_can_read_but_not_write(client, staff_factory, unique_email):
    await staff_factory(email=unique_email, role=StaffRole.RECEPTION)
    headers = _headers(await _login(client, unique_email))

    assert (await client.get(f"{API}/settings", headers=headers)).status_code == 200

    forbidden = await client.put(
        f"{API}/settings/ai_autoreply_enabled", headers=headers, json={"value": True}
    )
    assert forbidden.status_code == 403


async def test_a_string_false_is_not_treated_as_truthy(client, staff_factory, unique_email):
    """``bool("false")`` is True in Python; the API must refuse, not coerce."""
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))

    response = await client.put(
        f"{API}/settings/ai_autoreply_enabled", headers=headers, json={"value": "false"}
    )
    assert response.status_code == 422
    assert (await _catalogue(client, headers))["ai_autoreply_enabled"]["value"] is False


async def test_invalid_doctor_phone_is_rejected(client, staff_factory, unique_email):
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))

    response = await client.put(
        f"{API}/settings/ai_autoreply_doctor_phone",
        headers=headers,
        json={"value": "9359883349"},
    )
    assert response.status_code == 422
    assert "international format" in response.json()["error"]["message"]


async def test_unknown_setting_key_is_rejected(client, staff_factory, unique_email):
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))

    response = await client.put(
        f"{API}/settings/ai_autoreply_mode", headers=headers, json={"value": True}
    )
    assert response.status_code == 422
    assert "Unknown setting" in response.json()["error"]["message"]


async def test_authentication_is_required(client, staff_factory, unique_email):
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))
    await client.put(f"{API}/settings/ai_autoreply_enabled", headers=headers, json={"value": True})

    anonymous = await client.get(f"{API}/settings")
    assert anonymous.status_code == 401


async def test_a_setting_change_is_audited(
    client, staff_factory, unique_email, session_factory: async_sessionmaker[AsyncSession]
):
    user_id = await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))

    response = await client.put(
        f"{API}/settings/ai_autoreply_enabled", headers=headers, json={"value": True}
    )
    assert response.status_code == 200, response.text

    async with session_factory() as session:
        # ``actor_id`` is unique to this test, so the assertion does not depend on
        # audit rows left behind by earlier tests in the shared schema.
        event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "setting.updated",
                AuditEvent.actor_id == user_id,
            )
        )

    assert event is not None
    assert event.actor_id == user_id
    assert event.entity_type == "app_setting"
    assert event.entity_id == "ai_autoreply_enabled"
    assert event.change_summary == {"key": "ai_autoreply_enabled", "value": True}
