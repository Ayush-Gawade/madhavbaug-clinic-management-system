"""Integration tests for the rule engine, alerts and review queue (PostgreSQL)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

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
        f"{API}/patients", headers=headers, json={"full_name": "Alert Test Patient"}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_rule(
    client,
    headers: dict[str, str],
    *,
    rule_key: str,
    metric: str,
    comparator: str,
    threshold: float,
    priority: str,
    unit: str = "mg/dL",
    context: dict | None = None,
) -> dict:
    response = await client.post(
        f"{API}/safety-rules",
        headers=headers,
        json={
            "rule_key": rule_key,
            "metric": metric,
            "comparator": comparator,
            "threshold": threshold,
            "unit": unit,
            "priority": priority,
            "description": "test rule",
            "context": context,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _add_observation(client, headers: dict[str, str], patient_id: str, **kwargs) -> dict:
    payload = {
        "observation_type": "blood_glucose",
        "value": 210,
        "unit": "mg/dL",
        "observed_at": datetime.now(UTC).isoformat(),
        "source": "staff_entry",
        **kwargs,
    }
    response = await client.post(
        f"{API}/patients/{patient_id}/observations", headers=headers, json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def _key(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _make_alert(client, headers: dict[str, str], patient: dict, **overrides) -> dict:
    rule_payload = {
        "rule_key": _key("glucose_high"),
        "metric": "blood_glucose",
        "comparator": "gt",
        "threshold": 200,
        "unit": "mg/dL",
        "priority": "priority",
        "description": "test",
        "context": None,
    }
    rule_payload.update(overrides.pop("rule", {}))
    response = await client.post(f"{API}/safety-rules", headers=headers, json=rule_payload)
    assert response.status_code == 201, response.text

    obs_payload = {
        "observation_type": "blood_glucose",
        "value": 210,
        "unit": "mg/dL",
        "observed_at": datetime.now(UTC).isoformat(),
        "source": "staff_entry",
        "measurement_context": None,
    }
    obs_payload.update(overrides.pop("observation", {}))
    obs = await client.post(
        f"{API}/patients/{patient['id']}/observations", headers=headers, json=obs_payload
    )
    assert obs.status_code == 201, obs.text

    listing = await client.get(f"{API}/alerts?patient_id={patient['id']}", headers=headers)
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] >= 1
    return listing.json()["items"][0]


async def test_threshold_violation_creates_alert(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)

    await client.post(
        f"{API}/safety-rules",
        headers=headers,
        json={
            "rule_key": _key("glucose_high"),
            "metric": "blood_glucose",
            "comparator": "gt",
            "threshold": 200,
            "unit": "mg/dL",
            "priority": "priority",
            "context": None,
        },
    )

    await _add_observation(client, headers, patient["id"], value=210, unit="mg/dL")
    alerts = await client.get(f"{API}/alerts?patient_id={patient['id']}", headers=headers)
    assert alerts.json()["total"] == 1
    alert = alerts.json()["items"][0]
    assert alert["status"] == "open"
    assert alert["priority"] == "priority"
    assert alert["alert_type"] == "threshold"
    assert alert["metric"] == "blood_glucose"
    assert "above" in alert["reason"]
    assert alert["rule_version"] == 1

    # A reading within range must not raise a further alert.
    await _add_observation(client, headers, patient["id"], value=120, unit="mg/dL")
    alerts2 = await client.get(f"{API}/alerts?patient_id={patient['id']}", headers=headers)
    assert alerts2.json()["total"] == 1


async def test_blood_pressure_context_alert(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)

    await client.post(
        f"{API}/safety-rules",
        headers=headers,
        json={
            "rule_key": _key("bp_systolic_high"),
            "metric": "systolic",
            "comparator": "gt",
            "threshold": 140,
            "unit": "mmHg",
            "priority": "urgent",
            "context": None,
        },
    )
    await _add_observation(
        client,
        headers,
        patient["id"],
        observation_type="blood_pressure",
        value=None,
        unit="mmHg",
        measurement_context={"systolic": 150, "diastolic": 95},
    )
    alerts = await client.get(f"{API}/alerts?patient_id={patient['id']}", headers=headers)
    assert alerts.json()["total"] == 1
    alert = alerts.json()["items"][0]
    assert alert["priority"] == "urgent"
    assert alert["metric"] == "systolic"


async def test_alert_lifecycle_and_actions(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    alert = await _make_alert(client, headers, patient)

    acked = await client.post(
        f"{API}/alerts/{alert['id']}/acknowledge", headers=headers, json={"notes": "Seen"}
    )
    assert acked.status_code == 200, acked.text
    assert acked.json()["status"] == "acknowledged"

    again = await client.post(f"{API}/alerts/{alert['id']}/acknowledge", headers=headers, json={})
    assert again.status_code == 409

    escalated = await client.post(
        f"{API}/alerts/{alert['id']}/escalate", headers=headers, json={"notes": "Urgent"}
    )
    assert escalated.status_code == 200
    assert escalated.json()["priority"] == "urgent"

    resolved = await client.post(
        f"{API}/alerts/{alert['id']}/resolve", headers=headers, json={"notes": "Adjusted plan"}
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    closed_again = await client.post(
        f"{API}/alerts/{alert['id']}/resolve", headers=headers, json={}
    )
    assert closed_again.status_code == 409

    detail = await client.get(f"{API}/alerts/{alert['id']}", headers=headers)
    assert detail.status_code == 200
    action_types = [action["action_type"] for action in detail.json()["actions"]]
    assert action_types == ["acknowledge", "escalate", "resolve"]


async def test_alert_summary_counts(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    await _make_alert(client, headers, patient)

    summary = await client.get(f"{API}/alerts/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["open_total"] >= 1
    assert body["open"] + body["acknowledged"] >= 1


async def test_safety_rule_versioning(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    key = _key("glucose_high")

    first = await client.post(
        f"{API}/safety-rules",
        headers=headers,
        json={
            "rule_key": key,
            "metric": "blood_glucose",
            "comparator": "gt",
            "threshold": 200,
            "unit": "mg/dL",
            "priority": "priority",
        },
    )
    assert first.status_code == 201
    assert first.json()["version"] == 1

    second = await client.post(
        f"{API}/safety-rules",
        headers=headers,
        json={
            "rule_key": key,
            "metric": "blood_glucose",
            "comparator": "gt",
            "threshold": 180,
            "unit": "mg/dL",
            "priority": "priority",
        },
    )
    assert second.status_code == 201
    assert second.json()["version"] == 2

    active = await client.get(f"{API}/safety-rules", headers=headers)
    active_matching = [r for r in active.json() if r["rule_key"] == key]
    assert len(active_matching) == 1
    assert active_matching[0]["version"] == 2

    history = await client.get(f"{API}/safety-rules?active_only=false", headers=headers)
    history_matching = [r for r in history.json() if r["rule_key"] == key]
    assert len(history_matching) == 2
    assert any(r["is_active"] is False for r in history_matching)

    deactivated = await client.post(
        f"{API}/safety-rules/{second.json()['id']}/deactivate", headers=headers
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    active_after = await client.get(f"{API}/safety-rules", headers=headers)
    assert [r for r in active_after.json() if r["rule_key"] == key] == []


async def test_finance_role_cannot_view_or_manage_alerts(
    client, staff_factory, unique_email
) -> None:
    finance = unique_email
    await staff_factory(email=finance, role=StaffRole.FINANCE)
    headers = _headers(await _login(client, finance))
    assert (await client.get(f"{API}/alerts", headers=headers)).status_code == 403
    assert (await client.get(f"{API}/alerts/summary", headers=headers)).status_code == 403
    create = await client.post(
        f"{API}/safety-rules",
        headers=headers,
        json={
            "rule_key": "x",
            "metric": "blood_glucose",
            "comparator": "gt",
            "threshold": 200,
            "unit": "mg/dL",
            "priority": "priority",
        },
    )
    assert create.status_code == 403


async def test_reception_cannot_manage_rules(client, staff_factory, unique_email) -> None:
    reception = unique_email
    await staff_factory(email=reception, role=StaffRole.RECEPTION)
    headers = _headers(await _login(client, reception))
    assert (await client.get(f"{API}/alerts", headers=headers)).status_code == 200
    create = await client.post(
        f"{API}/safety-rules",
        headers=headers,
        json={
            "rule_key": _key("r"),
            "metric": "blood_glucose",
            "comparator": "gt",
            "threshold": 200,
            "unit": "mg/dL",
            "priority": "priority",
        },
    )
    assert create.status_code == 403


async def test_alerts_require_authentication(client) -> None:
    assert (await client.get(f"{API}/alerts")).status_code == 401
    assert (await client.get(f"{API}/alerts/summary")).status_code == 401
