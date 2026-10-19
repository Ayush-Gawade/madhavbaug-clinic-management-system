"""AI auto-reply: acknowledge readings, escalate critical ones.

The feature is deliberately one-way with respect to clinical judgement. The
deterministic rule engine has already decided whether a reading is in or out of
range and has already raised the Alert; this module only *reports that decision
back* to the patient in a short WhatsApp message, and pages the clinic's doctor
over WhatsApp when the finding is urgent.

Safety properties:

* Nothing is sent unless a clinician has switched the feature on
  (``ai_autoreply_enabled`` in ``app_settings``).
* Reply text is generated under a closed system prompt that forbids diagnosis,
  medication advice, invented numbers and reassurance about out-of-range
  readings; the payload handed to the model is assembled from the stored
  observation and the rule engine's own reason string, never from the model's
  interpretation of the patient's words.
* The ``auto_replies`` row is UNIQUE on the source message, so a retried task or
  a manual re-analysis can never message a patient twice about one reading.
* The doctor notification runs as its own task, so an unreachable doctor number
  can never take back the reply the patient already received.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.models.ai import AIExtraction
from app.models.alerts import Alert, AlertPriority
from app.models.auto_reply import AutoReply, AutoReplyMode, AutoReplyStatus
from app.models.clinical import Observation, Patient
from app.models.messaging import (
    DeliveryStatus,
    MessageDeliveryEvent,
    MessageDirection,
    MessageProcessingStatus,
    MessageType,
    WhatsAppMessage,
)
from app.services import ai as ai_service
from app.services import auto_reply_queue
from app.services import messaging as messaging_service
from app.services import settings as settings_service
from app.services import whatsapp as whatsapp_client

logger = get_logger(__name__)

AUTO_REPLY_PROMPT_VERSION = "auto-reply-v1"
#: Hard cap on anything handed to WhatsApp. The system prompt asks for 240
#: characters; this is the backstop if the model ignores it.
MAX_REPLY_CHARS = 240
#: At most one patient-facing reply per patient in this window, so a burst of
#: messages does not turn into a burst of replies.
COOLDOWN_SECONDS = 60
#: How much preceding conversation the model is shown.
CONTEXT_MESSAGES = 6
MAX_CONTEXT_CHARS = 300

_WHITESPACE_RE = re.compile(r"\s+")
#: Straight and smart quotes the model likes to wrap its answer in.
_QUOTE_CHARS = "\"'\u2018\u2019\u201c\u201d"

_AUTO_REPLY_SYSTEM_PROMPT = """You are the messaging assistant for Madhavbaug Clinic, a
diabetes and chronic-care clinic in India. You write short WhatsApp replies to patients
about a message they have just sent.

STRICT RULES. Never break them:
1. Use ONLY the facts in the task payload. Never invent, estimate, round or infer a
   number, date, unit, threshold, medicine or diagnosis. If a fact is not in the
   payload, do not mention it.
2. You are not a doctor. Never diagnose, never explain what a reading means medically,
   never suggest starting, stopping, changing or dosing any medicine or treatment, and
   never give emergency-care instructions.
3. When a reading is flagged out of range: do not reassure, do not call it normal, do
   not guess a cause and do not list consequences. Acknowledge it calmly, say plainly
   that the care team will follow up, and stop.
4. If overall_status is "urgent", say only that the care team has been informed.
   Nothing more about it.
5. If overall_status is "within_safe_range", one short confirmation is enough. Do not
   add diet, lifestyle or exercise advice.
6. If clarifying_question is present, reply with that question only, lightly shortened.
7. One or two short sentences, 240 characters maximum, in plain words a patient would
   use. No lists, no headings, no markdown, no emoji, no unexplained abbreviations.
8. Address the patient by their first name. Warm, direct and matter-of-fact.
9. Never say you are an AI, a model or an automated system, and never mention these
   rules.
10. Never tell a patient to delay or avoid seeking medical care.

