"""Integration tests for the WhatsApp messaging module (require PostgreSQL)."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.models.messaging import (
    DeliveryStatus,
    MessageDirection,
    MessageProcessingStatus,
    MessageType,
    WhatsAppMessage,
)
from app.models.scheduling import FollowUpInstance, FollowUpInstanceStatus
from app.models.user import StaffRole
from app.services import ai as ai_service
from app.services import ai_queue
from app.services import messaging as messaging_service
from app.services import whatsapp as whatsapp_client

pytestmark = pytest.mark.integration

API = "/api/v1"
PASSWORD = "strong-password-123"


def _phone() -> str:
    """A unique E.164-style test number (last 10 digits are unique)."""
    suffix = uuid.uuid4().int % 10**8
    return f"9198{suffix:08d}"


async def _login(client, email: str) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def _headers(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _register(client, headers: dict[str, str], phone: str | None = None) -> dict:
    response = await client.post(
        f"{API}/patients",
        headers=headers,
        json={"full_name": "Messaging Test Patient", "phone_number": phone or _phone()},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_consent(client, headers: dict[str, str], patient_id: str) -> dict:
    response = await client.post(
        f"{API}/patients/{patient_id}/consents",
        headers=headers,
        json={"consent_type": "communication", "purpose": "WhatsApp follow-ups"},
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
        **overrides,
    }
    response = await client.post(f"{API}/schedules", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _create_template(
    client, headers: dict[str, str], *, body: str = "Good morning, {{name}}.", approved: bool = True
) -> dict:
    response = await client.post(
        f"{API}/messages/templates",
        headers=headers,
        json={
            "code": f"CK-{uuid.uuid4().hex[:6].upper()}",
            "name": "daily_check_in",
            "category": "scheduled_check_in",
            "language": "en",
            "body": body,
            "approved": approved,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _queue_dispatchable_instance(
    client, headers: dict[str, str], patient_id: str, **schedule_overrides
) -> dict:
    await _create_consent(client, headers, patient_id)
    schedule = await _create_schedule(client, headers, patient_id, **schedule_overrides)
    materialize = await client.post(
        f"{API}/schedules/{schedule['id']}/materialize", headers=headers
    )
    assert materialize.status_code == 200, materialize.text
    result = await client.post(f"{API}/schedules/process-due", headers=headers)
    assert result.json()["eligible_to_send"] >= 1
    return schedule


def _webhook_payload(
    *, from_phone: str, message_id: str, text: str, timestamp: str = "1700000000"
) -> dict:
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
                                    "timestamp": timestamp,
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


async def _queue_one_instance(client, headers: dict[str, str], patient: dict) -> None:
    await _create_consent(client, headers, patient["id"])
    schedule = await _create_schedule(client, headers, patient["id"])
    materialize = await client.post(
        f"{API}/schedules/{schedule['id']}/materialize", headers=headers
    )
    assert materialize.status_code == 200, materialize.text
    result = await client.post(f"{API}/schedules/process-due", headers=headers)
    assert result.json()["eligible_to_send"] >= 1


async def test_webhook_verification_handshake(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    assert headers  # ensure owner login works

    ok = await client.get(
        f"{API}/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-token",
            "hub.challenge": "challenge-123",
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.text == "challenge-123"

    bad = await client.get(
        f"{API}/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "x"},
    )
    assert bad.status_code == 422


async def test_outbound_dispatch_then_inbound_marks_responded(
    client, staff_factory, unique_email
) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    await _queue_one_instance(client, headers, patient)

    dispatched = await client.post(f"{API}/messages/dispatch", headers=headers)
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["sent"] >= 1

    queue = await client.get(f"{API}/instances?status=sent", headers=headers)
    assert queue.json()["total"] >= 1

    conversation = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    assert conversation.status_code == 200, conversation.text
    outbound = conversation.json()["items"]
    assert any(m["direction"] == "outbound" for m in outbound)
    outbound_msg = next(m for m in outbound if m["direction"] == "outbound")
    assert outbound_msg["provider_message_id"].startswith("local-")

    payload = _webhook_payload(
        from_phone=patient["phone_number"],
        message_id="wamid.INBOUND1",
        text="Feeling much better today",
    )
    inbound = await _post_webhook(client, payload)
    assert inbound.status_code == 200, inbound.text
    assert inbound.json()["messages"] == 1

    responded = await client.get(f"{API}/instances?status=responded", headers=headers)
    assert responded.json()["total"] >= 1

    convo2 = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    inbound_msgs = [m for m in convo2.json()["items"] if m["direction"] == "inbound"]
    assert inbound_msgs
    assert inbound_msgs[0]["text_body"] == "Feeling much better today"
    assert inbound_msgs[0]["follow_up_instance_id"] is not None


async def test_inbound_webhook_is_idempotent(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)

    payload = _webhook_payload(
        from_phone=patient["phone_number"], message_id="wamid.DUP1", text="Same message"
    )
    first = await _post_webhook(client, payload)
    assert first.status_code == 200
    assert first.json()["messages"] == 1

    second = await _post_webhook(client, payload)
    assert second.status_code == 200
    assert second.json()["duplicate"] == 1
    assert second.json()["messages"] == 0

    conversation = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    assert conversation.json()["total"] == 1


async def test_unknown_sender_routes_to_exception_queue(
    client, staff_factory, unique_email
) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))

    payload = _webhook_payload(
        from_phone="910000000000", message_id="wamid.UNKNOWN1", text="Hello?"
    )
    response = await _post_webhook(client, payload)
    assert response.status_code == 200, response.text
    assert response.json()["messages"] == 1

    exceptions = await client.get(f"{API}/messages/exceptions?status=open", headers=headers)
    assert exceptions.status_code == 200, exceptions.text
    assert exceptions.json()["total"] >= 1
    item = exceptions.json()["items"][0]
    assert item["reason"] == "unknown_sender"

    resolved = await client.post(
        f"{API}/messages/exceptions/{item['id']}/resolve",
        headers=headers,
        json={"resolved": True, "notes": "Contacted patient to register"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"

    again = await client.post(
        f"{API}/messages/exceptions/{item['id']}/resolve",
        headers=headers,
        json={"resolved": True},
    )
    assert again.status_code == 409


async def test_ambiguous_sender_is_quarantined(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))

    suffix = uuid.uuid4().int % 10**8
    last10 = f"98{suffix:08d}"
    patient_a = await _register(client, headers, phone=f"91{last10}")
    patient_b = await _register(client, headers, phone=f"44{last10}")
    # The sender shares the last ten digits with both patients but exactly
    # matches neither, so the match is genuinely ambiguous.
    sender = f"33{last10}"

    payload = _webhook_payload(
        from_phone=sender, message_id="wamid.AMBIG1", text="Which record am I?"
    )
    response = await _post_webhook(client, payload)
    assert response.status_code == 200, response.text
    assert response.json()["messages"] == 1

    exceptions = await client.get(f"{API}/messages/exceptions?status=open", headers=headers)
    assert exceptions.status_code == 200, exceptions.text
    expected = sorted([patient_a["id"], patient_b["id"]])
    quarantined = [
        i
        for i in exceptions.json()["items"]
        if i["reason"] == "ambiguous_sender"
        and sorted(i["details"]["candidate_patient_ids"]) == expected
    ]
    assert quarantined, exceptions.json()["items"]
    item = quarantined[0]
    assert item["patient_id"] is None

    # The message is not attached to either candidate.
    for patient in (patient_a, patient_b):
        convo = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
        assert convo.json()["total"] == 0


async def test_exact_sender_match_disambiguates_last_ten(
    client, staff_factory, unique_email
) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))

    suffix = uuid.uuid4().int % 10**8
    last10 = f"77{suffix:08d}"
    patient_a = await _register(client, headers, phone=f"91{last10}")
    patient_b = await _register(client, headers, phone=f"44{last10}")

    # The sender exactly matches patient A's normalized number, so the
    # last-ten collision with patient B must not make it ambiguous.
    payload = _webhook_payload(from_phone=f"91{last10}", message_id="wamid.EXACT1", text="It's me")
    response = await _post_webhook(client, payload)
    assert response.status_code == 200, response.text
    assert response.json()["messages"] == 1

    convo = await client.get(f"{API}/patients/{patient_a['id']}/messages", headers=headers)
    assert convo.json()["total"] == 1
    other = await client.get(f"{API}/patients/{patient_b['id']}/messages", headers=headers)
    assert other.json()["total"] == 0

    exceptions = await client.get(f"{API}/messages/exceptions?status=open", headers=headers)
    candidates = {patient_a["id"], patient_b["id"]}
    for item in exceptions.json()["items"]:
        if item["reason"] == "ambiguous_sender":
            assert not candidates & set(item["details"]["candidate_patient_ids"])


async def test_finance_role_cannot_dispatch(client, staff_factory, unique_email) -> None:
    finance = unique_email
    await staff_factory(email=finance, role=StaffRole.FINANCE)
    headers = _headers(await _login(client, finance))
    response = await client.post(f"{API}/messages/dispatch", headers=headers)
    assert response.status_code == 403


async def test_delivery_status_event_updates_outbound(client, staff_factory, unique_email) -> None:
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    await _queue_one_instance(client, headers, patient)
    await client.post(f"{API}/messages/dispatch", headers=headers)

    convo = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    outbound = next(m for m in convo.json()["items"] if m["direction"] == "outbound")
    provider_id = outbound["provider_message_id"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1234567890",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "statuses": [
                                {
                                    "id": provider_id,
                                    "status": "delivered",
                                    "timestamp": "1700000100",
                                    "recipient_id": patient["phone_number"],
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    response = await _post_webhook(client, payload)
    assert response.status_code == 200, response.text
    assert response.json()["statuses"] == 1

    refreshed = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    updated = next(m for m in refreshed.json()["items"] if m["provider_message_id"] == provider_id)
    assert updated["delivery_status"] == "delivered"


async def test_messages_require_authentication(client) -> None:
    assert (await client.get(f"{API}/messages/exceptions")).status_code == 401
    assert (await client.post(f"{API}/messages/dispatch")).status_code == 401
    assert (await client.get(f"{API}/patients/{uuid.uuid4()}/messages")).status_code == 401


async def test_dispatch_skips_instance_when_consent_withdrawn_after_queue(
    client, staff_factory, unique_email
) -> None:
    """A queued instance must be re-checked at send time (FR-010)."""
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    consent = await _create_consent(client, headers, patient["id"])
    schedule = await _create_schedule(client, headers, patient["id"])
    await client.post(f"{API}/schedules/{schedule['id']}/materialize", headers=headers)
    queued = await client.post(f"{API}/schedules/process-due", headers=headers)
    assert queued.json()["eligible_to_send"] >= 1

    # Consent is withdrawn after the message was queued but before dispatch.
    withdrawn = await client.post(
        f"{API}/patients/{patient['id']}/consents/{consent['id']}/withdraw", headers=headers
    )
    assert withdrawn.status_code == 200, withdrawn.text

    dispatched = await client.post(f"{API}/messages/dispatch", headers=headers)
    assert dispatched.status_code == 200, dispatched.text

    conversation = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    assert conversation.json()["total"] == 0

    skipped = await client.get(
        f"{API}/instances?status=skipped&patient_id={patient['id']}", headers=headers
    )
    items = skipped.json()["items"]
    assert items
    assert all(item["skip_reason"] for item in items)


async def test_failed_status_event_reconciles_instance_and_alerts(
    client, staff_factory, unique_email
) -> None:
    """A provider failure must not leave the instance looking delivered (FR-027)."""
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    await _queue_one_instance(client, headers, patient)
    sent = await client.post(f"{API}/messages/dispatch", headers=headers)
    assert sent.json()["sent"] >= 1

    convo = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    outbound = next(m for m in convo.json()["items"] if m["direction"] == "outbound")
    provider_id = outbound["provider_message_id"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1234567890",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "statuses": [
                                {
                                    "id": provider_id,
                                    "status": "failed",
                                    "timestamp": "1700000100",
                                    "recipient_id": patient["phone_number"],
                                    "errors": [{"code": 131026, "title": "Message undeliverable"}],
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    response = await _post_webhook(client, payload)
    assert response.status_code == 200, response.text
    assert response.json()["statuses"] == 1

    failed = await client.get(
        f"{API}/instances?status=failed&patient_id={patient['id']}", headers=headers
    )
    assert failed.json()["total"] >= 1

    alerts = await client.get(
        f"{API}/alerts", headers=headers, params={"patient_id": patient["id"]}
    )
    assert any(a["alert_type"] == "delivery_failure" for a in alerts.json()["items"])


async def test_dispatch_skips_rows_claimed_by_another_worker(
    client, staff_factory, unique_email, session_factory
) -> None:
    """A second dispatcher must not send a row an active dispatcher holds."""
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    await _queue_one_instance(client, headers, patient)

    patient_id = uuid.UUID(patient["id"])
    async with session_factory() as neutralize:
        await neutralize.execute(
            update(FollowUpInstance)
            .where(
                FollowUpInstance.status == FollowUpInstanceStatus.QUEUED,
                FollowUpInstance.patient_id != patient_id,
            )
            .values(status=FollowUpInstanceStatus.SKIPPED)
        )
        await neutralize.commit()

    async with session_factory() as holder:
        locked = (
            (
                await holder.execute(
                    select(FollowUpInstance)
                    .where(
                        FollowUpInstance.patient_id == patient_id,
                        FollowUpInstance.status == FollowUpInstanceStatus.QUEUED,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .first()
        )
        assert locked is not None

        async with session_factory() as other:
            result = await messaging_service.dispatch_outbound(other)
            assert result["scanned"] == 0
            assert result["sent"] == 0
            await other.rollback()

        await holder.rollback()


async def test_concurrent_dispatch_sends_queued_instance_once(
    client, staff_factory, unique_email, session_factory
) -> None:
    """Two overlapping dispatches must produce exactly one outbound message."""
    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    await _queue_one_instance(client, headers, patient)

    patient_id = uuid.UUID(patient["id"])
    async with session_factory() as neutralize:
        await neutralize.execute(
            update(FollowUpInstance)
            .where(
                FollowUpInstance.status == FollowUpInstanceStatus.QUEUED,
                FollowUpInstance.patient_id != patient_id,
            )
            .values(status=FollowUpInstanceStatus.SKIPPED)
        )
        await neutralize.commit()

    responses = await asyncio.gather(
        client.post(f"{API}/messages/dispatch", headers=headers),
        client.post(f"{API}/messages/dispatch", headers=headers),
    )
    assert all(r.status_code == 200 for r in responses)
    assert sum(r.json()["sent"] for r in responses) == 1

    convo = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    outbound = [m for m in convo.json()["items"] if m["direction"] == "outbound"]
    assert len(outbound) == 1


async def test_inbound_ai_runs_off_the_request_path_when_deferred(
    client, staff_factory, unique_email, monkeypatch
) -> None:
    """In deferred mode the webhook must not analyze inline; it enqueues."""
    enqueued: list[uuid.UUID] = []
    monkeypatch.setattr(settings, "ai_processing_mode", "deferred")
    monkeypatch.setattr(
        ai_queue, "enqueue_inbound_analysis", lambda message_id: enqueued.append(message_id)
    )

    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)

    payload = _webhook_payload(
        from_phone=patient["phone_number"], message_id="wamid.DEFER1", text="My BP is 120/80"
    )
    response = await _post_webhook(client, payload)
    assert response.status_code == 200, response.text
    assert response.json()["messages"] == 1
    assert len(enqueued) == 1

    # Nothing was extracted on the request path.
    extractions = await client.get(
        f"{API}/patients/{patient['id']}/ai-extractions", headers=headers
    )
    assert extractions.json()["total"] == 0


async def test_deferred_analysis_helper_persists_extraction_when_row_visible(
    client, staff_factory, unique_email, session_factory, monkeypatch
) -> None:
    """The worker's analysis helper processes a committed inbound message."""
    monkeypatch.setattr(settings, "ai_processing_mode", "deferred")
    monkeypatch.setattr(ai_queue, "enqueue_inbound_analysis", lambda message_id: None)

    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)

    payload = _webhook_payload(
        from_phone=patient["phone_number"],
        message_id="wamid.DEFER2",
        text="Sugar 235 mg/dL after dinner",
    )
    response = await _post_webhook(client, payload)
    assert response.status_code == 200, response.text

    convo = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    message_id = convo.json()["items"][0]["id"]

    # An unknown id reports not-found so the task retries until it commits.
    async with session_factory() as session:
        missing = await ai_service.analyze_message_by_id(session, uuid.uuid4())
        assert missing["found"] is False

    async with session_factory() as session:
        result = await ai_service.analyze_message_by_id(session, uuid.UUID(message_id))
        await session.commit()
    assert result["found"] is True
    assert result["analyzed"] == 1

    extractions = await client.get(
        f"{API}/patients/{patient['id']}/ai-extractions", headers=headers
    )
    assert extractions.json()["total"] == 1


