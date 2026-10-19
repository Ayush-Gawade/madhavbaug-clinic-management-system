"""Tests for the AI auto-reply engine, its medical guardrails and doctor paging.

Unit tests here are pure (no database, no network). Integration tests are marked
``integration`` and run against PostgreSQL with WhatsApp pinned to dry-run and AI
pinned offline by ``conftest``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models.ai import AIExtraction, AIExtractionModality, AIExtractionStatus
from app.models.alerts import Alert, AlertPriority, AlertStatus, AlertType
from app.models.auto_reply import AutoReply, AutoReplyMode, AutoReplyStatus
from app.models.clinical import Observation, ObservationSource, Patient
from app.models.messaging import (
    DeliveryStatus,
    MessageDeliveryEvent,
    MessageDirection,
    MessageProcessingStatus,
    MessageType,
    WhatsAppMessage,
)
from app.models.settings import AppSetting
from app.services import ai as ai_service
from app.services import auto_reply as auto_reply_service
from app.services import auto_reply_queue
from app.services import settings as settings_service
from app.services import whatsapp as whatsapp_client

# -- Pure unit tests ----------------------------------------------------------


def test_sanitize_caps_reply_length() -> None:
    long = "Sanket, your reading was noted and the care team will follow up. " * 10
    cleaned = auto_reply_service.sanitize(long)
    assert len(cleaned) <= auto_reply_service.MAX_REPLY_CHARS
    assert "\n" not in cleaned


def test_sanitize_trims_on_a_word_boundary() -> None:
    assert auto_reply_service.sanitize("word " * 100).endswith("word")


def test_sanitize_rejects_blank_output() -> None:
    with pytest.raises(auto_reply_service.AutoReplyError):
        auto_reply_service.sanitize("   \n  ")


def test_sanitize_strips_wrapping_quotes() -> None:
    assert auto_reply_service.sanitize('"Sanket, noted."') == "Sanket, noted."


def test_system_prompt_enforces_medical_guardrails() -> None:
    prompt = auto_reply_service._AUTO_REPLY_SYSTEM_PROMPT
    for guardrail in (
        "Use ONLY the facts in the task payload",
        "Never invent",
        "You are not a doctor",
        "never suggest starting, stopping, changing or dosing",
        "do not reassure",
        "the care team has been informed",
        "Never say you are an AI",
        "delay or avoid seeking medical care",
        "240 characters maximum",
        "Output the message text only",
    ):
        assert guardrail in prompt, guardrail


def test_build_task_includes_facts_history_and_message() -> None:
    decision = auto_reply_service.ReplyDecision(
        mode=AutoReplyMode.OUT_OF_RANGE_READING,
        patient_first_name="Sanket",
        overall_status="urgent",
        urgent=True,
        readings=[{"type": "blood_glucose", "value": 52.0, "unit": "mg/dL", "context": None}],
        rule_alerts=[
            {
                "metric": "blood_glucose",
                "value": 52.0,
                "unit": "mg/dL",
                "priority": "urgent",
                "reason": "Glucose 52 mg/dL is below the configured urgent threshold.",
            }
        ],
    )
    task = auto_reply_service.build_task(
        decision=decision,
        patient_message="sugar 52 mg/dL",
        conversation=[{"from": "clinic", "text": "How are you today?"}],
    )

    assert '"overall_status": "urgent"' in task
    assert "Sanket" in task
    assert "Glucose 52 mg/dL is below" in task
    assert "sugar 52 mg/dL" in task
    assert "How are you today?" in task


def test_doctor_message_is_personalised_and_short() -> None:
    patient = Patient(internal_id="MB-TEST1", full_name="Sanket Sonwane")
    alert = Alert(
        patient_id=uuid.uuid4(),
        reason="Glucose 52 mg/dL is below the configured urgent threshold of 60 mg/dL.",
    )
    body = auto_reply_service.doctor_message(patient, [alert, alert, alert])
    assert body.startswith("Urgent reading from Sanket:")
    assert "Glucose 52 mg/dL" in body
    assert "+1 more" in body
    assert len(body) <= 600


# -- Integration helpers ------------------------------------------------------


async def _patient(session: AsyncSession) -> Patient:
    patient = Patient(
        internal_id=f"MB-T{uuid.uuid4().hex[:8].upper()}",
        full_name="Sanket Sonwane",
        phone_number="+918468902367",
    )
    session.add(patient)
    await session.flush()
    return patient


async def _inbound(session: AsyncSession, patient: Patient, *, body: str) -> WhatsAppMessage:
    message = WhatsAppMessage(
        patient_id=patient.id,
        direction=MessageDirection.INBOUND,
        message_type=MessageType.TEXT,
        from_phone="+918468902367",
        text_body=body,
        processing_status=MessageProcessingStatus.PROCESSED,
        received_at=datetime.now(UTC),
    )
    session.add(message)
    await session.flush()
    return message


async def _extraction(
    session: AsyncSession,
    *,
    patient: Patient,
    message: WhatsAppMessage,
    needs_clarification: bool = False,
    question: str | None = None,
) -> AIExtraction:
    extraction = AIExtraction(
        patient_id=patient.id,
        message_id=message.id,
        modality=AIExtractionModality.TEXT,
        model="heuristic",
        prompt_version="extraction-v2",
        status=(
            AIExtractionStatus.NEEDS_CLARIFICATION
            if needs_clarification
            else AIExtractionStatus.SUCCEEDED
        ),
        intent="observation_report",
        confidence=Decimal("0.9"),
        needs_clarification=needs_clarification,
        clarification_question=question,
        observations_created=0,
    )
    session.add(extraction)
    await session.flush()
    return extraction


async def _observe(
    session: AsyncSession,
    *,
    patient: Patient,
    extraction: AIExtraction,
    value: str = "52",
) -> Observation:
    observation = Observation(
        patient_id=patient.id,
        ai_extraction_id=extraction.id,
        observation_type="blood_glucose",
        value=Decimal(value),
        unit="mg/dL",
        observed_at=datetime.now(UTC),
        source=ObservationSource.WHATSAPP,
    )
    session.add(observation)
    await session.flush()
    return observation


async def _alert(
    session: AsyncSession, *, patient: Patient, observation: Observation, priority: AlertPriority
) -> Alert:
    alert = Alert(
        patient_id=patient.id,
        observation_id=observation.id,
        alert_type=AlertType.THRESHOLD,
        metric="blood_glucose",
        value=Decimal("52"),
        unit="mg/dL",
        priority=priority,
        status=AlertStatus.OPEN,
        reason="Glucose 52 mg/dL is below the configured urgent threshold of 60 mg/dL.",
    )
    session.add(alert)
    await session.flush()
    return alert


@pytest.fixture
async def reset_settings(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """The schema is session-scoped and shared; start a test unconfigured.

    Every integration test in this suite writes to the same database, so a test
    that asserts "the feature is off by default" must not inherit the row an
    earlier test turned on.
    """
    async with session_factory() as session:
        await session.execute(delete(AppSetting))
        await session.commit()


@pytest.fixture
def enqueued(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Record Celery dispatches instead of touching a broker."""
    calls = SimpleNamespace(replies=[], notifications=[])
    monkeypatch.setattr(auto_reply_queue, "enqueue_auto_reply", calls.replies.append)
    monkeypatch.setattr(auto_reply_queue, "enqueue_doctor_notification", calls.notifications.append)
    return calls


