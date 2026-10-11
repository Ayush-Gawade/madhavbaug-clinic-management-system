"""Integration tests for authentication and RBAC (require PostgreSQL)."""

from __future__ import annotations

import pytest

from app.models.user import StaffRole

pytestmark = pytest.mark.integration

API = "/api/v1"
PASSWORD = "strong-password-123"


async def _login(client, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


async def test_login_returns_tokens_and_me(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    tokens = await _login(client, unique_email)

    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    me = await client.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == unique_email
    assert me.json()["role"] == "owner"


async def test_login_rejects_bad_password(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email)
    response = await client.post(
        f"{API}/auth/login", json={"email": unique_email, "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_error"


async def test_login_rejects_unknown_user(client, unique_email) -> None:
    response = await client.post(
        f"{API}/auth/login", json={"email": unique_email, "password": PASSWORD}
    )
    assert response.status_code == 401


async def test_me_requires_token(client) -> None:
    response = await client.get(f"{API}/auth/me")
    assert response.status_code == 401


async def test_refresh_rotates_and_revokes_old_token(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email)
    tokens = await _login(client, unique_email)

    rotated = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200
    new_tokens = rotated.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    reuse = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reuse.status_code == 401


async def test_logout_revokes_refresh_token(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email)
    tokens = await _login(client, unique_email)

    logout = await client.post(
        f"{API}/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert logout.status_code == 204

    reuse = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reuse.status_code == 401


async def test_finance_role_cannot_manage_users(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email, role=StaffRole.FINANCE)
    tokens = await _login(client, unique_email)

    response = await client.post(
        f"{API}/users",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={
            "email": "new@example.com",
            "full_name": "New Person",
            "role": "reception",
            "password": "another-strong-pass",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


async def test_owner_can_create_user(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    tokens = await _login(client, unique_email)

    response = await client.post(
        f"{API}/users",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={
            "email": "doctor@example.com",
            "full_name": "Dr Test",
            "role": "doctor",
            "password": "another-strong-pass",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "doctor@example.com"
    assert body["role"] == "doctor"
    assert "hashed_password" not in body
