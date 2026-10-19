"""AI-assisted message extraction with strict provenance (PRD FR-018, FR-020).

The AI layer is deliberately narrow: it may *extract* structured readings from a
patient's text or photo, but it never diagnoses, never advises on medication and
never decides whether a threshold was crossed. Extracted observations are written
as ordinary clinical data and then evaluated by the deterministic rule engine, so
the safety path does not depend on the model.

When the integration is disabled (no API key or ``ai_enabled`` false) a
deterministic heuristic extractor runs instead, which keeps the whole flow
working offline and makes tests reproducible.
"""

from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.pagination import PageParams
from app.models.ai import AIExtraction, AIExtractionModality, AIExtractionStatus
from app.models.alerts import Alert, AlertPriority, AlertType
from app.models.clinical import (
    Observation,
    ObservationSource,
    ObservationValidationStatus,
    Patient,
)
from app.models.messaging import (
    MessageDirection,
    MessageProcessingStatus,
    MessageType,
    WhatsAppMessage,
)
from app.models.scheduling import FollowUpInstance
from app.services import auto_reply_queue, rule_engine
from app.services import media as media_service
from app.services import settings as settings_service
from app.services import whatsapp as whatsapp_client

PROMPT_VERSION = "extraction-v2"
_HEURISTIC_MODEL = "heuristic"

_SYSTEM_PROMPT = """You extract structured clinical data from a patient message.
Rules you must always follow:
- Only extract what the patient explicitly stated. Never infer missing values or units.
- Never diagnose, never recommend or change medication, never give treatment advice.
- Use the metric units the patient gave. If a value has no unit, do not invent one.
- If a clinical reading is unclear, partial or unit-less, set needs_clarification true
  and ask one short clarifying question. Otherwise set it false.
Return strict JSON with keys: intent (one of observation_report, meal_update,
symptom, question, greeting, unclear), needs_clarification (boolean),
clarification_question (string or null), confidence (0-1),
observations (array of {type, value, unit, context}).
Every observation type MUST be one of these exact names, with the given unit:
- "blood_glucose"  unit "mg/dL"   value is a single number
- "blood_pressure" unit "mmHg"    value null, context {"systolic": n, "diastolic": n}
- "weight"         unit "kg"      value is a single number
Never invent other type names (do not use "sugar", "bp", "glucose", ...).
Leave observations empty when the message carries no such reading."""

_BP_RE = re.compile(r"(\d{2,3})\s*(?:/|over|by)\s*(\d{2,3})")
_GLUCOSE_RE = re.compile(
    r"(?:sugar|glucose|blood\s*sugar|fbs|ppbs|bs)\D{0,12}(\d{2,3}(?:\.\d+)?)", re.IGNORECASE
)
_GLUCOSE_UNIT_RE = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*(?:mg\s*/?\s*dl|mgdl)", re.IGNORECASE)
_WEIGHT_RE = re.compile(r"(?:weight|wt|weigh)\D{0,12}(\d{2,3}(?:\.\d+)?)", re.IGNORECASE)
_WEIGHT_UNIT_RE = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*(?:kg\b|kgs\b|kilo(?:gram)?s?)", re.IGNORECASE)
_METRIC_KEYWORD_RE = re.compile(r"(sugar|glucose|blood\s*pressure|bp\b|weight|wt\b)", re.IGNORECASE)
_MEAL_KEYWORD_RE = re.compile(
    r"(ate|eaten|breakfast|lunch|dinner|meal|food|diet|snack|fasting|post.?meal)", re.IGNORECASE
)
_SYMPTOM_KEYWORD_RE = re.compile(
    r"(pain|ache|dizz|fever|cough|nausea|vomit|tired|fatigue|weak|swelling|breathless)",
    re.IGNORECASE,
)
_GREETING_RE = re.compile(
    r"^(hi|hello|hey|namaste|good\s*(morning|evening)|thanks|thank you)", re.IGNORECASE
)


