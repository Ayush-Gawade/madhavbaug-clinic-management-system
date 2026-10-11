"""Integration tests for non-response, reminders and escalation (PostgreSQL)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.scheduling import FollowUpInstance, FollowUpInstanceStatus
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


async def _register(client, headers: dict[str, str], phone: str | None = None) -> dict:
    payload: dict[str, object] = {"full_name": "Non-Response Test Patient"}
    if phone is not None:
        payload["phone_number"] = phone
    response = await client.post(f"{API}/patients", headers=headers, json=payload)
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
        "response_deadline_hours": 1,
        "reminder_policy": {"max_reminders": 1, "interval_hours": 6},
        "escalation_policy": {"escalate_after_deadline": True, "review_priority": "priority"},
        **overrides,
    }
    response = await client.post(f"{API}/schedules", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _instances(client, headers: dict[str, str], patient_id: str, **params) -> list[dict]:
    query = "&".join(["size=50", *[f"{key}={value}" for key, value in params.items()]])
    response = await client.get(f"{API}/instances?patient_id={patient_id}&{query}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def _force(
    session_factory,
    instance_id: str,
    *,
    status: FollowUpInstanceStatus | None = None,
    response_deadline_at: datetime | None = None,
) -> None:
    async with session_factory() as session:
        instance = await session.get(FollowUpInstance, uuid.UUID(instance_id))
        assert instance is not None
        if status is not None:
            instance.status = status
        if response_deadline_at is not None:
            instance.response_deadline_at = response_deadline_at
        await session.commit()


async def _first_instance_id(client, headers, patient_id: str) -> str:
    items = await _instances(client, headers, patient_id)
    assert items
    return items[0]["id"]


async def test_reminder_then_overdue_then_escalation(
    client, staff_factory, unique_email, session_factory
) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient_resp = await client.post(
        f"{API}/patients",
        headers=headers,
        json={"full_name": "Non Response Patient", "phone_number": "919812345678"},
    )
    assert patient_resp.status_code == 201, patient_resp.text
    patient = patient_resp.json()
    await _create_consent(client, headers, patient["id"])
    template = await _create_template(client, headers)
    schedule = await _create_schedule(
        client, headers, patient["id"], message_template_id=template["id"]
    )
    await client.post(f"{API}/schedules/{schedule['id']}/materialize", headers=headers)
    assert schedule["status"] == "active"
    assert schedule["reminder_policy"] == {"max_reminders": 1, "interval_hours": 6}
    assert template["id"] == schedule["message_template_id"]

    instance_id = await _first_instance_id(client, headers, patient["id"])
    now = datetime.now(UTC)
    await _force(
        session_factory,
        instance_id,
        status=FollowUpInstanceStatus.SENT,
        response_deadline_at=now - timedelta(hours=1),
    )

    first = await client.post(f"{API}/schedules/process-non-response", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["reminders_sent"] >= 1

    # The pending instance now carries a reminder and a future deadline.
    async with session_factory() as session:
        refreshed = await session.get(FollowUpInstance, uuid.UUID(instance_id))
        assert refreshed is not None
        assert refreshed.status == FollowUpInstanceStatus.SENT
        assert refreshed.reminder_count == 1
        assert refreshed.response_deadline_at is not None
        assert refreshed.response_deadline_at > datetime.now(UTC)

    # Exhaust the reminder and pass the deadline again -> overdue + escalation.
    await _force(
        session_factory,
        instance_id,
        status=FollowUpInstanceStatus.SENT,
        response_deadline_at=datetime.now(UTC) - timedelta(hours=1),
    )
    result = await client.post(f"{API}/schedules/process-non-response", headers=headers)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["marked_overdue"] >= 1
    assert body["escalations_created"] >= 1

    overdue = await _instances(client, headers, patient["id"], status="overdue")
    assert any(item["id"] == instance_id for item in overdue)

    alerts = await client.get(f"{API}/alerts?patient_id={patient['id']}", headers=headers)
    assert alerts.status_code == 200, alerts.text
    non_response_alerts = [
        alert for alert in alerts.json()["items"] if alert["alert_type"] == "non_response"
    ]
    assert non_response_alerts
    assert non_response_alerts[0]["priority"] == "priority"
    assert non_response_alerts[0]["follow_up_instance_id"] == instance_id


async def test_failed_reminder_does_not_advance_state_or_alert_overdue(
    client, staff_factory, unique_email, session_factory, monkeypatch
) -> None:
    """A rejected reminder is a delivery failure, not a reminder that counts (FR-027)."""
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient_resp = await client.post(
        f"{API}/patients",
        headers=headers,
        json={"full_name": "Failed Reminder Patient", "phone_number": "919812345679"},
    )
    assert patient_resp.status_code == 201, patient_resp.text
    patient = patient_resp.json()
    await _create_consent(client, headers, patient["id"])
    schedule = await _create_schedule(client, headers, patient["id"])
    await client.post(f"{API}/schedules/{schedule['id']}/materialize", headers=headers)
    instance_id = await _first_instance_id(client, headers, patient["id"])
    await _force(
        session_factory,
        instance_id,
        status=FollowUpInstanceStatus.SENT,
        response_deadline_at=datetime.now(UTC) - timedelta(hours=1),
    )

    from app.services import whatsapp as whatsapp_client

    async def _reject(_to: str, _body: str) -> whatsapp_client.SendResult:
        return whatsapp_client.SendResult(
            ok=False, error_code="provider_rejected", error_message="provider rejected the send"
        )

    monkeypatch.setattr(whatsapp_client, "send_text_message", _reject)

    result = await client.post(f"{API}/schedules/process-non-response", headers=headers)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["reminders_failed"] >= 1
    assert body["marked_overdue"] == 0

    async with session_factory() as session:
        refreshed = await session.get(FollowUpInstance, uuid.UUID(instance_id))
        assert refreshed is not None
        assert refreshed.status == FollowUpInstanceStatus.FAILED
        assert refreshed.reminder_count == 0

    alerts = await client.get(f"{API}/alerts?patient_id={patient['id']}", headers=headers)
    assert any(alert["alert_type"] == "delivery_failure" for alert in alerts.json()["items"])


async def test_failed_delivery_is_not_treated_as_non_response(
    client, staff_factory, unique_email, session_factory
) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await client.post(
        f"{API}/patients", headers=headers, json={"full_name": "Failed Delivery Patient"}
    )
    patient = patient.json()
    await _create_consent(client, headers, patient["id"])
    schedule = await _create_schedule(client, headers, patient["id"])
    await client.post(f"{API}/schedules/{schedule['id']}/materialize", headers=headers)
    instance_id = await _first_instance_id(client, headers, patient["id"])

    await _force(
        session_factory,
        instance_id,
        status=FollowUpInstanceStatus.FAILED,
        response_deadline_at=datetime.now(UTC) - timedelta(hours=2),
    )
    result = await client.post(f"{API}/schedules/process-non-response", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["marked_overdue"] == 0

    async with session_factory() as session:
        refreshed = await session.get(FollowUpInstance, uuid.UUID(instance_id))
        assert refreshed is not None
        assert refreshed.status == FollowUpInstanceStatus.FAILED


async def test_dispatch_without_number_raises_delivery_failure_alert(
    client, staff_factory, unique_email, session_factory
) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await client.post(
        f"{API}/patients", headers=headers, json={"full_name": "No Phone Patient"}
    )
    patient = patient.json()
    await _create_consent(client, headers, patient["id"])
    schedule = await _create_schedule(client, headers, patient["id"])
    await client.post(f"{API}/schedules/{schedule['id']}/materialize", headers=headers)
    instance_id = await _first_instance_id(client, headers, patient["id"])
    await _force(session_factory, instance_id, status=FollowUpInstanceStatus.QUEUED)

    dispatch = await client.post(f"{API}/messages/dispatch", headers=headers)
    assert dispatch.status_code == 200, dispatch.text

    async with session_factory() as session:
        refreshed = await session.get(FollowUpInstance, uuid.UUID(instance_id))
        assert refreshed is not None
        assert refreshed.status == FollowUpInstanceStatus.FAILED

    alerts = await client.get(f"{API}/alerts?patient_id={patient['id']}", headers=headers)
    assert alerts.status_code == 200, alerts.text
    assert any(alert["alert_type"] == "delivery_failure" for alert in alerts.json()["items"])


async def test_acknowledge_and_resolve_instance(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await client.post(
        f"{API}/patients", headers=headers, json={"full_name": "Ack Patient"}
    )
    patient = patient.json()
    schedule = await _create_schedule(client, headers, patient["id"])
    await client.post(f"{API}/schedules/{schedule['id']}/materialize", headers=headers)
    instance_id = await _first_instance_id(client, headers, patient["id"])

    ack = await client.post(
        f"{API}/instances/{instance_id}/acknowledge",
        headers=headers,
        json={"notes": "Seen by front desk"},
    )
    assert ack.status_code == 200, ack.text
    assert ack.json()["acknowledged_by"] is not None

    resolved = await client.post(
        f"{API}/instances/{instance_id}/resolve", headers=headers, json={"notes": "Called patient"}
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "skipped"

    again = await client.post(f"{API}/instances/{instance_id}/resolve", headers=headers, json={})
    assert again.status_code == 409


async def test_finance_role_cannot_run_non_response(client, staff_factory, unique_email) -> None:
    finance = unique_email
    await staff_factory(email=finance, role=StaffRole.FINANCE)
    headers = _headers(await _login(client, finance))
    response = await client.post(f"{API}/schedules/process-non-response", headers=headers)
    assert response.status_code == 403
