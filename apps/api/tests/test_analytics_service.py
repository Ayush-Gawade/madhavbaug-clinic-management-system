"""Unit tests for analytics bucketing helpers (no database required)."""

from __future__ import annotations

from datetime import date

from app.services.analytics import _bucket_start, _expected_buckets


def test_bucket_start_day_is_identity() -> None:
    assert _bucket_start(date(2026, 10, 10), "day") == date(2026, 10, 10)


def test_bucket_start_week_is_monday() -> None:
    # 2026-10-10 is a Saturday; its week begins Monday 2026-10-05.
    assert _bucket_start(date(2026, 10, 10), "week") == date(2026, 10, 5)


def test_bucket_start_month_is_first_day() -> None:
    assert _bucket_start(date(2026, 10, 10), "month") == date(2026, 10, 1)


def test_expected_buckets_daily_count() -> None:
    buckets = _expected_buckets(date(2026, 10, 1), date(2026, 10, 10), "day")
    assert len(buckets) == 10
    assert buckets[0] == date(2026, 10, 1)
    assert buckets[-1] == date(2026, 10, 10)


def test_expected_buckets_weekly_collapses_consecutive_days() -> None:
    # 2026-10-01 (Thu) -> Monday 2026-09-28; 2026-10-10 (Sat) -> Monday 2026-10-05.
    buckets = _expected_buckets(date(2026, 10, 1), date(2026, 10, 10), "week")
    assert buckets == [date(2026, 9, 28), date(2026, 10, 5)]


def test_expected_buckets_monthly_within_one_month() -> None:
    buckets = _expected_buckets(date(2026, 10, 1), date(2026, 10, 31), "month")
    assert buckets == [date(2026, 10, 1)]


def test_expected_buckets_monthly_across_months() -> None:
    buckets = _expected_buckets(date(2026, 1, 15), date(2026, 4, 2), "month")
    assert buckets == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
        date(2026, 4, 1),
    ]