@dataclass(frozen=True)
class ExtractedObservation:
    """One structured reading proposed by the model."""

    observation_type: str
    value: Decimal | None
    unit: str | None
    measurement_context: dict[str, Any] | None = None


@dataclass(frozen=True)
class ExtractionResult:
    """Normalized outcome of one AI analysis."""

    modality: AIExtractionModality
    model: str
    status: AIExtractionStatus
    intent: str | None = None
    confidence: Decimal | None = None
    needs_clarification: bool = False
    clarification_question: str | None = None
    observations: list[ExtractedObservation] = field(default_factory=list)
    extracted: dict[str, Any] = field(default_factory=dict)
    raw_response: dict[str, Any] | None = None
    error_message: str | None = None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


_VALUE_RANGES: dict[str, tuple[Decimal, Decimal]] = {
    "blood_glucose": (Decimal("10"), Decimal("1000")),  # mg/dL
    "weight": (Decimal("2"), Decimal("500")),  # kg
}
_ACCEPTED_UNITS: dict[str, set[str]] = {
    "blood_glucose": {"mg/dl", "mgdl"},
    "weight": {"kg", "kgs", "kilogram", "kilograms"},
}

# Models do not reliably echo the canonical type names, so aliases are folded
# onto the canonical set before validation. Without this, a perfectly good
# reading the model labelled "sugar" would be rejected as unsupported.
_OBSERVATION_TYPE_ALIASES: dict[str, str] = {
    "sugar": "blood_glucose",
    "blood sugar": "blood_glucose",
    "blood_sugar": "blood_glucose",
    "glucose": "blood_glucose",
    "blood glucose": "blood_glucose",
    "blood glucose level": "blood_glucose",
    "blood_glucose_level": "blood_glucose",
    "glucose level": "blood_glucose",
    "fasting glucose": "blood_glucose",
    "fasting sugar": "blood_glucose",
    "postprandial glucose": "blood_glucose",
    "random glucose": "blood_glucose",
    "bp": "blood_pressure",
    "blood pressure": "blood_pressure",
    "systolic diastolic": "blood_pressure",
    "body weight": "weight",
    "body_weight": "weight",
    "wt": "weight",
    "weigh": "weight",
}


def _normalize_observation_type(raw: Any) -> str:
    """Fold a model-supplied observation type onto the canonical vocabulary."""
    name = str(raw or "").strip().lower()
    return _OBSERVATION_TYPE_ALIASES.get(name, name.replace(" ", "_"))


def validate_observation(observation: ExtractedObservation) -> str | None:
    """Return a clarification reason when an extracted reading is implausible.

    Guards the persistence path against malformed or out-of-range model output.
    Returns ``None`` when the observation is safe to store.
    """
    obs_type = (observation.observation_type or "").strip().lower()
    if obs_type == "blood_pressure":
        context = observation.measurement_context or {}
        systolic = _to_decimal(context.get("systolic"))
        diastolic = _to_decimal(context.get("diastolic"))
        if systolic is None or diastolic is None:
            return "The blood pressure reading was incomplete; please resend systolic/diastolic."
        if not (Decimal("40") <= systolic <= Decimal("300")) or not (
            Decimal("20") <= diastolic <= Decimal("200")
        ):
            return "The blood pressure reading is outside a plausible range; please confirm it."
        if systolic <= diastolic:
            return "The blood pressure reading looks reversed; please send systolic over diastolic."
        return None

    if obs_type not in _VALUE_RANGES:
        return f"The reading type '{observation.observation_type}' is not supported."

    if observation.value is None:
        return f"The {obs_type.replace('_', ' ')} reading had no numeric value."
    low, high = _VALUE_RANGES[obs_type]
    if not (low <= observation.value <= high):
        return (
            f"The {obs_type.replace('_', ' ')} reading {observation.value} is outside a "
            "plausible range; please confirm it."
        )
    if observation.unit and observation.unit.strip().lower() not in _ACCEPTED_UNITS[obs_type]:
        return (
            f"The unit '{observation.unit}' was not recognised; please resend with the right unit."
        )
    return None