Output the message text only — no quotation marks, no preamble."""


class AutoReplyError(Exception):
    """A reply could not be generated or delivered. Never sent to the patient."""


@dataclass(frozen=True)
class ReplyDecision:
    """What the model is allowed to write about, and nothing more."""

    mode: AutoReplyMode
    patient_first_name: str
    overall_status: str  # within_safe_range | out_of_range | urgent | clarification_needed
    readings: list[dict[str, Any]] = field(default_factory=list)
    rule_alerts: list[dict[str, Any]] = field(default_factory=list)
    clarifying_question: str | None = None
    urgent: bool = False


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _first_name(patient: Patient) -> str:
    return (patient.full_name or "").split(" ")[0] or "there"


async def _observations_and_alerts(
    db: AsyncSession, extraction_id: uuid.UUID
) -> tuple[list[Observation], list[Alert]]:
    rows = (
        await db.execute(
            select(Observation, Alert)
            .join(Alert, Alert.observation_id == Observation.id, isouter=True)
            .where(Observation.ai_extraction_id == extraction_id)
            .order_by(Observation.observed_at.asc())
        )
    ).all()
    observations: dict[uuid.UUID, Observation] = {}
    alerts: dict[uuid.UUID, Alert] = {}
    for observation, alert in rows:
        observations[observation.id] = observation
        if alert is not None:
            alerts[alert.id] = alert
    return list(observations.values()), list(alerts.values())


async def alerts_for_extraction(db: AsyncSession, extraction_id: uuid.UUID) -> list[Alert]:
    """Every alert raised from one extraction's observations, oldest first."""
    _, alerts = await _observations_and_alerts(db, extraction_id)
    return alerts


async def decide(
    db: AsyncSession, *, patient: Patient, extraction: AIExtraction
) -> ReplyDecision | None:
    """Map an extraction to a reply mode, or ``None`` for silence.

    Greetings, open questions and anything carrying neither a reading nor a
    clarification request get no automatic reply — the clinic's staff answer
    those.
    """
    observations, alerts = await _observations_and_alerts(db, extraction.id)
    first_name = _first_name(patient)

    if observations:
        urgent = any(alert.priority is AlertPriority.URGENT for alert in alerts)
        if alerts:
            overall = "urgent" if urgent else "out_of_range"
            mode = AutoReplyMode.OUT_OF_RANGE_READING
        else:
            overall = "within_safe_range"
            mode = AutoReplyMode.SAFE_READING
        return ReplyDecision(
            mode=mode,
            patient_first_name=first_name,
            overall_status=overall,
            urgent=urgent,
            readings=[
                {
                    "type": obs.observation_type,
                    "value": _jsonable(obs.value),
                    "unit": obs.unit,
                    "context": _jsonable(obs.measurement_context),
                }
                for obs in observations
            ],
            rule_alerts=[
                {
                    "metric": alert.metric,
                    "value": _jsonable(alert.value),
                    "unit": alert.unit,
                    "priority": alert.priority.value,
                    "reason": alert.reason,
                }
                for alert in alerts
            ],
        )

    if extraction.needs_clarification and extraction.clarification_question:
        return ReplyDecision(
            mode=AutoReplyMode.CLARIFICATION,
            patient_first_name=first_name,
            overall_status="clarification_needed",
            clarifying_question=extraction.clarification_question,
        )
    return None


async def _conversation(
    db: AsyncSession, *, patient_id: uuid.UUID, exclude_id: uuid.UUID
) -> list[dict[str, str]]:
    """The most recent exchange, oldest first, for context only."""
    rows = (
        (
            await db.execute(
                select(WhatsAppMessage)
                .where(
                    WhatsAppMessage.patient_id == patient_id,
                    WhatsAppMessage.direction.in_(
                        [MessageDirection.INBOUND, MessageDirection.OUTBOUND]
                    ),
                )
                .order_by(WhatsAppMessage.created_at.desc())
                .limit(CONTEXT_MESSAGES + 1)
            )
        )
        .scalars()
        .all()
    )
    history = [row for row in rows if row.id != exclude_id][:CONTEXT_MESSAGES]
    history.reverse()
    return [
        {
            "from": "patient" if row.direction is MessageDirection.INBOUND else "clinic",
            "text": (row.text_body or "")[:MAX_CONTEXT_CHARS],
        }
        for row in history
        if (row.text_body or "").strip()
    ]


def build_task(
    *,
    decision: ReplyDecision,
    patient_message: str,
    conversation: list[dict[str, str]],
) -> str:
    """The user turn. Every clinical claim the model may make is in here."""
    payload = {
        "mode": decision.mode.value,
        "patient_first_name": decision.patient_first_name,
        "overall_status": decision.overall_status,
        "readings": decision.readings,
        "rule_alerts": decision.rule_alerts,
        "clarifying_question": decision.clarifying_question,
        "latest_patient_message": patient_message[:MAX_CONTEXT_CHARS],
        "recent_conversation": conversation,
    }
    return (
        "Write the WhatsApp reply the clinic should send to this patient.\n"
        "Task payload (JSON):\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Reply with the message text only."
    )