async def test_outside_window_sends_approved_template(
    client, staff_factory, unique_email, monkeypatch
) -> None:
    """Outside the 24h window an approved template must be sent, not free text."""
    monkeypatch.setattr(settings, "whatsapp_enforce_session_window", True)
    captured: dict = {}

    async def _template(_to, name, language="en", body_parameters=None):
        captured["name"] = name
        captured["language"] = language
        captured["params"] = body_parameters
        return whatsapp_client.SendResult(ok=True, provider_message_id="template-1", dry_run=True)

    monkeypatch.setattr(whatsapp_client, "send_template_message", _template)

    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    template = await _create_template(client, headers, body="Hi {{name}}, time to check in.")
    await _queue_dispatchable_instance(
        client, headers, patient["id"], message_template_id=template["id"]
    )

    dispatched = await client.post(f"{API}/messages/dispatch", headers=headers)
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["sent"] >= 1
    assert captured["name"] == "daily_check_in"
    assert captured["language"] == "en"
    assert captured["params"] == ["Messaging"]

    convo = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    outbound = next(m for m in convo.json()["items"] if m["direction"] == "outbound")
    assert outbound["message_type"] == "template"
    assert outbound["template_code"] == template["code"]
    assert outbound["delivery_status"] == "sent"


async def test_outside_window_without_template_fails_cleanly(
    client, staff_factory, unique_email, monkeypatch
) -> None:
    """With no approved template, dispatch must fail loudly rather than send text."""
    monkeypatch.setattr(settings, "whatsapp_enforce_session_window", True)

    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)
    await _queue_dispatchable_instance(client, headers, patient["id"])

    dispatched = await client.post(f"{API}/messages/dispatch", headers=headers)
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["failed"] >= 1

    convo = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    outbound = next(m for m in convo.json()["items"] if m["direction"] == "outbound")
    assert outbound["delivery_status"] == "failed"
    assert outbound["error_code"] == "template_required"

    alerts = await client.get(
        f"{API}/alerts", headers=headers, params={"patient_id": patient["id"]}
    )
    assert any(a["alert_type"] == "delivery_failure" for a in alerts.json()["items"])


