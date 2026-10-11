"""Unit tests for the deterministic rule engine (no database required)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.models.alerts import AlertPriority, RuleComparator, RuleMetric, SafetyRule
from app.models.clinical import Observation
from app.services import rule_engine


def _rule(
    metric: RuleMetric,
    comparator: RuleComparator,
    threshold: str,
    *,
    priority: AlertPriority = AlertPriority.PRIORITY,
    context: dict | None = None,
    active: bool = True,
    unit: str = "mg/dL",
) -> SafetyRule:
    return SafetyRule(
        rule_key=f"{metric.value}_{comparator.value}",
        version=1,
        metric=metric,
        comparator=comparator,
        threshold=Decimal(threshold),
        unit=unit,
        priority=priority,
        context=context,
        is_active=active,
    )


def _obs(**kwargs) -> Observation:
    base = {"patient_id": uuid.uuid4(), "observed_at": datetime.now(UTC)}
    base.update(kwargs)
    return Observation(**base)


def test_glucose_above_threshold_trips() -> None:
    rule = _rule(RuleMetric.BLOOD_GLUCOSE, RuleComparator.GT, "200")
    observation = _obs(observation_type="blood_glucose", value=Decimal("210"))
    violations = rule_engine.evaluate(observation, [rule])
    assert len(violations) == 1
    assert violations[0].value == Decimal("210")
    assert "above" in violations[0].reason


def test_glucose_within_range_does_not_trip() -> None:
    rule = _rule(RuleMetric.BLOOD_GLUCOSE, RuleComparator.GT, "200")
    observation = _obs(observation_type="blood_glucose", value=Decimal("150"))
    assert rule_engine.evaluate(observation, [rule]) == []


def test_missing_value_is_not_inferred() -> None:
    rule = _rule(RuleMetric.BLOOD_GLUCOSE, RuleComparator.GT, "200")
    observation = _obs(observation_type="blood_glucose", value=None)
    assert rule_engine.evaluate(observation, [rule]) == []


def test_inactive_rule_is_skipped() -> None:
    rule = _rule(RuleMetric.BLOOD_GLUCOSE, RuleComparator.GT, "200", active=False)
    observation = _obs(observation_type="blood_glucose", value=Decimal("210"))
    assert rule_engine.evaluate(observation, [rule]) == []


def test_comparator_boundary_is_inclusive_for_gte() -> None:
    rule = _rule(RuleMetric.BLOOD_GLUCOSE, RuleComparator.GTE, "200")
    observation = _obs(observation_type="blood_glucose", value=Decimal("200"))
    assert len(rule_engine.evaluate(observation, [rule])) == 1


def test_blood_pressure_reads_measurement_context() -> None:
    systolic = _rule(RuleMetric.SYSTOLIC, RuleComparator.GT, "140", unit="mmHg")
    observation = _obs(
        observation_type="blood_pressure",
        measurement_context={"systolic": 150, "diastolic": 95},
    )
    violations = rule_engine.evaluate(observation, [systolic])
    assert len(violations) == 1
    assert violations[0].value == Decimal("150")


def test_metric_not_applicable_to_observation_type() -> None:
    systolic = _rule(RuleMetric.SYSTOLIC, RuleComparator.GT, "140", unit="mmHg")
    observation = _obs(observation_type="blood_glucose", value=Decimal("210"))
    assert rule_engine.evaluate(observation, [systolic]) == []


def test_context_filter_requires_match() -> None:
    rule = _rule(
        RuleMetric.BLOOD_GLUCOSE,
        RuleComparator.GT,
        "200",
        context={"context": "fasting"},
    )
    post_meal = _obs(
        observation_type="blood_glucose",
        value=Decimal("210"),
        measurement_context={"context": "post_meal"},
    )
    fasting = _obs(
        observation_type="blood_glucose",
        value=Decimal("210"),
        measurement_context={"context": "fasting"},
    )
    assert rule_engine.evaluate(post_meal, [rule]) == []
    assert len(rule_engine.evaluate(fasting, [rule])) == 1


def test_extract_metric_handles_string_context_values() -> None:
    observation = _obs(
        observation_type="blood_pressure",
        measurement_context={"systolic": "150", "diastolic": "95"},
    )
    assert rule_engine.extract_metric(observation, RuleMetric.SYSTOLIC) == Decimal("150")
    assert rule_engine.extract_metric(observation, RuleMetric.DIASTOLIC) == Decimal("95")