@pytest.fixture
def fake_generation(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stub the model call so tests never spend a token."""
    calls: list[str] = []

    async def _generate(task: str) -> str:
        calls.append(task)
        return "Sanket, noted. The care team will follow up shortly."

    monkeypatch.setattr(auto_reply_service, "generate", _generate)
    return calls


@pytest.fixture
def recorded_sends(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Capture WhatsApp sends while keeping the dry-run transport."""
    sends: list[tuple[str, str]] = []
    real_send = whatsapp_client.send_text_message

    async def _record(to_phone: str, body: str):
        sends.append((to_phone, body))
        return await real_send(to_phone, body)

    monkeypatch.setattr(whatsapp_client, "send_text_message", _record)
    return sends


async def _enable_auto_reply(session: AsyncSession) -> None:
    await settings_service.set_setting(session, settings_service.SETTING_AI_AUTOREPLY_ENABLED, True)


async def _outbound_count(session: AsyncSession, patient_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(WhatsAppMessage)
        .where(
            WhatsAppMessage.patient_id == patient_id,
            WhatsAppMessage.direction == MessageDirection.OUTBOUND,
        )
    )
    return int((await session.execute(stmt)).scalar_one())


# -- Decision table -----------------------------------------------------------


@pytest.mark.integration
async def test_decide_returns_safe_mode_for_in_range_reading(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        patient = await _patient(session)
        message = await _inbound(session, patient, body="sugar 102 mg/dL")
        extraction = await _extraction(session, patient=patient, message=message)
        await _observe(session, patient=patient, extraction=extraction, value="102")

        decision = await auto_reply_service.decide(session, patient=patient, extraction=extraction)

    assert decision is not None
    assert decision.mode is AutoReplyMode.SAFE_READING
    assert decision.overall_status == "within_safe_range"
    assert decision.urgent is False
    assert decision.patient_first_name == "Sanket"


@pytest.mark.integration
async def test_decide_returns_out_of_range_mode_for_a_routine_alert(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        patient = await _patient(session)
        message = await _inbound(session, patient, body="sugar 52 mg/dL")
        extraction = await _extraction(session, patient=patient, message=message)
        observation = await _observe(session, patient=patient, extraction=extraction)
        await _alert(
            session, patient=patient, observation=observation, priority=AlertPriority.ROUTINE
        )

        decision = await auto_reply_service.decide(session, patient=patient, extraction=extraction)

    assert decision is not None
    assert decision.mode is AutoReplyMode.OUT_OF_RANGE_READING
    assert decision.overall_status == "out_of_range"
    assert decision.urgent is False
    assert decision.rule_alerts[0]["reason"].startswith("Glucose 52 mg/dL")


@pytest.mark.integration
async def test_decide_flags_an_urgent_reading(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        patient = await _patient(session)
        message = await _inbound(session, patient, body="sugar 52 mg/dL")
        extraction = await _extraction(session, patient=patient, message=message)
        observation = await _observe(session, patient=patient, extraction=extraction)
        await _alert(
            session, patient=patient, observation=observation, priority=AlertPriority.URGENT
        )

        decision = await auto_reply_service.decide(session, patient=patient, extraction=extraction)

    assert decision is not None
    assert decision.urgent is True
    assert decision.overall_status == "urgent"


@pytest.mark.integration
async def test_decide_asks_for_clarification_when_there_is_no_reading(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        patient = await _patient(session)
        message = await _inbound(session, patient, body="my sugar was high today")
        extraction = await _extraction(
            session,
            patient=patient,
            message=message,
            needs_clarification=True,
            question="Please confirm the units (mg/dL).",
        )

        decision = await auto_reply_service.decide(session, patient=patient, extraction=extraction)

    assert decision is not None
    assert decision.mode is AutoReplyMode.CLARIFICATION
    assert decision.clarifying_question == "Please confirm the units (mg/dL)."


@pytest.mark.integration
async def test_decide_stays_silent_without_a_reading_or_question(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        patient = await _patient(session)
        message = await _inbound(session, patient, body="Hello doctor, good morning")
        extraction = await _extraction(session, patient=patient, message=message)

        decision = await auto_reply_service.decide(session, patient=patient, extraction=extraction)

    assert decision is None


# -- Delivery -----------------------------------------------------------------


@pytest.mark.integration
async def test_nothing_is_sent_while_the_toggle_is_off(
    session_factory: async_sessionmaker[AsyncSession],
    reset_settings: None,
) -> None:
    async with session_factory() as session:
        patient = await _patient(session)
        patient_id = patient.id
        message = await _inbound(session, patient, body="sugar 102 mg/dL")
        message_id = message.id
        extraction = await _extraction(session, patient=patient, message=message)
        await _observe(session, patient=patient, extraction=extraction, value="102")

        result = await auto_reply_service.generate_and_send(session, source_message_id=message_id)
        await session.commit()

        assert result["reason"] == "auto_reply_disabled"
        assert result["sent"] is False
        stored = (
            await session.execute(
                select(func.count())
                .select_from(AutoReply)
                .where(AutoReply.patient_id == patient_id)
            )
        ).scalar_one()
        assert stored == 0
        assert await _outbound_count(session, patient_id) == 0


@pytest.mark.integration
async def test_reply_is_generated_sent_and_recorded_exactly_once(
    session_factory: async_sessionmaker[AsyncSession],
    enqueued: SimpleNamespace,
    fake_generation: list[str],
) -> None:
    async with session_factory() as session:
        patient = await _patient(session)
        patient_id = patient.id
        message = await _inbound(session, patient, body="sugar 102 mg/dL")
        message_id = message.id
        extraction = await _extraction(session, patient=patient, message=message)
        await _observe(session, patient=patient, extraction=extraction, value="102")
        await _enable_auto_reply(session)

        first = await auto_reply_service.generate_and_send(session, source_message_id=message_id)
        await session.commit()

        assert first["sent"] is True
        assert first["mode"] == AutoReplyMode.SAFE_READING.value
        assert len(fake_generation) == 1
        assert "sugar 102 mg/dL" in fake_generation[0]
        assert await _outbound_count(session, patient_id) == 1

        row = await session.get(AutoReply, uuid.UUID(first["auto_reply_id"]))
        assert row is not None
        assert row.status is AutoReplyStatus.SENT
        assert row.reply_message_id is not None
        assert row.generated_text is not None
        assert row.prompt_version == auto_reply_service.AUTO_REPLY_PROMPT_VERSION

        # A retried task must never message the patient twice.
        second = await auto_reply_service.generate_and_send(session, source_message_id=message_id)
        await session.commit()

        assert second["reason"] == "already_recorded"
        assert len(fake_generation) == 1
        assert await _outbound_count(session, patient_id) == 1


@pytest.mark.integration
async def test_generation_failure_is_recorded_not_raised(
    session_factory: async_sessionmaker[AsyncSession],
    enqueued: SimpleNamespace,
) -> None:
    async with session_factory() as session:
        patient = await _patient(session)
        patient_id = patient.id
        message = await _inbound(session, patient, body="sugar 52 mg/dL")
        message_id = message.id
        extraction = await _extraction(session, patient=patient, message=message)
        await _observe(session, patient=patient, extraction=extraction)
        await _enable_auto_reply(session)

        # ``generate`` is left real: with AI offline it must refuse rather than
        # fall back to an unguarded template.
        result = await auto_reply_service.generate_and_send(session, source_message_id=message_id)
        await session.commit()

        assert result["sent"] is False
        assert result["reason"] == "generation_failed"

        row = await session.get(AutoReply, uuid.UUID(result["auto_reply_id"]))
        assert row is not None
        assert row.status is AutoReplyStatus.FAILED
        assert row.error_message is not None
        assert "AI generation" in row.error_message
        assert await _outbound_count(session, patient_id) == 0


@pytest.mark.integration
async def test_second_reading_within_the_cooldown_is_suppressed(
    session_factory: async_sessionmaker[AsyncSession],
    enqueued: SimpleNamespace,
    fake_generation: list[str],
) -> None:
    async with session_factory() as session:
        patient = await _patient(session)
        patient_id = patient.id
        first_message = await _inbound(session, patient, body="sugar 102 mg/dL")
        first_id = first_message.id
        first_extraction = await _extraction(session, patient=patient, message=first_message)
        await _observe(session, patient=patient, extraction=first_extraction, value="102")
        second_message = await _inbound(session, patient, body="bp 120/80")
        second_id = second_message.id
        second_extraction = await _extraction(session, patient=patient, message=second_message)
        await _observe(session, patient=patient, extraction=second_extraction, value="120")
        await _enable_auto_reply(session)

        first = await auto_reply_service.generate_and_send(session, source_message_id=first_id)
        await session.commit()
        second = await auto_reply_service.generate_and_send(session, source_message_id=second_id)
        await session.commit()

        assert first["sent"] is True
        assert second["reason"] == "cooldown"

        row = await session.get(AutoReply, uuid.UUID(second["auto_reply_id"]))
        assert row is not None
        assert row.status is AutoReplyStatus.SUPPRESSED
        assert len(fake_generation) == 1
        assert await _outbound_count(session, patient_id) == 1


@pytest.mark.integration
async def test_urgent_reading_pages_the_doctor_exactly_once(
    session_factory: async_sessionmaker[AsyncSession],
    enqueued: SimpleNamespace,
    fake_generation: list[str],
    recorded_sends: list[tuple[str, str]],
) -> None:
    async with session_factory() as session:
        patient = await _patient(session)
        message = await _inbound(session, patient, body="sugar 52 mg/dL")
        message_id = message.id
        extraction = await _extraction(session, patient=patient, message=message)
        observation = await _observe(session, patient=patient, extraction=extraction)
        await _alert(
            session, patient=patient, observation=observation, priority=AlertPriority.URGENT
        )
        await _enable_auto_reply(session)

        result = await auto_reply_service.generate_and_send(session, source_message_id=message_id)
        await session.commit()

        assert result["sent"] is True
        assert len(enqueued.notifications) == 1

        reply_id = uuid.UUID(result["auto_reply_id"])
        row = await session.get(AutoReply, reply_id)
        assert row is not None
        first = await auto_reply_service.notify_doctor(session, auto_reply_id=reply_id)
        await session.commit()
        second = await auto_reply_service.notify_doctor(session, auto_reply_id=reply_id)
        await session.commit()

    assert first["notified"] is True
    assert second["reason"] == "already_notified"

    # ``recorded_sends`` sits on the shared WhatsApp client, so it also caught
    # the patient-facing reply; the two must not be confused.
    doctor_sends = [item for item in recorded_sends if item[0] == "+919359883349"]
    patient_sends = [item for item in recorded_sends if item[0] != "+919359883349"]
    assert len(doctor_sends) == 1
    assert len(patient_sends) == 1
    _, body = doctor_sends[0]
    assert body.startswith("Urgent reading from Sanket:")
    assert patient_sends[0][1] == row.generated_text


@pytest.mark.integration
async def test_doctor_page_is_recorded_as_an_outbound_message(
    session_factory: async_sessionmaker[AsyncSession],
    enqueued: SimpleNamespace,
    fake_generation: list[str],
) -> None:
    """A page that leaves no row is invisible to the clinic.

    Regression: the page used to go straight out through the transport and set
    ``doctor_notified_at`` without ever writing a message row, so a clinician
    looking at the message log saw no evidence the doctor had been warned.
    """
    async with session_factory() as session:
        patient = await _patient(session)
        message = await _inbound(session, patient, body="sugar 52 mg/dL")
        extraction = await _extraction(session, patient=patient, message=message)
        observation = await _observe(session, patient=patient, extraction=extraction)
        await _alert(
            session, patient=patient, observation=observation, priority=AlertPriority.URGENT
        )
        await _enable_auto_reply(session)

        result = await auto_reply_service.generate_and_send(session, source_message_id=message.id)
        await session.commit()
        await auto_reply_service.notify_doctor(
            session, auto_reply_id=uuid.UUID(result["auto_reply_id"])
        )
        await session.commit()

        # Scoped by body: the shared schema also holds follow-ups addressed to
        # the same number from earlier tests.
        page = (
            (
                await session.execute(
                    select(WhatsAppMessage).where(
                        WhatsAppMessage.to_phone == "+919359883349",
                        WhatsAppMessage.text_body.like("Urgent reading from%"),
                    )
                )
            )
            .scalars()
            .first()
        )

        assert page is not None
        assert page.direction is MessageDirection.OUTBOUND
        assert page.delivery_status is DeliveryStatus.SENT
        # No patient_id: attaching the escalation to the patient would feed this
        # internal text back to the model as patient-facing conversation.
        assert page.patient_id is None

        event = (
            (
                await session.execute(
                    select(MessageDeliveryEvent).where(MessageDeliveryEvent.message_id == page.id)
                )
            )
            .scalars()
            .first()
        )
        assert event is not None
        assert event.payload["kind"] == "doctor_notification"


@pytest.mark.integration
async def test_doctor_is_not_paged_without_an_urgent_reading(
    session_factory: async_sessionmaker[AsyncSession],
    fake_generation: list[str],
    recorded_sends: list[tuple[str, str]],
) -> None:
    async with session_factory() as session:
        patient = await _patient(session)
        message = await _inbound(session, patient, body="sugar 102 mg/dL")
        extraction = await _extraction(session, patient=patient, message=message)
        await _observe(session, patient=patient, extraction=extraction, value="102")

        reply = AutoReply(
            source_message_id=message.id,
            patient_id=patient.id,
            mode=AutoReplyMode.SAFE_READING,
            status=AutoReplyStatus.SENT,
            model="gpt-4o-mini",
            prompt_version=auto_reply_service.AUTO_REPLY_PROMPT_VERSION,
        )
        session.add(reply)
        await session.flush()

        outcome = await auto_reply_service.notify_doctor(session, auto_reply_id=reply.id)

    assert outcome["reason"] == "no_urgent_alert"
    assert recorded_sends == []


# -- Enqueue hook -------------------------------------------------------------


@pytest.mark.integration
async def test_analysis_enqueues_a_reply_only_when_the_feature_is_on(
    session_factory: async_sessionmaker[AsyncSession],
    enqueued: SimpleNamespace,
    reset_settings: None,
) -> None:
    async with session_factory() as session:
        patient = await _patient(session)
        message = await _inbound(session, patient, body="sugar 102 mg/dL")
        message_id = message.id

        await ai_service.analyze_inbound(session, message, patient, None)
        assert enqueued.replies == []

        await _enable_auto_reply(session)
        await ai_service.analyze_inbound(session, message, patient, None)
        await session.commit()

    assert enqueued.replies == [message_id]


async def test_generation_is_refused_without_an_ai_key() -> None:
    """No key means no reply — a template fallback would be unguarded prose."""
    assert settings.ai_enabled is False
    assert settings.openai_api_key == ""
    with pytest.raises(auto_reply_service.AutoReplyError):
        await auto_reply_service.generate("Write a reply.")
