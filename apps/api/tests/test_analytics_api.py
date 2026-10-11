"""Integration tests for the analytics/reporting module (require PostgreSQL)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest

from app.models.user import StaffRole

pytestmark = pytest.mark.integration

API = "/api/v1"
PASSWORD = "strong-password-123"


def _phone() -> str:
    suffix = uuid.uuid4().int % 10**8
    return f"9198{suffix:08d}"


def _at(day: date, hour: int) -> str:
    return datetime.combine(day, time(hour, 0), tzinfo=UTC).isoformat()


async def _login(client, email: str) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def _headers(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _register(client, headers: dict[str, str]) -> dict:
    response = await client.post(
        f"{API}/patients",
        headers=headers,
        json={"full_name": "Analytics Test Patient", "phone_number": _phone()},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _add_observation(client, headers: dict[str, str], patient_id: str, **overrides) -> dict:
    payload = {
        "observation_type": "blood_glucose",
        "value": 120,
        "unit": "mg/dL",
        "observed_at": datetime.now(UTC).isoformat(),
        **overrides,
    }
    response = await client.post(
        f"{API}/patients/{patient_id}/observations", headers=headers, json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_urgent_glucose_rule(client, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{API}/safety-rules",
        headers=headers,
        json={
            "rule_key": f"analytics_glucose_{uuid.uuid4().hex[:8]}",
            "metric": "blood_glucose",
            "comparator": "gt",
            "threshold": 200,
            "unit": "mg/dL",
            "priority": "urgent",
            "description": "Analytics test glucose threshold",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_treatment(client, headers: dict[str, str]) -> dict:
    response = await client.post(
        f"{API}/treatments",
        headers=headers,
        json={
            "name": "Analytics Panchakarma",
            "treatment_code": f"AN-{uuid.uuid4().hex[:6].upper()}",
            "service_category": "Panchakarma",
            "list_price": "10000.00",
            "estimated_sessions": 21,
            "royalty_percent": "5",
            "therapist_cost": "3000",
            "material_cost": "1000",
            "other_direct_cost": "500",
            "overhead_allocation": "500",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_overview_requires_authentication(client) -> None:
    response = await client.get(f"{API}/analytics/overview")
    assert response.status_code == 401


async def test_overview_reflects_new_patient_and_observation(
    client, staff_factory, unique_email
) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))

    before = (await client.get(f"{API}/analytics/overview", headers=headers)).json()
    patient = await _register(client, headers)
    await _add_observation(client, headers, patient["id"])
    after = (await client.get(f"{API}/analytics/overview", headers=headers)).json()

    assert after["total_patients"] == before["total_patients"] + 1
    assert after["active_patients"] == before["active_patients"] + 1
    assert after["pending_observation_reviews"] >= before["pending_observation_reviews"] + 1


async def test_operations_lists_patient_with_open_alert(
    client, staff_factory, unique_email
) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))
    patient = await _register(client, headers)
    rule_id = await _create_urgent_glucose_rule(client, headers)
    try:
        await _add_observation(client, headers, patient["id"], value=260)
        operations = await client.get(f"{API}/analytics/operations", headers=headers)
        assert operations.status_code == 200, operations.text
        body = operations.json()
        match = [item for item in body["items"] if item["patient_id"] == patient["id"]]
        assert match, body
        assert match[0]["priority"] == "urgent"
        assert match[0]["reasons"]
    finally:
        await client.post(f"{API}/safety-rules/{rule_id}/deactivate", headers=headers)


async def test_adherence_summary_includes_denominator_definition(
    client, staff_factory, unique_email
) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))
    patient = await _register(client, headers)

    schedule = await client.post(
        f"{API}/schedules",
        headers=headers,
        json={
            "patient_id": patient["id"],
            "follow_up_type": "meal_check_in",
            "recurrence_rule": {"freq": "daily", "interval": 1},
            "scheduled_local_time": "00:01",
            "timezone": "Asia/Kolkata",
            "response_deadline_hours": 12,
        },
    )
    assert schedule.status_code == 201, schedule.text
    materialized = await client.post(
        f"{API}/schedules/{schedule.json()['id']}/materialize", headers=headers
    )
    assert materialized.status_code == 200, materialized.text

    today = datetime.now(UTC).date()
    adherence = await client.get(
        f"{API}/analytics/adherence",
        headers=headers,
        params={
            "date_from": (today - timedelta(days=1)).isoformat(),
            "date_to": (today + timedelta(days=7)).isoformat(),
            "patient_id": patient["id"],
        },
    )
    assert adherence.status_code == 200, adherence.text
    body = adherence.json()
    assert body["scheduled_total"] >= 1
    assert "skipped" in body["rate_definition"]
    assert Decimal(body["completion_rate_percent"]) >= Decimal("0")


async def test_patient_glucose_trends_bucket_by_day(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))
    patient = await _register(client, headers)

    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    await _add_observation(client, headers, patient["id"], value=120, observed_at=_at(today, 6))
    await _add_observation(client, headers, patient["id"], value=140, observed_at=_at(today, 12))
    await _add_observation(
        client, headers, patient["id"], value=110, observed_at=_at(yesterday, 12)
    )

    trends = await client.get(
        f"{API}/analytics/patients/{patient['id']}/trends",
        headers=headers,
        params={
            "observation_type": "blood_glucose",
            "granularity": "day",
            "date_from": yesterday.isoformat(),
            "date_to": today.isoformat(),
        },
    )
    assert trends.status_code == 200, trends.text
    body = trends.json()
    assert body["unit"] == "mg/dL"
    assert body["granularity"] == "day"
    assert len(body["points"]) == 2
    assert body["missing_buckets"] == 0
    by_bucket = {point["bucket"]: point for point in body["points"]}
    assert by_bucket[yesterday.isoformat()]["count"] == 1
    assert by_bucket[today.isoformat()]["count"] == 2
    assert Decimal(by_bucket[today.isoformat()]["average_value"]) == Decimal("130.00")


async def test_trends_unknown_patient_returns_404(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))
    response = await client.get(
        f"{API}/analytics/patients/{uuid.uuid4()}/trends",
        headers=headers,
        params={"observation_type": "blood_glucose"},
    )
    assert response.status_code == 404


async def test_finance_overview_separates_recorded_and_estimated(
    client, staff_factory, unique_email
) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))
    treatment = await _create_treatment(client, headers)
    patient = await _register(client, headers)

    assigned = await client.post(
        f"{API}/patients/{patient['id']}/treatments",
        headers=headers,
        json={"treatment_id": treatment["id"], "discount_percent": 10},
    )
    assert assigned.status_code == 201, assigned.text
    paid = await client.post(
        f"{API}/patients/{patient['id']}/payments",
        headers=headers,
        json={"treatment_id": treatment["id"], "amount": "3000", "payment_method": "upi"},
    )
    assert paid.status_code == 201, paid.text

    overview = await client.get(f"{API}/analytics/finance", headers=headers)
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert Decimal(body["recorded_revenue"]) >= Decimal("3000.00")
    assert body["notes"]
    lines = [line for line in body["lines"] if line["treatment_id"] == treatment["id"]]
    assert lines, body["lines"]
    # charge = 10000 * (1 - 0.10) = 9000; direct = 450 royalty + 3000 + 1000 + 500 = 4950.
    assert Decimal(lines[0]["billed"]) == Decimal("9000.00")
    assert Decimal(lines[0]["estimated_direct_costs"]) == Decimal("4950.00")
    assert Decimal(lines[0]["estimated_contribution"]) == Decimal("4050.00")


async def test_finance_overview_role_gating(client, staff_factory, unique_email) -> None:
    doctor_email = f"doc-{unique_email}"
    finance_email = f"fin-{unique_email}"
    await staff_factory(email=doctor_email, role=StaffRole.DOCTOR)
    await staff_factory(email=finance_email, role=StaffRole.FINANCE)

    doctor_headers = _headers(await _login(client, doctor_email))
    finance_headers = _headers(await _login(client, finance_email))

    doctor_finance = await client.get(f"{API}/analytics/finance", headers=doctor_headers)
    finance_finance = await client.get(f"{API}/analytics/finance", headers=finance_headers)
    finance_overview = await client.get(f"{API}/analytics/overview", headers=finance_headers)

    assert doctor_finance.status_code == 403
    assert finance_finance.status_code == 200
    assert finance_overview.status_code == 403
