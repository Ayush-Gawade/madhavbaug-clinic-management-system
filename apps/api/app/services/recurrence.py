"""Deterministic follow-up recurrence engine.

Schedules store a JSONB ``recurrence_rule`` from a small, validated grammar.
Occurrence dates are computed in pure Python so the scheduler has predictable,
testable behaviour (PRD 10.2). No ruff strings, no cron parsing libraries.

Grammar::

    {"freq": "daily", "interval": 1}                  # every N days
    {"freq": "weekly", "on_weekdays": [1, 3, 5]}      # ISO weekday 1=Mon..7=Sun
    {"freq": "monthly", "day_of_month": 15}           # day-of-month (clamped)
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.core.errors import ValidationError


class RecurrenceRuleError(ValidationError):
    """Raised when a recurrence rule is invalid or unsupported."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            code="invalid_recurrence_rule",
            message=detail,
        )


_MAX_OCCURRENCES = 366


def validate_recurrence_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Validate a recurrence rule and return a normalized copy."""
    if not isinstance(rule, dict):
        raise RecurrenceRuleError("Recurrence rule must be an object.")
    freq = rule.get("freq")
    if freq not in {"daily", "weekly", "monthly"}:
        raise RecurrenceRuleError("Only daily, weekly and monthly frequencies are supported.")

    normalized: dict[str, Any] = {"freq": freq}

    if freq == "daily":
        interval = rule.get("interval", 1)
        if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
            raise RecurrenceRuleError("daily: interval must be a positive integer.")
        if interval > 366:
            raise RecurrenceRuleError("daily: interval must be at most 366.")
        normalized["interval"] = interval
    elif freq == "weekly":
        weekdays = rule.get("on_weekdays")
        if not isinstance(weekdays, list) or not weekdays:
            raise RecurrenceRuleError("weekly: on_weekdays must be a non-empty list.")
        cleaned: list[int] = []
        for day in weekdays:
            if not isinstance(day, int) or isinstance(day, bool) or day < 1 or day > 7:
                raise RecurrenceRuleError("weekly: weekdays must be integers 1 (Mon) to 7 (Sun).")
            if day not in cleaned:
                cleaned.append(day)
        normalized["on_weekdays"] = sorted(cleaned)
    else:  # monthly
        day_of_month = rule.get("day_of_month")
        if not isinstance(day_of_month, int) or isinstance(day_of_month, bool):
            raise RecurrenceRuleError("monthly: day_of_month must be an integer.")
        if day_of_month < 1 or day_of_month > 31:
            raise RecurrenceRuleError("monthly: day_of_month must be between 1 and 31.")
        normalized["day_of_month"] = day_of_month

    return normalized


def _clamp_day(year: int, month: int, day: int) -> date:
    """Clamp day-of-month into valid range (e.g. Feb 31 -> Feb 29)."""
    if month == 12:
        return date(year, month, min(day, 31))
    last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(day, last))


def dates_between(rule: dict[str, Any], start: date, end: date) -> list[date]:
    """Return all occurrence dates in ``[start, end]`` (inclusive), ascending.

    The rule must have been produced by :func:`validate_recurrence_rule`.
    """
    start, end = (start, end) if start <= end else (end, start)
    freq = rule["freq"]
    occurrences: list[date] = []

    if freq == "daily":
        interval = rule["interval"]
        day = start
        guard = 0
        while day <= end:
            occurrences.append(day)
            guard += 1
            if guard > _MAX_OCCURRENCES:
                break
            day += timedelta(days=interval)
        return occurrences

    if freq == "weekly":
        weekdays = set(rule["on_weekdays"])
        day = start
        guard = 0
        while day <= end:
            if day.isoweekday() in weekdays:
                occurrences.append(day)
            guard += 1
            if guard > _MAX_OCCURRENCES * 2:
                break
            day += timedelta(days=1)
        return occurrences

    # monthly
    day_of_month = rule["day_of_month"]
    year, month = start.year, start.month
    guard = 0
    while True:
        candidate = _clamp_day(year, month, day_of_month)
        if candidate >= start and candidate <= end:
            occurrences.append(candidate)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        if date(year, month, 1) > end:
            break
        guard += 1
        if guard > _MAX_OCCURRENCES:
            break
    return occurrences


def next_occurrence_after(rule: dict[str, Any], after: date) -> date | None:
    """Return the first occurrence strictly after ``after`` or ``None``.

    Used to advance a schedule day by day without scanning excessively far.
    """
    end = after + timedelta(days=_MAX_OCCURRENCES)
    for candidate in dates_between(rule, after + timedelta(days=1), end):
        return candidate  # dates_between returns ascending
    return None
