"""Unit tests for the offline AI extraction heuristics (no database/network)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

from app.core.config import settings
from app.models.ai import AIExtractionModality, AIExtractionStatus
from app.models.messaging import WhatsAppMessage
from app.services import ai as ai_service
from app.services import media as media_service
from app.services import whatsapp as whatsapp_client


def test_blood_pressure_is_extracted_from_context() -> None:
    result = ai_service.extract_from_text("My BP was 150/95 this morning")
    assert result.status is AIExtractionStatus.SUCCEEDED
    assert result.intent == "observation_report"
    assert result.modality is AIExtractionModality.TEXT
    assert result.model == ai_service._HEURISTIC_MODEL
    assert len(result.observations) == 1
    observation = result.observations[0]
    assert observation.observation_type == "blood_pressure"
    assert observation.measurement_context == {"systolic": 150.0, "diastolic": 95.0}


def test_glucose_with_unit_is_extracted() -> None:
    result = ai_service.extract_from_text("Sugar 235 mg/dL after dinner")
    assert result.status is AIExtractionStatus.SUCCEEDED
    assert len(result.observations) == 1
    observation = result.observations[0]
    assert observation.observation_type == "blood_glucose"
    assert observation.value == Decimal("235")
    assert observation.unit == "mg/dL"
    assert result.confidence is not None and result.confidence >= Decimal("0.7")


def test_glucose_without_unit_requests_clarification() -> None:
    result = ai_service.extract_from_text("My sugar reading was 235 today")
    assert result.status is AIExtractionStatus.NEEDS_CLARIFICATION
    assert result.needs_clarification is True
    assert result.observations == []
    assert result.clarification_question is not None
    assert "unit" in result.clarification_question.lower()


def test_qualitative_metric_mention_needs_clarification() -> None:
    result = ai_service.extract_from_text("I checked my sugar today, it was high")
    assert result.status is AIExtractionStatus.NEEDS_CLARIFICATION
    assert result.intent == "observation_report"
    assert result.observations == []


def test_weight_with_unit_is_extracted() -> None:
    result = ai_service.extract_from_text("My weight is 78 kg today")
    assert result.status is AIExtractionStatus.SUCCEEDED
    assert result.observations[0].observation_type == "weight"
    assert result.observations[0].value == Decimal("78")


def test_weight_without_unit_needs_clarification() -> None:
    result = ai_service.extract_from_text("I think my weight is 78 now")
    assert result.needs_clarification is True
    assert result.observations == []


def test_meal_update_intent_without_clarification() -> None:
    result = ai_service.extract_from_text("I ate rice and dal for lunch today")
    assert result.intent == "meal_update"
    assert result.needs_clarification is False
    assert result.observations == []


def test_greeting_intent() -> None:
    result = ai_service.extract_from_text("Hello doctor, good morning")
    assert result.intent == "greeting"
    assert result.needs_clarification is False


def test_question_intent() -> None:
    result = ai_service.extract_from_text("When should I take my medicine?")
    assert result.intent == "question"


def test_unreadable_message_requests_clarification() -> None:
    result = ai_service.extract_from_text("asdkjfh qoiwe")
    assert result.status is AIExtractionStatus.NEEDS_CLARIFICATION
    assert result.needs_clarification is True
    assert result.observations == []


def test_confidence_is_within_unit_interval() -> None:
    result = ai_service.extract_from_text("BP 120/80")
    assert result.confidence is not None
    assert Decimal("0") <= result.confidence <= Decimal("1")


async def test_provider_outage_is_caught_and_yields_failure(monkeypatch) -> None:
    """A model/network failure must degrade to a recorded FAILED result."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    class _Boom:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr("openai.AsyncOpenAI", _Boom)
    result = await ai_service.analyze_text("Sugar 235 mg/dL")
    assert result.status is AIExtractionStatus.FAILED
    assert result.observations == []
    assert result.error_message


async def test_ai_disabled_uses_deterministic_extractor(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(settings, "openai_api_key", "")
    result = await ai_service.analyze_text("Sugar 235 mg/dL")
    assert result.model == ai_service._HEURISTIC_MODEL
    assert result.status is AIExtractionStatus.SUCCEEDED


# -- Extraction validation gate (A5) -----------------------------------------


def _obs(
    observation_type: str,
    value: Decimal | None,
    unit: str | None,
    context: dict | None = None,
) -> ai_service.ExtractedObservation:
    return ai_service.ExtractedObservation(
        observation_type=observation_type,
        value=value,
        unit=unit,
        measurement_context=context,
    )


def test_valid_observations_pass_validation() -> None:
    assert ai_service.validate_observation(_obs("blood_glucose", Decimal("235"), "mg/dL")) is None
    assert ai_service.validate_observation(_obs("weight", Decimal("78"), "kg")) is None
    assert (
        ai_service.validate_observation(
            _obs("blood_pressure", None, "mmHg", {"systolic": 120, "diastolic": 80})
        )
        is None
    )


def test_out_of_range_reading_is_rejected() -> None:
    assert ai_service.validate_observation(_obs("blood_glucose", Decimal("5000"), "mg/dL"))
    assert ai_service.validate_observation(_obs("weight", Decimal("800"), "kg"))


def test_missing_value_is_rejected() -> None:
    assert ai_service.validate_observation(_obs("blood_glucose", None, "mg/dL"))


def test_unexpected_unit_is_rejected() -> None:
    assert ai_service.validate_observation(_obs("blood_glucose", Decimal("12"), "mmol/L"))


def test_unsupported_observation_type_is_rejected() -> None:
    assert ai_service.validate_observation(_obs("heart_rate", Decimal("72"), "bpm"))


def test_incomplete_or_reversed_blood_pressure_is_rejected() -> None:
    assert ai_service.validate_observation(_obs("blood_pressure", None, "mmHg", {"systolic": 120}))
    assert ai_service.validate_observation(
        _obs("blood_pressure", None, "mmHg", {"systolic": 80, "diastolic": 120})
    )
    assert ai_service.validate_observation(
        _obs("blood_pressure", None, "mmHg", {"systolic": 500, "diastolic": 90})
    )


# -- Model gateway wiring ----------------------------------------------------


async def test_base_url_is_forwarded_to_the_client(monkeypatch) -> None:
    """The provider gateway (e.g. OpenRouter) must reach the OpenAI client."""
    captured: dict[str, object] = {}

    async def _create(**_: object) -> object:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"intent": "unclear", "confidence": 0.2}')
                )
            ]
        )

    class _FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=_create))

    monkeypatch.setattr("openai.AsyncOpenAI", _FakeClient)
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "openai_base_url", "https://openrouter.ai/api/v1")

    result = await ai_service.analyze_text("hello")

    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["api_key"] == "sk-test"
    assert result.status is AIExtractionStatus.SUCCEEDED


