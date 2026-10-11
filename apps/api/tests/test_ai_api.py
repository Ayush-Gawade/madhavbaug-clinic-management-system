"""Integration tests for the AI extraction module (require PostgreSQL)."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest

from app.core.config import settings
from app.models.user import StaffRole
from app.services import ai as ai_service

pytestmark = pytest.mark.integration

API = "/api/v1"
PASSWORD = "strong-password-123"


def _phone() -> str:
    suffix = uuid.uuid4().int % 10**8
    return f"9197{suffix:08d}"


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
        json={"full_name": "AI Test Patient", "phone_number": _phone()},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _webhook_payload(from_phone: str, message_id: str, text: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "field": "messages",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": from_phone,
                                    "id": message_id,
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


async def _post_webhook(client, payload: dict):
    return await client.post(
        f"{API}/whatsapp/webhook",
        content=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )


async def _create_glucose_rule(client, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{API}/safety-rules",
        headers=headers,
        json={
            "rule_key": f"ai_glucose_high_{uuid.uuid4().hex[:8]}",
            "metric": "blood_glucose",
            "comparator": "gt",
            "threshold": 200,
            "unit": "mg/dL",
            "priority": "priority",
            "description": "AI test glucose threshold",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _deactivate_rule(client, headers: dict[str, str], rule_id: str) -> None:
    await client.post(f"{API}/safety-rules/{rule_id}/deactivate", headers=headers)


async def test_inbound_reading_creates_extraction_observation_and_alert(
    client, staff_factory, unique_email
) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    rule_id = await _create_glucose_rule(client, headers)
    try:
        await _assert_reading_flow(client, headers, patient)
    finally:
        await _deactivate_rule(client, headers, rule_id)


async def _assert_reading_flow(client, headers, patient) -> None:
    response = await _post_webhook(
        client,
        _webhook_payload(patient["phone_number"], "wamid.AI1", "Sugar 235 mg/dL after dinner"),
    )
    assert response.status_code == 200, response.text

    extractions = await client.get(
        f"{API}/patients/{patient['id']}/ai-extractions", headers=headers
    )
    assert extractions.status_code == 200, extractions.text
    body = extractions.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["status"] == "succeeded"
    assert item["intent"] == "observation_report"
    assert item["observations_created"] == 1
    assert item["modality"] == "text"
    assert item["message_id"] is not None
    assert float(item["confidence"]) >= 0.7

    observations = await client.get(f"{API}/patients/{patient['id']}/observations", headers=headers)
    assert observations.json()["total"] >= 1
    obs = observations.json()["items"][0]
    assert obs["observation_type"] == "blood_glucose"
    assert obs["source"] == "whatsapp"
    assert obs["ai_extraction_id"] == item["id"]

    alerts = await client.get(
        f"{API}/alerts", headers=headers, params={"patient_id": patient["id"]}
    )
    assert alerts.status_code == 200, alerts.text
    alert_items = alerts.json()["items"]
    assert any(
        a["alert_type"] == "threshold" and a["metric"] == "blood_glucose" for a in alert_items
    )

    detail = await client.get(f"{API}/ai-extractions/{item['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["id"] == item["id"]


async def test_unitless_reading_triggers_clarification(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)

    response = await _post_webhook(
        client,
        _webhook_payload(
            patient["phone_number"], "wamid.AI2", "I checked my sugar today, it was high"
        ),
    )
    assert response.status_code == 200, response.text

    extractions = await client.get(
        f"{API}/patients/{patient['id']}/ai-extractions", headers=headers
    )
    item = extractions.json()["items"][0]
    assert item["status"] == "needs_clarification"
    assert item["needs_clarification"] is True
    assert item["clarification_question"]
    assert item["observations_created"] == 0

    alerts = await client.get(
        f"{API}/alerts", headers=headers, params={"patient_id": patient["id"]}
    )
    assert any(a["alert_type"] == "clarification" for a in alerts.json()["items"])

    conversation = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    inbound = [m for m in conversation.json()["items"] if m["direction"] == "inbound"]
    assert inbound[0]["processing_status"] == "needs_clarification"


async def test_out_of_range_reading_is_not_persisted_and_requests_clarification(
    client, staff_factory, unique_email, monkeypatch
) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)

    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(settings, "openai_api_key", "")
    bogus = ai_service.ExtractionResult(
        modality=ai_service.AIExtractionModality.TEXT,
        model=ai_service._HEURISTIC_MODEL,
        status=ai_service.AIExtractionStatus.SUCCEEDED,
        intent="observation_report",
        confidence=Decimal("0.95"),
        needs_clarification=False,
        observations=[
            ai_service.ExtractedObservation(
                observation_type="blood_glucose",
                value=Decimal("5000"),
                unit="mg/dL",
            )
        ],
    )
    monkeypatch.setattr(ai_service, "extract_from_text", lambda _text: bogus)

    response = await _post_webhook(
        client,
        _webhook_payload(patient["phone_number"], "wamid.AIV1", "Sugar 5000 mg/dL"),
    )
    assert response.status_code == 200, response.text

    observations = await client.get(f"{API}/patients/{patient['id']}/observations", headers=headers)
    assert observations.json()["total"] == 0

    extractions = await client.get(
        f"{API}/patients/{patient['id']}/ai-extractions", headers=headers
    )
    item = extractions.json()["items"][0]
    assert item["status"] == "needs_clarification"
    assert item["observations_created"] == 0
    assert item["needs_clarification"] is True

    alerts = await client.get(
        f"{API}/alerts", headers=headers, params={"patient_id": patient["id"]}
    )
    assert any(a["alert_type"] == "clarification" for a in alerts.json()["items"])

    conversation = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    inbound = [m for m in conversation.json()["items"] if m["direction"] == "inbound"]
    assert inbound[0]["processing_status"] == "needs_clarification"


async def test_unknown_sender_creates_no_extraction(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))

    before = await client.get(
        f"{API}/messages/exceptions", headers=headers, params={"status": "open"}
    )
    before_total = before.json()["total"]

    response = await _post_webhook(
        client, _webhook_payload("910000000123", "wamid.AI3", "Sugar 300 mg/dL")
    )
    assert response.status_code == 200, response.text

    after = await client.get(
        f"{API}/messages/exceptions", headers=headers, params={"status": "open"}
    )
    assert after.json()["total"] == before_total + 1
    assert any(i["reason"] == "unknown_sender" for i in after.json()["items"])


async def test_manual_reanalyze_creates_new_extraction(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)

    await _post_webhook(
        client, _webhook_payload(patient["phone_number"], "wamid.AI4", "Weight 78 kg today")
    )

    conversation = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    inbound = [m for m in conversation.json()["items"] if m["direction"] == "inbound"]
    message_id = inbound[0]["id"]

    reanalyzed = await client.post(f"{API}/messages/{message_id}/analyze", headers=headers)
    assert reanalyzed.status_code == 200, reanalyzed.text
    assert reanalyzed.json()["observations_created"] == 1

    extractions = await client.get(
        f"{API}/patients/{patient['id']}/ai-extractions", headers=headers
    )
    assert extractions.json()["total"] == 2


async def test_manual_reanalyze_unknown_message_returns_404(
    client, staff_factory, unique_email
) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    response = await client.post(f"{API}/messages/{uuid.uuid4()}/analyze", headers=headers)
    assert response.status_code == 404


async def test_finance_role_cannot_view_extractions(client, staff_factory, unique_email) -> None:
    finance = unique_email
    await staff_factory(email=finance, role=StaffRole.FINANCE)
    headers = _headers(await _login(client, finance))
    response = await client.get(f"{API}/patients/{uuid.uuid4()}/ai-extractions", headers=headers)
    assert response.status_code == 403


async def test_extractions_require_authentication(client) -> None:
    assert (await client.get(f"{API}/patients/{uuid.uuid4()}/ai-extractions")).status_code == 401
    assert (await client.get(f"{API}/ai-extractions/{uuid.uuid4()}")).status_code == 401
    assert (await client.post(f"{API}/messages/{uuid.uuid4()}/analyze")).status_code == 401