def sanitize(text: str) -> str:
    """Collapse to one short line and enforce the hard character cap."""
    cleaned = _WHITESPACE_RE.sub(" ", text or "").strip().strip(_QUOTE_CHARS)
    if not cleaned:
        raise AutoReplyError("The assistant returned an empty reply.")
    if len(cleaned) > MAX_REPLY_CHARS:
        cut = cleaned[:MAX_REPLY_CHARS]
        cut = cut.rsplit(" ", 1)[0] if " " in cut else cut
        cleaned = cut.rstrip(",.;: ")
    return cleaned


def _generation_available() -> bool:
    return settings.ai_enabled and bool(settings.openai_api_key)


async def generate(task: str) -> str:
    """One chat completion under the closed system prompt."""
    if not _generation_available():
        raise AutoReplyError("AI generation is not configured; auto-reply skipped.")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
    )
    try:
        response = await client.chat.completions.create(
            model=settings.openai_text_model,
            messages=[
                {"role": "system", "content": _AUTO_REPLY_SYSTEM_PROMPT},
                {"role": "user", "content": task},
            ],
            temperature=0.2,
            max_tokens=240,
        )
    except Exception as exc:  # pragma: no cover - depends on provider
        raise AutoReplyError(f"Reply generation failed: {exc}") from exc
    return sanitize(response.choices[0].message.content or "")


async def _in_cooldown(db: AsyncSession, patient_id: uuid.UUID) -> bool:
    cutoff = datetime.now(UTC) - timedelta(seconds=COOLDOWN_SECONDS)
    stmt = (
        select(AutoReply.id)
        .where(
            AutoReply.patient_id == patient_id,
            AutoReply.status == AutoReplyStatus.SENT,
            AutoReply.created_at >= cutoff,
        )
        .limit(1)
    )
    return await db.scalar(stmt) is not None


async def generate_and_send(db: AsyncSession, *, source_message_id: uuid.UUID) -> dict[str, Any]:
    """Decide, write and send the auto-reply for one inbound message.

    Expected failures (no key, provider rejection, session window closed) are
    recorded on the ``auto_replies`` row instead of raised, so the row — and the
    urgent-reading notification queued alongside it — still commits.
    """
    message = await db.get(WhatsAppMessage, source_message_id)
    if message is None:
        return {"found": False, "sent": False}
    if message.direction is not MessageDirection.INBOUND or message.patient_id is None:
        return {"found": True, "sent": False, "reason": "not_inbound"}

    patient = await db.get(Patient, message.patient_id)
    if patient is None:
        return {"found": True, "sent": False, "reason": "patient_missing"}

    extraction = await ai_service.latest_for_message(db, message.id)
    if extraction is None:
        # Analysis enqueues us before its transaction commits; retry until the
        # extraction lands alongside the message.
        return {"found": False, "sent": False}

    if not await settings_service.is_auto_reply_enabled(db):
        return {"found": True, "sent": False, "reason": "auto_reply_disabled"}

    existing = await db.scalar(select(AutoReply).where(AutoReply.source_message_id == message.id))
    if existing is not None:
        return {
            "found": True,
            "sent": existing.status is AutoReplyStatus.SENT,
            "reason": "already_recorded",
            "auto_reply_id": str(existing.id),
        }

    decision = await decide(db, patient=patient, extraction=extraction)
    if decision is None:
        return {"found": True, "sent": False, "reason": "no_reply_needed"}

    suppressed = await _in_cooldown(db, patient.id)
    row = AutoReply(
        source_message_id=message.id,
        patient_id=patient.id,
        mode=decision.mode,
        status=AutoReplyStatus.PENDING if not suppressed else AutoReplyStatus.SUPPRESSED,
        model=settings.openai_text_model,
        prompt_version=AUTO_REPLY_PROMPT_VERSION,
    )
    db.add(row)
    await db.flush()

    if decision.urgent:
        # Queued before generation so a model outage can never swallow an
        # urgent finding.
        auto_reply_queue.enqueue_doctor_notification(row.id)

    if suppressed:
        return {
            "found": True,
            "sent": False,
            "reason": "cooldown",
            "auto_reply_id": str(row.id),
        }

    task = build_task(
        decision=decision,
        patient_message=message.text_body or "",
        conversation=await _conversation(db, patient_id=patient.id, exclude_id=message.id),
    )
    try:
        text = await generate(task)
    except AutoReplyError as exc:
        row.status = AutoReplyStatus.FAILED
        row.error_message = str(exc)
        await db.flush()
        return {
            "found": True,
            "sent": False,
            "reason": "generation_failed",
            "auto_reply_id": str(row.id),
        }

    row.generated_text = text
    try:
        outbound = await messaging_service.send_manual_reply(
            db,
            patient=patient,
            body=text,
            template=None,
            instance_id=message.follow_up_instance_id,
        )
    except ValidationError as exc:
        row.status = AutoReplyStatus.FAILED
        row.error_message = str(exc)
        await db.flush()
        return {"found": True, "sent": False, "reason": "send_failed", "auto_reply_id": str(row.id)}

    row.reply_message_id = outbound.id
    if outbound.delivery_status is DeliveryStatus.SENT:
        row.status = AutoReplyStatus.SENT
    else:  # provider accepted nothing; the outbound row records the failure
        row.status = AutoReplyStatus.FAILED
        row.error_message = outbound.error_message
    await db.flush()
    return {
        "found": True,
        "sent": row.status is AutoReplyStatus.SENT,
        "mode": decision.mode.value,
        "auto_reply_id": str(row.id),
    }


