"""Deterministic rule engine for numeric safety thresholds (PRD FR-019/FR-020).

Threshold evaluation lives here and only here: the AI layer may extract a
reading, but never decides whether a threshold was crossed. Evaluation is pure
and side-effect free except for the explicit persistence step, making it easy to
test and to reuse from the WhatsApp ingestion path.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alerts import (
    Alert,
    AlertPriority,
    AlertType,
    RuleComparator,
    RuleMetric,
    SafetyRule,
)
from app.models.clinical import Observation

# Which observation types carry each metric. Blood pressure carries two metrics
# (systolic and diastolic) inside its measurement context.
METRIC_OBSERVATION_TYPES: dict[RuleMetric, frozenset[str]] = {
    RuleMetric.SYSTOLIC: frozenset({"blood_pressure"}),
    RuleMetric.DIASTOLIC: frozenset({"blood_pressure"}),
    RuleMetric.BLOOD_GLUCOSE: frozenset({"blood_glucose"}),
    RuleMetric.WEIGHT: frozenset({"weight"}),
}

# Measurement-context keys that hold a metric for compound observations.
_CONTEXT_KEYS = {
    RuleMetric.SYSTOLIC: "systolic",
    RuleMetric.DIASTOLIC: "diastolic",
}

_METRIC_LABELS = {
    RuleMetric.SYSTOLIC: "Systolic blood pressure",
    RuleMetric.DIASTOLIC: "Diastolic blood pressure",
    RuleMetric.BLOOD_GLUCOSE: "Blood glucose",
    RuleMetric.WEIGHT: "Weight",
}

_COMPARATOR_PHRASES = {
    RuleComparator.GT: "above",
    RuleComparator.GTE: "at or above",
    RuleComparator.LT: "below",
    RuleComparator.LTE: "at or below",
}


@dataclass(frozen=True)
class RuleViolation:
    """A single deterministic threshold violation."""

    rule: SafetyRule
    metric: RuleMetric
    value: Decimal
    reason: str


def metric_label(metric: RuleMetric) -> str:
    return _METRIC_LABELS.get(metric, metric.value)


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def extract_metric(observation: Observation, metric: RuleMetric) -> Decimal | None:
    """Read a metric value from an observation, or ``None`` when absent.

    Missing values are never inferred (PRD FR-019): if the reading is not
    present, no comparison is made.
    """
    context_key = _CONTEXT_KEYS.get(metric)
    if context_key is not None:
        context = observation.measurement_context or {}
        return _to_decimal(context.get(context_key))
    return _to_decimal(observation.value)


def _comparator_trips(comparator: RuleComparator, value: Decimal, threshold: Decimal) -> bool:
    if comparator is RuleComparator.GT:
        return value > threshold
    if comparator is RuleComparator.GTE:
        return value >= threshold
    if comparator is RuleComparator.LT:
        return value < threshold
    return value <= threshold


def _context_matches(rule: SafetyRule, observation: Observation) -> bool:
    if not rule.context:
        return True
    context = observation.measurement_context or {}
    return all(context.get(key) == expected for key, expected in rule.context.items())


def _build_reason(rule: SafetyRule, value: Decimal) -> str:
    phrase = _COMPARATOR_PHRASES[rule.comparator]
    return (
        f"{metric_label(rule.metric)} {value} {rule.unit} is {phrase} the configured "
        f"{rule.priority.value} threshold of {rule.threshold} {rule.unit} "
        f"(rule {rule.rule_key} v{rule.version})."
    )


def evaluate(observation: Observation, rules: list[SafetyRule]) -> list[RuleViolation]:
    """Evaluate an observation against the given rules (pure function)."""
    violations: list[RuleViolation] = []
    for rule in rules:
        if not rule.is_active:
            continue
        if observation.observation_type not in METRIC_OBSERVATION_TYPES.get(
            rule.metric, frozenset()
        ):
            continue
        if not _context_matches(rule, observation):
            continue
        value = extract_metric(observation, rule.metric)
        if value is None:
            continue
        if _comparator_trips(rule.comparator, value, rule.threshold):
            violations.append(
                RuleViolation(
                    rule=rule,
                    metric=rule.metric,
                    value=value,
                    reason=_build_reason(rule, value),
                )
            )
    return violations


async def active_rules_for(db: AsyncSession, observation: Observation) -> list[SafetyRule]:
    """Return active rules whose metric applies to the observation type."""
    metrics = [
        metric
        for metric, types in METRIC_OBSERVATION_TYPES.items()
        if observation.observation_type in types
    ]
    if not metrics:
        return []
    stmt = select(SafetyRule).where(SafetyRule.is_active.is_(True), SafetyRule.metric.in_(metrics))
    return list((await db.execute(stmt)).scalars().all())


async def evaluate_observation(db: AsyncSession, observation: Observation) -> list[Alert]:
    """Evaluate an observation and persist an alert per violation (idempotent).

    Already-raised alerts for the same observation and rule are not duplicated,
    so re-processing an observation (e.g. a retried webhook) is safe.
    """
    rules = await active_rules_for(db, observation)
    violations = evaluate(observation, rules)
    if not violations:
        return []

    existing = set(
        (await db.execute(select(Alert.rule_id).where(Alert.observation_id == observation.id)))
        .scalars()
        .all()
    )

    created: list[Alert] = []
    for violation in violations:
        rule = violation.rule
        if rule.id in existing:
            continue
        alert = Alert(
            patient_id=observation.patient_id,
            observation_id=observation.id,
            follow_up_instance_id=observation.follow_up_instance_id,
            rule_id=rule.id,
            rule_version=rule.version,
            metric=rule.metric.value,
            value=violation.value,
            unit=rule.unit,
            priority=rule.priority,
            alert_type=AlertType.THRESHOLD,
            reason=violation.reason,
            context=observation.measurement_context,
        )
        db.add(alert)
        created.append(alert)
    await db.flush()
    return created


async def create_rule(
    db: AsyncSession,
    *,
    rule_key: str,
    metric: RuleMetric,
    comparator: RuleComparator,
    threshold: Decimal,
    unit: str,
    priority: AlertPriority,
    description: str | None,
    context: dict[str, Any] | None,
    actor_id: Any,
) -> SafetyRule:
    """Publish a rule version, deactivating any prior active version."""
    existing = (
        await db.execute(
            select(SafetyRule)
            .where(SafetyRule.rule_key == rule_key)
            .order_by(SafetyRule.version.desc())
        )
    ).scalars()
    versions = list(existing)
    next_version = (versions[0].version + 1) if versions else 1
    for previous in versions:
        if previous.is_active:
            previous.is_active = False

    rule = SafetyRule(
        rule_key=rule_key,
        version=next_version,
        metric=metric,
        comparator=comparator,
        threshold=threshold,
        unit=unit,
        priority=priority,
        description=description,
        context=context,
        is_active=True,
        created_by=actor_id,
    )
    db.add(rule)
    await db.flush()
    return rule


async def list_rules(
    db: AsyncSession, *, active_only: bool = True, rule_key: str | None = None
) -> list[SafetyRule]:
    stmt = select(SafetyRule)
    if active_only:
        stmt = stmt.where(SafetyRule.is_active.is_(True))
    if rule_key is not None:
        stmt = stmt.where(SafetyRule.rule_key == rule_key)
    stmt = stmt.order_by(SafetyRule.rule_key.asc(), SafetyRule.version.desc())
    return list((await db.execute(stmt)).scalars().all())


async def deactivate_rule(db: AsyncSession, rule_id: Any) -> SafetyRule | None:
    rule = await db.get(SafetyRule, rule_id)
    if rule is None:
        return None
    rule.is_active = False
    await db.flush()
    await db.refresh(rule)
    return rule