def _ai_available() -> bool:
    return settings.ai_enabled and bool(settings.openai_api_key)


# -- Heuristic (offline) extractor -------------------------------------------


def _heuristic_payload(text: str) -> dict[str, Any]:
    """Deterministic, dependency-free extraction used offline and in tests."""
    raw = (text or "").strip()
    observations: list[dict[str, Any]] = []
    intent = "unclear"
    needs = False
    question: str | None = None

    bp = _BP_RE.search(raw)
    if bp:
        observations.append(
            {
                "type": "blood_pressure",
                "value": None,
                "unit": "mmHg",
                "context": {"systolic": float(bp.group(1)), "diastolic": float(bp.group(2))},
            }
        )
        intent = "observation_report"

    if not observations:
        glucose = _search_glucose(raw)
        if glucose is not None:
            number, explicit_unit = glucose
            if explicit_unit:
                observations.append(
                    {
                        "type": "blood_glucose",
                        "value": float(number),
                        "unit": "mg/dL",
                        "context": None,
                    }
                )
            else:
                needs = True
                question = (
                    f"You mentioned a blood sugar reading of {number}. "
                    "Please confirm the units (mg/dL)."
                )
            intent = "observation_report"

    if not observations and intent == "unclear":
        weight = _search_weight(raw)
        if weight is not None:
            number, explicit_unit = weight
            if explicit_unit:
                observations.append(
                    {"type": "weight", "value": float(number), "unit": "kg", "context": None}
                )
            else:
                needs = True
                question = f"You mentioned a weight of {number}. Please confirm the units (kg)."
            intent = "observation_report"

    if not observations and not needs and _METRIC_KEYWORD_RE.search(raw):
        needs = True
        question = (
            "Please share the exact reading with units (for example 120/80 mmHg or 110 mg/dL)."
        )
        intent = "observation_report"

    if intent == "unclear":
        if _MEAL_KEYWORD_RE.search(raw):
            intent = "meal_update"
        elif _SYMPTOM_KEYWORD_RE.search(raw):
            intent = "symptom"
        elif _GREETING_RE.search(raw):
            intent = "greeting"
        elif "?" in raw:
            intent = "question"
        else:
            needs = True
            question = (
                "We could not read a value from your message. "
                "Could you resend it with the reading and units?"
            )

    if observations:
        confidence = 0.9
    elif needs:
        confidence = 0.5
    elif intent in {"meal_update", "symptom"}:
        confidence = 0.6
    elif intent in {"greeting", "question"}:
        confidence = 0.8
    else:
        confidence = 0.3

    return {
        "intent": intent,
        "needs_clarification": needs,
        "clarification_question": question,
        "confidence": confidence,
        "observations": observations,
    }


def _search_glucose(raw: str) -> tuple[str, bool] | None:
    match = _GLUCOSE_RE.search(raw)
    if match:
        return match.group(1), bool(_GLUCOSE_UNIT_RE.search(raw))
    unit = _GLUCOSE_UNIT_RE.search(raw)
    if unit:
        return unit.group(1), True
    return None


def _search_weight(raw: str) -> tuple[str, bool] | None:
    match = _WEIGHT_RE.search(raw)
    if match:
        return match.group(1), bool(_WEIGHT_UNIT_RE.search(raw))
    unit = _WEIGHT_UNIT_RE.search(raw)
    if unit:
        return unit.group(1), True
    return None


