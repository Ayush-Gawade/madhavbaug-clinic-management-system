"""Integration tests for the patient clinical workflow (require PostgreSQL)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.user import StaffRole

pytestmark = pytest.mark.integration

API = "/api/v1"
PASSWORD = "strong-password-123"


async def _login(client, email: str, role: StaffRole) -> dict[str, str]:
    tokens = await client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert tokens.status_code == 200, tokens.text
    return tokens.json()


def _headers(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _register(client, headers: dict[str, str], **overrides) -> dict:
    payload = {
        "full_name": "Asha Patil",
        "phone_number": "+91 98765 43210",
        "categories": ["obesity"],
        **overrides,
    }
    response = await client.post(f"{API}/patients", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_owner_registers_patient_with_categories(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    tokens = await _login(client, unique_email, StaffRole.OWNER)

    patient = await _register(client, _headers(tokens))

    assert patient["internal_id"].startswith("MB-")
    assert patient["full_name"] == "Asha Patil"
    assert patient["phone_number"] == "+91 98765 43210"
    assert [c["category_type"] for c in patient["categories"]] == ["obesity"]


async def test_finance_role_cannot_access_patients(client, staff_factory, unique_email) -> None:
    email = f"fin-{unique_email}"
    await staff_factory(email=email, role=StaffRole.FINANCE)
    tokens = await _login(client, email, StaffRole.FINANCE)

    response = await client.get(f"{API}/patients", headers=_headers(tokens))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


async def test_patient_search_and_filters(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    tokens = await _login(client, unique_email, StaffRole.OWNER)
    headers = _headers(tokens)

    await _register(client, headers, full_name="Rajesh Kumar", categories=["blood_pressure"])
    await _register(client, headers, full_name="Meena Devi", categories=["diabetes"])

    by_name = await client.get(f"{API}/patients", headers=headers, params={"search": "Rajesh"})
    assert by_name.status_code == 200
    assert by_name.json()["total"] == 1
    assert by_name.json()["items"][0]["full_name"] == "Rajesh Kumar"

    by_category = await client.get(
        f"{API}/patients", headers=headers, params={"category": "diabetes"}
    )
    assert by_category.status_code == 200
    assert by_category.json()["total"] == 1
    assert by_category.json()["items"][0]["full_name"] == "Meena Devi"

    invalid_category = await client.get(
        f"{API}/patients", headers=headers, params={"category": "not-a-category"}
    )
    assert invalid_category.status_code == 422


async def test_patient_update_and_duplicate_category_conflict(
    client, staff_factory, unique_email
) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    tokens = await _login(client, unique_email, StaffRole.OWNER)
    headers = _headers(tokens)
    patient = await _register(client, headers)

    updated = await client.patch(
        f"{API}/patients/{patient['id']}", headers=headers, json={"full_name": "Asha P. Patil"}
    )
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Asha P. Patil"

    duplicate = await client.post(
        f"{API}/patients/{patient['id']}/categories",
        headers=headers,
        json={"category_type": "obesity"},
    )
    assert duplicate.status_code == 409


async def test_happy_path_observation_lifecycle(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    tokens = await _login(client, unique_email, StaffRole.OWNER)
    headers = _headers(tokens)
    patient = await _register(client, headers)

    first = await client.post(
        f"{API}/patients/{patient['id']}/observations",
        headers=headers,
        json={
            "observation_type": "blood_pressure",
            "value": 121,
            "unit": "mmhg",
            "observed_at": datetime.now(UTC).isoformat(),
            "measurement_context": {"systolic": 121, "diastolic": 82},
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["source"] == "staff_entry"

    second = await client.post(
        f"{API}/patients/{patient['id']}/observations",
        headers=headers,
        json={
            "observation_type": "blood_glucose",
            "value": 105,
            "unit": "mg/dL",
            "observed_at": datetime.now(UTC).isoformat(),
        },
    )
    assert second.status_code == 201

    listing = await client.get(f"{API}/patients/{patient['id']}/observations", headers=headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 2
    assert body["items"][0]["observation_type"] == "blood_glucose"

    no_tz = await client.post(
        f"{API}/patients/{patient['id']}/observations",
        headers=headers,
        json={
            "observation_type": "weight",
            "value": 70,
            "observed_at": "2026-10-09T10:00:00",
        },
    )
    assert no_tz.status_code == 422


async def test_consent_add_and_withdraw(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    tokens = await _login(client, unique_email, StaffRole.OWNER)
    headers = _headers(tokens)
    patient = await _register(client, headers)

    added = await client.post(
        f"{API}/patients/{patient['id']}/consents",
        headers=headers,
        json={"consent_type": "communication", "purpose": "WhatsApp updates"},
    )
    assert added.status_code == 201
    consent = added.json()
    assert consent["status"] == "active"

    withdrawn = await client.post(
        f"{API}/patients/{patient['id']}/consents/{consent['id']}/withdraw", headers=headers
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "withdrawn"
    assert withdrawn.json()["withdrawn_at"] is not None


async def test_care_plan_versioning_archives_previous_active(
    client, staff_factory, unique_email
) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    tokens = await _login(client, unique_email, StaffRole.OWNER)
    headers = _headers(tokens)
    patient = await _register(client, headers)

    v1 = await client.post(
        f"{API}/patients/{patient['id']}/care-plans",
        headers=headers,
        json={"content": {"diet": "low carb"}},
    )
    assert v1.status_code == 201
    assert v1.json()["version"] == 1
    assert v1.json()["status"] == "active"

    v2 = await client.post(
        f"{API}/patients/{patient['id']}/care-plans",
        headers=headers,
        json={"content": {"diet": "keto"}},
    )
    assert v2.status_code == 201
    assert v2.json()["version"] == 2

    listing = await client.get(f"{API}/patients/{patient['id']}/care-plans", headers=headers)
    assert listing.status_code == 200
    plans = listing.json()
    assert len(plans) == 2
    assert plans[0]["version"] == 2
    statuses = {p["status"] for p in plans}
    assert statuses == {"active", "archived"}


async def test_timeline_bundles_events(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    tokens = await _login(client, unique_email, StaffRole.OWNER)
    headers = _headers(tokens)
    patient = await _register(client, headers)

    await client.post(
        f"{API}/patients/{patient['id']}/observations",
        headers=headers,
        json={
            "observation_type": "weight",
            "value": 72,
            "unit": "kg",
            "observed_at": datetime.now(UTC).isoformat(),
        },
    )
    await client.post(
        f"{API}/patients/{patient['id']}/care-plans",
        headers=headers,
        json={"content": {"diet": "balanced"}},
    )
    await client.post(
        f"{API}/patients/{patient['id']}/consents",
        headers=headers,
        json={"consent_type": "health_data", "purpose": "Monitoring"},
    )

    timeline = await client.get(f"{API}/patients/{patient['id']}/timeline", headers=headers)
    assert timeline.status_code == 200
    events = timeline.json()
    assert len(events) >= 4
    types = {e["event_type"] for e in events}
    assert types >= {"observation", "care_plan", "consent", "category"}
    for i in range(len(events) - 1):
        assert events[i]["occurred_at"] >= events[i + 1]["occurred_at"]
