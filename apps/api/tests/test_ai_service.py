"""Unit tests for the offline AI extraction heuristics (no database/network)."""

from __future__ import annotations

from decimal import Decimal

from app.core.config import settings
from app.models.ai import AIExtractionModality, AIExtractionStatus
from app.services import ai as ai_service


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