def _payload_to_result(
    payload: dict[str, Any], *, modality: AIExtractionModality, model: str
) -> ExtractionResult:
    raw_observations = payload.get("observations") or []
    observations: list[ExtractedObservation] = []
    if isinstance(raw_observations, list):
        for item in raw_observations:
            if not isinstance(item, dict) or not item.get("type"):
                continue
            context = item.get("context")
            observations.append(
                ExtractedObservation(
                    observation_type=_normalize_observation_type(item["type"]),
                    value=_to_decimal(item.get("value")),
                    unit=item.get("unit"),
                    measurement_context=context if isinstance(context, dict) else None,
                )
            )
    needs = bool(payload.get("needs_clarification"))
    return ExtractionResult(
        modality=modality,
        model=model,
        status=AIExtractionStatus.NEEDS_CLARIFICATION if needs else AIExtractionStatus.SUCCEEDED,
        intent=payload.get("intent"),
        confidence=_to_decimal(payload.get("confidence")),
        needs_clarification=needs,
        clarification_question=payload.get("clarification_question"),
        observations=observations,
        extracted=payload,
    )


def extract_from_text(text: str) -> ExtractionResult:
    """Offline extraction (public for unit tests)."""
    return _payload_to_result(
        _heuristic_payload(text), modality=AIExtractionModality.TEXT, model=_HEURISTIC_MODEL
    )


# -- Model-backed extraction -------------------------------------------------


def _build_messages(
    *,
    text: str | None,
    image_bytes: bytes | None,
    mime: str | None,
    caption: str | None,
    modality: AIExtractionModality,
) -> list[dict[str, Any]]:
    if modality == AIExtractionModality.VISION:
        parts: list[dict[str, Any]] = [
            {"type": "text", "text": caption or "Extract any clinical reading from this image."}
        ]
        if image_bytes:
            encoded = base64.b64encode(image_bytes).decode("ascii")
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime or 'image/jpeg'};base64,{encoded}"},
                }
            )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": parts},
        ]
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": text or ""},
    ]


async def _analyze_with_model(
    *,
    text: str | None,
    image_bytes: bytes | None,
    mime: str | None,
    caption: str | None,
    modality: AIExtractionModality,
    model: str,
) -> ExtractionResult:
    try:  # pragma: no cover - network dependent
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        )
        response = await client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=_build_messages(
                text=text, image_bytes=image_bytes, mime=mime, caption=caption, modality=modality
            ),
        )  # type: ignore[call-overload]
        content = response.choices[0].message.content or "{}"
        payload = json.loads(content)
        result = _payload_to_result(payload, modality=modality, model=model)
        return ExtractionResult(
            modality=result.modality,
            model=result.model,
            status=result.status,
            intent=result.intent,
            confidence=result.confidence,
            needs_clarification=result.needs_clarification,
            clarification_question=result.clarification_question,
            observations=result.observations,
            extracted=result.extracted,
            raw_response={"content": payload},
        )
    except Exception as exc:
        return ExtractionResult(
            modality=modality,
            model=model,
            status=AIExtractionStatus.FAILED,
            error_message=str(exc)[:500],
        )


async def analyze_text(text: str) -> ExtractionResult:
    if not _ai_available():
        return extract_from_text(text)
    return await _analyze_with_model(
        text=text,
        image_bytes=None,
        mime=None,
        caption=None,
        modality=AIExtractionModality.TEXT,
        model=settings.openai_text_model,
    )


async def _load_media_bytes(message: WhatsAppMessage) -> tuple[bytes, str | None]:
    """Bytes for an image message: the stored copy first, else a fresh download.

    Reading from ``media_root`` avoids a second provider round-trip (and a
    second failure) for media the worker already persisted.
    """
    path = media_service.stored_media_path(message.id, message.media_mime_type)
    if path.is_file():
        return path.read_bytes(), message.media_mime_type

    if not (_ai_available() and message.media_reference):
        return b"", message.media_mime_type

    try:  # pragma: no cover - network dependent
        data, mime = await whatsapp_client.download_media(message.media_reference)
    except Exception:
        return b"", message.media_mime_type
    return data, mime or message.media_mime_type


