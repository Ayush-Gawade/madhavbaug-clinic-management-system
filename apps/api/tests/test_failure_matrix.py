"""Safety and failure test matrix (PRD §15.4).

Each PRD failure scenario maps to at least one test here (integration) or in
the adjacent unit suites:

======================================  =========================================
PRD §15.4 scenario                      Where it is asserted
======================================  =========================================
Duplicate webhooks                      test_duplicate_webhook_is_ignored
Incorrect patient mapping               test_unknown_sender_is_quarantined
Missing units                           test_reading_without_units_requests_clarification
Invalid numeric readings                test_unreadable_reading_is_not_compliance
Ambiguous images                        test_ai_service (heuristic) + ai api tests
AI timeout or unavailable service       test_ai_service.test_provider_outage_*
Failed outbound messages                test_failed_outbound_raises_delivery_alert
Invalid or withdrawn consent            test_withdrawn_consent_blocks_dispatch
Expired or paused schedules             test_paused_schedule_blocks_dispatch
Unresolved alerts                       test_open_alerts_remain_visible
Unauthorized staff access               test_unauthorized_and_finance_access_denied
Invalid webhook signature               test_invalid_webhook_signature_is_rejected
======================================  =========================================
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.models.user import StaffRole

pytestmark = pytest.mark.integration

API = "/api/v1"
PASSWORD = "strong-password-123"


def _phone() -> str:
    suffix = uuid.uuid4().int % 10**8
    return f"9191{suffix:08d}"


async def _login(client, email: str) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def _headers(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _register(client, headers: dict[str, str], *, with_phone: bool = True) -> dict:
    payload: dict[str, object] = {"full_name": "Failure Matrix Patient"}
    if with_phone:
        suffix = uuid.uuid4().int % 10**8
        payload["phone_number"] = f"9198{suffix:08d}"
    response = await client.post(f"{API}/patients", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _add_consent(client, headers: dict[str, str], patient_id: str) -> dict:
    response = await client.post(
        f"{API}/patients/{patient_id}/consents",
        headers=headers,
        json={"consent_type": "communication", "purpose": "WhatsApp follow-ups"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_schedule(client, headers: dict[str, str], patient_id: str) -> dict:
    response = await client.post(
        f"{API}/schedules",
        headers=headers,
        json={
            "patient_id": patient_id,
            "follow_up_type": "meal_check_in",
            "recurrence_rule": {"freq": "daily", "interval": 1},
            "scheduled_local_time": "00:01",
            "timezone": "Asia/Kolkata",
            "response_deadline_hours": 12,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _webhook_payload(*, from_phone: str, message_id: str, text: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1234567890",
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


async def _post_webhook(client, payload: dict, signature: str | None = None):
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    return await client.post(
        f"{API}/whatsapp/webhook", content=json.dumps(payload).encode(), headers=headers
    )


async def _queue_one_instance(client, headers: dict[str, str], patient_id: str) -> None:
    await _add_consent(client, headers, patient_id)
    schedule = await _create_schedule(client, headers, patient_id)
    materialize = await client.post(
        f"{API}/schedules/{schedule['id']}/materialize", headers=headers
    )
    assert materialize.status_code == 200, materialize.text
    result = await client.post(f"{API}/schedules/process-due", headers=headers)
    assert result.json()["eligible_to_send"] >= 1


async def test_duplicate_webhook_is_ignored(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)

    payload = _webhook_payload(
        from_phone=patient["phone_number"], message_id="wamid.DUP", text="Same twice"
    )
    first = await _post_webhook(client, payload)
    second = await _post_webhook(client, payload)
    assert first.json()["messages"] == 1
    assert second.json()["duplicate"] == 1
    assert second.json()["messages"] == 0

    conversation = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    assert conversation.json()["total"] == 1


async def test_unknown_sender_is_quarantined(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))

    before = (
        await client.get(f"{API}/messages/exceptions", headers=headers, params={"status": "open"})
    ).json()["total"]
    response = await _post_webhook(
        client, _webhook_payload(from_phone="910000009999", message_id="wamid.UNK", text="Hello?")
    )
    assert response.status_code == 200

    after = await client.get(
        f"{API}/messages/exceptions", headers=headers, params={"status": "open"}
    )
    assert after.json()["total"] == before + 1
    assert any(i["reason"] == "unknown_sender" for i in after.json()["items"])


async def test_reading_without_units_requests_clarification(
    client, staff_factory, unique_email
) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)

    response = await _post_webhook(
        client,
        _webhook_payload(
            from_phone=patient["phone_number"], message_id="wamid.NOUNIT", text="my sugar was 235"
        ),
    )
    assert response.status_code == 200

    observations = await client.get(f"{API}/patients/{patient['id']}/observations", headers=headers)
    assert observations.json()["total"] == 0
    alerts = await client.get(
        f"{API}/alerts", headers=headers, params={"patient_id": patient["id"]}
    )
    assert any(a["alert_type"] == "clarification" for a in alerts.json()["items"])
    assert not any(a["alert_type"] == "threshold" for a in alerts.json()["items"])


async def test_unreadable_reading_is_not_compliance(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)

    response = await _post_webhook(
        client,
        _webhook_payload(
            from_phone=patient["phone_number"], message_id="wamid.GARBAGE", text="asdkjfh qoiwe"
        ),
    )
    assert response.status_code == 200

    observations = await client.get(f"{API}/patients/{patient['id']}/observations", headers=headers)
    assert observations.json()["total"] == 0
    alerts = await client.get(
        f"{API}/alerts", headers=headers, params={"patient_id": patient["id"]}
    )
    assert not any(a["alert_type"] == "threshold" for a in alerts.json()["items"])


async def test_failed_outbound_raises_delivery_alert(
    client, staff_factory, unique_email, monkeypatch
) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    await _queue_one_instance(client, headers, patient["id"])

    async def _reject(_to: str, _body: str):
        from app.services.whatsapp import SendResult

        return SendResult(ok=False, error_code="500", error_message="provider rejected")

    monkeypatch.setattr("app.services.whatsapp.send_text_message", _reject)

    result = await client.post(f"{API}/messages/dispatch", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["failed"] >= 1

    alerts = await client.get(
        f"{API}/alerts", headers=headers, params={"patient_id": patient["id"]}
    )
    assert any(a["alert_type"] == "delivery_failure" for a in alerts.json()["items"])


async def test_withdrawn_consent_blocks_dispatch(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    consent = await _add_consent(client, headers, patient["id"])
    schedule = await _create_schedule(client, headers, patient["id"])
    await client.post(f"{API}/schedules/{schedule['id']}/materialize", headers=headers)

    withdrawn = await client.post(
        f"{API}/patients/{patient['id']}/consents/{consent['id']}/withdraw", headers=headers
    )
    assert withdrawn.status_code == 200

    result = await client.post(f"{API}/schedules/process-due", headers=headers)
    assert result.json()["eligible_to_send"] == 0
    assert result.json()["skipped_consent"] >= 1


async def test_paused_schedule_blocks_dispatch(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    await _add_consent(client, headers, patient["id"])
    schedule = await _create_schedule(client, headers, patient["id"])

    paused = await client.patch(
        f"{API}/schedules/{schedule['id']}", headers=headers, json={"status": "paused"}
    )
    assert paused.status_code == 200

    result = await client.post(f"{API}/schedules/{schedule['id']}/materialize", headers=headers)
    assert result.json()["instances_created"] == 0


async def test_invalid_webhook_signature_is_rejected(
    client, staff_factory, unique_email, monkeypatch
) -> None:
    monkeypatch.setattr("app.core.config.settings.whatsapp_app_secret", "app-secret")
    # Signature enforcement is exercised explicitly; the test dry-run opt-out
    # (enabled suite-wide) must not mask a bad/absent signature here.
    monkeypatch.setattr("app.core.config.settings.webhook_allow_unsigned", False)
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)

    payload = _webhook_payload(
        from_phone=patient["phone_number"], message_id="wamid.SIG", text="Hi"
    )
    rejected = await _post_webhook(client, payload, signature="sha256=deadbeef")
    assert rejected.status_code == 403

    unsigned = await _post_webhook(client, payload)
    assert unsigned.status_code == 403


async def test_unauthenticated_and_finance_access_is_denied(
    client, staff_factory, unique_email
) -> None:
    assert (await client.get(f"{API}/schedules")).status_code == 401
    assert (await client.get(f"{API}/alerts")).status_code == 401
    assert (await client.get(f"{API}/analytics/overview")).status_code == 401
    assert (await client.post(f"{API}/messages/dispatch")).status_code == 401

    finance = unique_email
    await staff_factory(email=finance, role=StaffRole.FINANCE)
    finance_headers = _headers(await _login(client, finance))
    assert (await client.get(f"{API}/alerts", headers=finance_headers)).status_code == 403
    assert (await client.get(f"{API}/schedules", headers=finance_headers)).status_code == 403
    assert (
        await client.get(f"{API}/analytics/overview", headers=finance_headers)
    ).status_code == 403

    doctor = f"doctor-{unique_email}"
    await staff_factory(email=doctor, role=StaffRole.DOCTOR)
    doctor_headers = _headers(await _login(client, doctor))
    assert (await client.get(f"{API}/analytics/finance", headers=doctor_headers)).status_code == 403