async def test_analyze_image_without_bits_fails_loudly(monkeypatch) -> None:
    """AI on but no bytes must fail, never caption the message and call it vision."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    result = await ai_service.analyze_image(b"", "image/jpeg", "my sugar is 210")

    assert result.status is AIExtractionStatus.FAILED
    assert result.modality is AIExtractionModality.VISION
    assert result.observations == []
    assert result.error_message


async def test_analyze_image_without_bits_is_skipped_offline(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(settings, "openai_api_key", "")

    result = await ai_service.analyze_image(b"", "image/jpeg", None)

    assert result.status is AIExtractionStatus.SKIPPED
    assert result.model == ai_service._HEURISTIC_MODEL


async def test_analyze_image_offline_still_uses_a_caption(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(settings, "openai_api_key", "")

    result = await ai_service.analyze_image(b"", "image/jpeg", "Sugar 180 mg/dL")

    assert result.modality is AIExtractionModality.VISION
    assert result.model == ai_service._HEURISTIC_MODEL
    assert len(result.observations) == 1
    assert result.observations[0].observation_type == "blood_glucose"


async def test_load_media_bytes_prefers_the_stored_copy(monkeypatch, tmp_path) -> None:
    """A stored file is read from disk; the provider is never re-hit."""
    monkeypatch.setattr(settings, "media_root", tmp_path)
    message = WhatsAppMessage(
        id=uuid.uuid4(),
        media_mime_type="image/jpeg",
        media_reference="provider-media-id",
    )
    path = media_service.stored_media_path(message.id, "image/jpeg")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"stored-bytes")

    async def _must_not_download(_media_id: str) -> tuple[bytes, str]:
        raise AssertionError("stored media must not be re-downloaded")

    monkeypatch.setattr(whatsapp_client, "download_media", _must_not_download)

    data, mime = await ai_service._load_media_bytes(message)

    assert data == b"stored-bytes"
    assert mime == "image/jpeg"


async def test_load_media_bytes_falls_back_to_a_download(monkeypatch, tmp_path) -> None:
    """With nothing on disk the provider copy is fetched (AI enabled)."""
    monkeypatch.setattr(settings, "media_root", tmp_path)
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    message = WhatsAppMessage(
        id=uuid.uuid4(),
        media_mime_type="image/jpeg",
        media_reference="provider-media-id",
    )

    async def _download(_media_id: str) -> tuple[bytes, str]:
        return b"downloaded-bytes", "image/jpeg"

    monkeypatch.setattr(whatsapp_client, "download_media", _download)

    data, mime = await ai_service._load_media_bytes(message)

    assert data == b"downloaded-bytes"
    assert mime == "image/jpeg"


# -- Observation type normalisation ------------------------------------------


def test_system_prompt_enumerates_canonical_types() -> None:
    """The model must be told the exact vocabulary the validator accepts."""
    for name in ("blood_glucose", "blood_pressure", "weight"):
        assert name in ai_service._SYSTEM_PROMPT


def test_model_type_aliases_are_canonicalised() -> None:
    """A reading labelled 'sugar'/'bp' must still survive validation."""
    payload = {
        "intent": "observation_report",
        "confidence": 0.9,
        "observations": [
            {"type": "sugar", "value": 248, "unit": "mg/dL"},
            {
                "type": "BP",
                "value": None,
                "unit": "mmHg",
                "context": {"systolic": 150, "diastolic": 95},
            },
            {"type": "body weight", "value": 78, "unit": "kg"},
        ],
    }
    result = ai_service._payload_to_result(
        payload, modality=AIExtractionModality.VISION, model="meta-llama/llama-4-maverick"
    )

    assert [o.observation_type for o in result.observations] == [
        "blood_glucose",
        "blood_pressure",
        "weight",
    ]
    assert all(ai_service.validate_observation(o) is None for o in result.observations)
    # The raw model output is preserved verbatim for provenance.
    assert result.extracted["observations"][0]["type"] == "sugar"


def test_unknown_model_type_is_still_rejected() -> None:
    """Normalisation must not turn an unsupported reading into a stored one."""
    payload = {
        "intent": "observation_report",
        "observations": [{"type": "heart_rate", "value": 72, "unit": "bpm"}],
    }
    result = ai_service._payload_to_result(payload, modality=AIExtractionModality.TEXT, model="m")

    assert result.observations[0].observation_type == "heart_rate"
    assert ai_service.validate_observation(result.observations[0]) is not None