async def analyze_image(
    image_bytes: bytes, mime: str | None, caption: str | None
) -> ExtractionResult:
    if not _ai_available():
        if caption:
            base = extract_from_text(caption)
            return ExtractionResult(
                modality=AIExtractionModality.VISION,
                model=_HEURISTIC_MODEL,
                status=base.status,
                intent=base.intent,
                confidence=base.confidence,
                needs_clarification=base.needs_clarification,
                clarification_question=base.clarification_question,
                observations=base.observations,
                extracted=base.extracted,
            )
        return ExtractionResult(
            modality=AIExtractionModality.VISION,
            model=_HEURISTIC_MODEL,
            status=AIExtractionStatus.SKIPPED,
            intent="image",
        )

    # With the model enabled but no bytes on hand there is nothing to see. Fail
    # loudly instead of quietly captioning the message and calling it vision.
    if not image_bytes:
        return ExtractionResult(
            modality=AIExtractionModality.VISION,
            model=settings.openai_vision_model,
            status=AIExtractionStatus.FAILED,
            intent="image",
            error_message="Image bytes were unavailable (media expired or download failed).",
        )

    return await _analyze_with_model(
        text=None,
        image_bytes=image_bytes,
        mime=mime,
        caption=caption,
        modality=AIExtractionModality.VISION,
        model=settings.openai_vision_model,
    )


# -- Persistence -------------------------------------------------------------


async def persist_extraction(
    db: AsyncSession,
    *,
    patient: Patient,
    message: WhatsAppMessage,
    instance: FollowUpInstance | None,
    result: ExtractionResult,
) -> AIExtraction:
    """Store provenance and materialize any extracted observations."""
    extraction = AIExtraction(
        patient_id=patient.id,
        message_id=message.id,
        modality=result.modality,
        model=result.model,
        prompt_version=PROMPT_VERSION,
        status=result.status,
        intent=result.intent,
        confidence=result.confidence,
        needs_clarification=result.needs_clarification,
        clarification_question=result.clarification_question,
        extracted=result.extracted or None,
        raw_response=result.raw_response,
        error_message=result.error_message,
    )
    db.add(extraction)
    await db.flush()

    created = 0
    validated = result.confidence is not None and result.confidence >= Decimal("0.7")
    validation_failures: list[str] = []
    for observation_data in result.observations:
        reason = validate_observation(observation_data)
        if reason is not None:
            validation_failures.append(reason)
            continue
        observation = Observation(
            patient_id=message.patient_id,
            follow_up_instance_id=instance.id if instance is not None else None,
            observation_type=observation_data.observation_type,
            value=observation_data.value,
            unit=observation_data.unit,
            observed_at=datetime.now(UTC),
            source=ObservationSource.WHATSAPP,
            measurement_context=observation_data.measurement_context,
            validation_status=(
                ObservationValidationStatus.VALIDATED
                if validated
                else ObservationValidationStatus.PENDING
            ),
            ai_extraction_id=extraction.id,
        )
        db.add(observation)
        await db.flush()
        await rule_engine.evaluate_observation(db, observation)
        created += 1

    extraction.observations_created = created

    needs_clarification = result.needs_clarification or bool(validation_failures)
    if needs_clarification:
        clarification = (
            result.clarification_question
            or (validation_failures[0] if validation_failures else None)
            or "Patient message needs clarification."
        )
        extraction.needs_clarification = True
        extraction.clarification_question = clarification
        if validation_failures:
            extraction.status = AIExtractionStatus.NEEDS_CLARIFICATION
        message.processing_status = MessageProcessingStatus.NEEDS_CLARIFICATION
        db.add(
            Alert(
                patient_id=message.patient_id,
                follow_up_instance_id=instance.id if instance is not None else None,
                alert_type=AlertType.CLARIFICATION,
                priority=AlertPriority.ROUTINE,
                reason=clarification,
                context={
                    "message_id": str(message.id),
                    "extraction_id": str(extraction.id),
                    "intent": result.intent,
                },
            )
        )
    elif result.status is AIExtractionStatus.FAILED:
        # Surface a provider/media failure instead of leaving the message as
        # "processed" with no readings.
        message.processing_status = MessageProcessingStatus.FAILED
    else:
        message.processing_status = MessageProcessingStatus.PROCESSED

    await db.flush()
    return extraction