async def test_inside_window_uses_free_form_text(
    client, staff_factory, unique_email, monkeypatch
) -> None:
    """A recent inbound message opens the window, so free-form text is allowed."""
    monkeypatch.setattr(settings, "whatsapp_enforce_session_window", True)
    text_calls: list[str] = []
    template_calls: list[str] = []

    async def _text(_to, body):
        text_calls.append(body)
        return whatsapp_client.SendResult(ok=True, provider_message_id="text-1", dry_run=True)

    async def _template(_to, name, language="en", body_parameters=None):
        template_calls.append(name)
        return whatsapp_client.SendResult(ok=True, provider_message_id="template-1", dry_run=True)

    monkeypatch.setattr(whatsapp_client, "send_text_message", _text)
    monkeypatch.setattr(whatsapp_client, "send_template_message", _template)

    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    patient = await _register(client, headers)

    # A fresh inbound message (current timestamp) keeps the session window open.
    fresh = str(int(datetime.now(UTC).timestamp()))
    inbound = await _post_webhook(
        client,
        _webhook_payload(
            from_phone=patient["phone_number"],
            message_id="wamid.WINDOW1",
            text="Hi, checking in",
            timestamp=fresh,
        ),
    )
    assert inbound.status_code == 200, inbound.text
    assert inbound.json()["messages"] == 1

    template = await _create_template(client, headers)
    await _queue_dispatchable_instance(
        client, headers, patient["id"], message_template_id=template["id"]
    )

    dispatched = await client.post(f"{API}/messages/dispatch", headers=headers)
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["sent"] >= 1
    assert text_calls and not template_calls

    convo = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    outbound = next(m for m in convo.json()["items"] if m["direction"] == "outbound")
    assert outbound["message_type"] == "text"