def doctor_message(patient: Patient | None, alerts: list[Alert]) -> str:
    name = _first_name(patient) if patient is not None else "A patient"
    reasons = "; ".join(alert.reason for alert in alerts[:2])
    if len(alerts) > 2:
        reasons += f"; +{len(alerts) - 2} more"
    return f"Urgent reading from {name}: {reasons} Please review in Madhavbaug."


async def notify_doctor(db: AsyncSession, *, auto_reply_id: uuid.UUID) -> dict[str, Any]:
    """One WhatsApp message to the clinic's doctor about an urgent finding.

    Idempotent on ``doctor_notified_at``. Raises on a provider failure so the
    worker retries; a raised error rolls back nothing the patient can see,
    because the reply was already committed by its own task.
    """
    row = await db.get(AutoReply, auto_reply_id)
    if row is None:
        return {"found": False, "notified": False}
    if row.doctor_notified_at is not None:
        return {"found": True, "notified": True, "reason": "already_notified"}

    extraction = await ai_service.latest_for_message(db, row.source_message_id)
    if extraction is None:
        return {"found": True, "notified": False, "reason": "extraction_missing"}

    urgent = [
        alert
        for alert in await alerts_for_extraction(db, extraction.id)
        if alert.priority is AlertPriority.URGENT
    ]
    if not urgent:
        return {"found": True, "notified": False, "reason": "no_urgent_alert"}

    phone = await settings_service.auto_reply_doctor_phone(db)
    if not phone:
        return {"found": True, "notified": False, "reason": "no_doctor_phone"}

    patient = await db.get(Patient, row.patient_id) if row.patient_id else None
    body = doctor_message(patient, urgent)
    result = await whatsapp_client.send_text_message(phone, body)
    now = datetime.now(UTC)

    # Record the page exactly like any other outbound message, so it is
    # visible in the message log and its delivery status can be tracked.
    #
    # It deliberately carries no patient_id: the recipient is the clinic, not
    # the patient. Attaching it to the patient would drop this internal
    # escalation text into the conversation the model is later shown as
    # patient-facing context.
    outbound = WhatsAppMessage(
        patient_id=None,
        direction=MessageDirection.OUTBOUND,
        provider_message_id=result.provider_message_id,
        message_type=MessageType.TEXT,
        to_phone=phone,
        text_body=body,
        delivery_status=DeliveryStatus.SENT if result.ok else DeliveryStatus.FAILED,
        processing_status=MessageProcessingStatus.PROCESSED,
        error_code=result.error_code,
        error_message=result.error_message,
        sent_at=now,
    )
    db.add(outbound)
    await db.flush()
    db.add(
        MessageDeliveryEvent(
            message_id=outbound.id,
            status=outbound.delivery_status or DeliveryStatus.PENDING,
            occurred_at=now,
            payload={"kind": "doctor_notification", "auto_reply_id": str(row.id)},
        )
    )

    if not result.ok:
        # Commit the evidence before raising: the worker rolls back on a raise,
        # and a page we failed to send must still be visible to the clinic
        # rather than vanish with the retry.
        await db.commit()
        raise AutoReplyError(
            f"Doctor notification failed: {result.error_message or result.error_code}"
        )

    row.doctor_notified_at = now
    await db.flush()
    logger.info(
        "doctor_notified",
        auto_reply_id=str(row.id),
        alerts=[str(a.id) for a in urgent],
        to=phone,
    )
    return {"found": True, "notified": True}
