"""Integration tests for the scheduling module (require PostgreSQL)."""

from __future__ import annotations

import uuid

import pytest

from app.models.user import StaffRole

pytestmark = pytest.mark.integration

API = "/api/v1"
PASSWORD = "strong-password-123"


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
        json={"full_name": "Schedule Test Patient"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_consent(client, headers: dict[str, str], patient_id: str) -> None:
    response = await client.post(
        f"{API}/patients/{patient_id}/consents",
        headers=headers,
        json={"consent_type": "communication", "purpose": "WhatsApp follow-ups"},
    )
    assert response.status_code == 201, response.text


async def _create_template(client, headers: dict[str, str]) -> dict:
    response = await client.post(
        f"{API}/messages/templates",
        headers=headers,
        json={
            "code": f"CK-{uuid.uuid4().hex[:6].upper()}",
            "name": "Daily check-in",
            "category": "scheduled_check_in",
            "language": "en",
            "body": "Good morning, {{name}}. It is time for your scheduled check-in.",
            "approved": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_schedule(client, headers: dict[str, str], patient_id: str, **overrides) -> dict:
    payload = {
        "patient_id": patient_id,
        "follow_up_type": "meal_check_in",
        "recurrence_rule": {"freq": "daily", "interval": 1},
        "scheduled_local_time": "00:01",
        "timezone": "Asia/Kolkata",
        "response_deadline_hours": 12,
        "reminder_policy": {"max_reminders": 2, "interval_hours": 6},
        "escalation_policy": {"escalate_after_deadline": True, "review_priority": "priority"},
        **overrides,
    }
    response = await client.post(f"{API}/schedules", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_owner_creates_schedule_and_materializes_daily_instances(
    client, staff_factory, unique_email
) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    template = await _create_template(client, headers)

    schedule = await _create_schedule(
        client, headers, patient["id"], message_template_id=template["id"]
    )
    assert schedule["status"] == "active"
    assert schedule["follow_up_type"] == "meal_check_in"
    assert schedule["recurrence_rule"] == {"freq": "daily", "interval": 1}
    assert schedule["response_deadline_hours"] == 12

    advanced = await client.post(f"{API}/schedules/{schedule['id']}/materialize", headers=headers)
    assert advanced.status_code == 200, advanced.text
    created = advanced.json()["instances_created"]
    assert created >= 1

    queued_before = (
        await client.get(
            f"{API}/instances?status=scheduled&patient_id={patient['id']}", headers=headers
        )
    ).json()
    assert queued_before["total"] == created
    all_advanced = queued_before["items"]

    due_dates = {item["due_date"] for item in all_advanced}
    assert len(due_dates) == created

    again = await client.post(f"{API}/schedules/{schedule['id']}/materialize", headers=headers)
    assert again.json()["instances_created"] == 0


async def test_dispatch_requires_active_consent(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    schedule = await _create_schedule(client, headers, patient["id"])
    await client.post(f"{API}/schedules/{schedule['id']}/materialize", headers=headers)

    result = await client.post(f"{API}/schedules/process-due", headers=headers)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["eligible_to_send"] == 0
    assert body["skipped_consent"] >= 1


async def test_dispatch_queues_instances_with_consent(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    await _create_consent(client, headers, patient["id"])
    schedule = await _create_schedule(client, headers, patient["id"])
    await client.post(f"{API}/schedules/{schedule['id']}/materialize", headers=headers)

    result = await client.post(f"{API}/schedules/process-due", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["eligible_to_send"] >= 1

    queue = await client.get(f"{API}/instances?status=queued", headers=headers)
    assert queue.status_code == 200, queue.text
    assert queue.json()["total"] >= 1
    for item in queue.json()["items"]:
        assert item["status"] == "queued"
        assert item["response_deadline_at"] is not None


async def test_finance_role_cannot_manage_schedules(client, staff_factory, unique_email) -> None:
    finance = unique_email
    await staff_factory(email=finance, role=StaffRole.FINANCE)
    headers = _headers(await _login(client, finance))
    response = await client.post(
        f"{API}/schedules",
        headers=headers,
        json={
            "patient_id": str(uuid.uuid4()),
            "follow_up_type": "meal_check_in",
            "recurrence_rule": {"freq": "daily", "interval": 1},
        },
    )
    assert response.status_code == 403


async def test_templates_crud_and_invalid_recurrence_rejected(
    client, staff_factory, unique_email
) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    template = await _create_template(client, headers)

    listing = await client.get(f"{API}/messages/templates", headers=headers)
    assert listing.status_code == 200
    assert any(t["id"] == template["id"] for t in listing.json())

    updated = await client.patch(
        f"{API}/messages/templates/{template['id']}",
        headers=headers,
        json={"approved": False},
    )
    assert updated.status_code == 200
    assert updated.json()["approved"] is False

    bad = await client.post(
        f"{API}/schedules",
        headers=headers,
        json={
            "patient_id": patient["id"],
            "follow_up_type": "meal_check_in",
            "recurrence_rule": {"freq": "weekly", "on_weekdays": [0]},
        },
    )
    assert bad.status_code == 422

    bad2 = await client.post(
        f"{API}/schedules",
        headers=headers,
        json={
            "patient_id": patient["id"],
            "follow_up_type": "meal_check_in",
            "recurrence_rule": {"freq": "monthly", "day_of_month": 32},
        },
    )
    assert bad2.status_code == 422


async def test_schedule_pause_stops_materialization(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    schedule = await _create_schedule(client, headers, patient["id"])

    paused = await client.patch(
        f"{API}/schedules/{schedule['id']}",
        headers=headers,
        json={"status": "paused"},
    )
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    result = await client.post(f"{API}/schedules/{schedule['id']}/materialize", headers=headers)
    assert result.json()["instances_created"] == 0

    resumed = await client.patch(
        f"{API}/schedules/{schedule['id']}",
        headers=headers,
        json={"status": "active"},
    )
    assert resumed.json()["status"] == "active"
    result2 = await client.post(f"{API}/schedules/{schedule['id']}/materialize", headers=headers)
    assert result2.json()["instances_created"] >= 1


async def test_schedule_update_persists_message_template_id(
    client, staff_factory, unique_email
) -> None:
    """PATCHing a UUID field (message_template_id) must commit, not roll back.

    Regression: the audit change_summary is stored in JSONB; a raw pydantic
    uuid.UUID in it crashed the commit and silently undid the update.
    """
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    template = await _create_template(client, headers)
    schedule = await _create_schedule(client, headers, patient["id"])

    updated = await client.patch(
        f"{API}/schedules/{schedule['id']}",
        headers=headers,
        json={"message_template_id": template["id"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["message_template_id"] == template["id"]

    fetched = await client.get(f"{API}/schedules/{schedule['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["message_template_id"] == template["id"]