async def test_clinic_wide_message_list_filters(
    client, staff_factory, unique_email, session_factory
) -> None:
    """GET /messages lists WhatsApp traffic clinic-wide with transport filters."""
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))
    patient = await _register(client, headers)
    patient_id = uuid.UUID(patient["id"])

    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add_all(
            [
                WhatsAppMessage(
                    patient_id=patient_id,
                    direction=MessageDirection.OUTBOUND,
                    message_type=MessageType.TEXT,
                    text_body="Breakfast check-in",
                    delivery_status=DeliveryStatus.SENT,
                    processing_status=MessageProcessingStatus.PROCESSED,
                    sent_at=now,
                ),
                WhatsAppMessage(
                    patient_id=patient_id,
                    direction=MessageDirection.INBOUND,
                    message_type=MessageType.TEXT,
                    text_body="I had poha and tea",
                    delivery_status=None,
                    processing_status=MessageProcessingStatus.PROCESSED,
                    received_at=now,
                ),
                WhatsAppMessage(
                    patient_id=patient_id,
                    direction=MessageDirection.OUTBOUND,
                    message_type=MessageType.TEXT,
                    text_body="Broken number",
                    delivery_status=DeliveryStatus.FAILED,
                    processing_status=MessageProcessingStatus.PROCESSED,
                    sent_at=now,
                ),
            ]
        )
        await session.commit()

    all_messages = await client.get(f"{API}/messages", headers=headers, params={"size": 50})
    assert all_messages.status_code == 200, all_messages.text
    assert any(item["text_body"] == "I had poha and tea" for item in all_messages.json()["items"])

    failed = await client.get(
        f"{API}/messages",
        headers=headers,
        params={
            "direction": "outbound",
            "delivery_status": "failed",
            "patient_id": patient["id"],
            "size": 50,
        },
    )
    assert failed.status_code == 200, failed.text
    failed_items = failed.json()["items"]
    assert len(failed_items) == 1
    assert failed_items[0]["text_body"] == "Broken number"

    inbound = await client.get(
        f"{API}/messages", headers=headers, params={"direction": "inbound", "size": 50}
    )
    assert any(m["direction"] == "inbound" for m in inbound.json()["items"])

    searched = await client.get(
        f"{API}/messages", headers=headers, params={"search": "poha", "size": 50}
    )
    assert searched.json()["total"] >= 1