async def analyze_inbound(
    db: AsyncSession,
    message: WhatsAppMessage,
    patient: Patient,
    instance: FollowUpInstance | None,
) -> AIExtraction | None:
    """Analyze a stored inbound message and persist the result + observations."""
    if message.direction != MessageDirection.INBOUND:
        return None

    if message.message_type == MessageType.TEXT:
        result = await analyze_text(message.text_body or "")
    elif message.message_type == MessageType.IMAGE:
        image_bytes, mime = await _load_media_bytes(message)
        result = await analyze_image(image_bytes, mime, message.text_body)
    else:
        return None

    extraction = await persist_extraction(
        db, message=message, patient=patient, instance=instance, result=result
    )
    if await settings_service.is_auto_reply_enabled(db):
        # The reply runs in its own task: it must never roll back the observation
        # or the alert persisted above. The worker retries until this
        # transaction commits, and a broker outage is swallowed so analysis
        # cannot fail because of the reply.
        auto_reply_queue.enqueue_auto_reply(message.id)
    return extraction


# -- Queries -----------------------------------------------------------------


async def list_extractions(
    db: AsyncSession, patient_id: uuid.UUID, pagination: PageParams
) -> tuple[list[AIExtraction], int]:
    total = (
        await db.execute(
            select(func.count())
            .select_from(AIExtraction)
            .where(AIExtraction.patient_id == patient_id)
        )
    ).scalar_one()
    rows = list(
        (
            await db.execute(
                select(AIExtraction)
                .where(AIExtraction.patient_id == patient_id)
                .order_by(AIExtraction.created_at.desc())
                .offset(pagination.offset)
                .limit(pagination.limit)
            )
        )
        .scalars()
        .all()
    )
    return rows, int(total)


async def get_extraction(db: AsyncSession, extraction_id: uuid.UUID) -> AIExtraction | None:
    return await db.get(AIExtraction, extraction_id)


async def latest_for_message(db: AsyncSession, message_id: uuid.UUID) -> AIExtraction | None:
    stmt = (
        select(AIExtraction)
        .where(AIExtraction.message_id == message_id)
        .order_by(AIExtraction.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def analyze_message_by_id(db: AsyncSession, message_id: uuid.UUID) -> dict[str, Any]:
    """Analyze a stored inbound message by id (used by the deferred worker).

    Returns ``{"found": False, ...}`` while the message row is not yet visible,
    so the caller can retry: the webhook enqueues analysis before its request
    transaction commits.
    """
    message = await db.get(WhatsAppMessage, message_id)
    if message is None:
        return {"found": False, "analyzed": 0}
    if message.patient_id is None or message.direction != MessageDirection.INBOUND:
        return {"found": True, "analyzed": 0}
    patient = await db.get(Patient, message.patient_id)
    if patient is None:
        return {"found": True, "analyzed": 0}
    instance: FollowUpInstance | None = None
    if message.follow_up_instance_id is not None:
        instance = await db.get(FollowUpInstance, message.follow_up_instance_id)
    extraction = await analyze_inbound(db, message, patient, instance)
    return {"found": True, "analyzed": 1 if extraction is not None else 0}


async def reanalyze(db: AsyncSession, message_id: uuid.UUID) -> AIExtraction | None:
    """Manually re-run analysis for a stored inbound message (staff action)."""
    message = await db.get(WhatsAppMessage, message_id)
    if message is None or message.patient_id is None:
        return None
    patient = await db.get(Patient, message.patient_id)
    if patient is None:
        return None
    instance: FollowUpInstance | None = None
    if message.follow_up_instance_id is not None:
        instance = await db.get(FollowUpInstance, message.follow_up_instance_id)
    return await analyze_inbound(db, message, patient, instance)