async def test_manual_reply_within_session_window_sends_free_text(
    client, staff_factory, unique_email, monkeypatch
) -> None:
    """A free-form reply is allowed inside the 24h session window."""
    monkeypatch.setattr(settings, "whatsapp_enforce_session_window", True)
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))
    patient = await _register(client, headers)

    payload = _webhook_payload(
        from_phone=patient["phone_number"],
        message_id="wamid.SESSION1",
        text="Hi, need an update",
        timestamp=str(int(datetime.now(UTC).timestamp())),
    )
    inbound = await _post_webhook(client, payload)
    assert inbound.status_code == 200, inbound.text
    assert inbound.json()["messages"] == 1

    response = await client.post(
        f"{API}/messages/reply",
        headers=headers,
        json={"patient_id": patient["id"], "body": "Please drink a glass of water."},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["direction"] == "outbound"
    assert body["message_type"] == "text"
    assert body["text_body"] == "Please drink a glass of water."
    assert body["delivery_status"] == "sent"

    convo = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    outbound = [m for m in convo.json()["items"] if m["direction"] == "outbound"]
    assert any(m["text_body"] == "Please drink a glass of water." for m in outbound)
    assert outbound[0]["follow_up_instance_id"] is None


async def test_manual_reply_outside_window_blocks_free_text_and_prompts_template(
    client, staff_factory, unique_email, monkeypatch
) -> None:
    """Outside the window a free-form reply is blocked with a template prompt."""
    monkeypatch.setattr(settings, "whatsapp_enforce_session_window", True)
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))
    patient = await _register(client, headers)

    response = await client.post(
        f"{API}/messages/reply",
        headers=headers,
        json={"patient_id": patient["id"], "body": "Free text outside the window"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "session_window_required"
    assert "template" in response.json()["error"]["message"].lower()

    convo = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    assert not any(m["direction"] == "outbound" for m in convo.json()["items"])


async def test_manual_reply_outside_window_sends_approved_template(
    client, staff_factory, unique_email, monkeypatch
) -> None:
    """Outside the window an explicit approved template is the compliant path."""
    monkeypatch.setattr(settings, "whatsapp_enforce_session_window", True)
    captured: dict = {}

    async def _template(_to, name, language="en", body_parameters=None):
        captured["name"] = name
        captured["language"] = language
        captured["params"] = body_parameters
        return whatsapp_client.SendResult(ok=True, provider_message_id="tpl-reply-1", dry_run=True)

    monkeypatch.setattr(whatsapp_client, "send_template_message", _template)
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))
    patient = await _register(client, headers)
    template = await _create_template(client, headers, body="Hi {{name}}, time to check in.")

    response = await client.post(
        f"{API}/messages/reply",
        headers=headers,
        json={"patient_id": patient["id"], "template_id": template["id"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message_type"] == "template"
    assert body["template_code"] == template["code"]
    assert body["delivery_status"] == "sent"
    assert captured["name"] == "daily_check_in"
    assert captured["params"] == ["Messaging"]


async def test_manual_reply_rejects_unapproved_template(
    client, staff_factory, unique_email, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "whatsapp_enforce_session_window", True)
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))
    patient = await _register(client, headers)
    template = await _create_template(client, headers, body="Hi {{name}}", approved=False)

    response = await client.post(
        f"{API}/messages/reply",
        headers=headers,
        json={"patient_id": patient["id"], "template_id": template["id"]},
    )
    assert response.status_code == 422, response.text
    assert "approved" in response.json()["error"]["message"].lower()


async def test_manual_reply_requires_body_without_template(
    client, staff_factory, unique_email
) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))
    patient = await _register(client, headers)

    response = await client.post(
        f"{API}/messages/reply",
        headers=headers,
        json={"patient_id": patient["id"], "body": "   "},
    )
    assert response.status_code == 422, response.text
