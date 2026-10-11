"""Unit tests for the non-response decision helpers (no database required)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.alerts import AlertPriority
from app.models.scheduling import FollowUpInstanceStatus, FollowUpType
from app.services import non_response


def _now() -> datetime:
    return datetime(2026, 1, 10, 12, 0, tzinfo=UTC)


def test_decide_waits_before_deadline() -> None:
    now = _now()
    decision = non_response.decide_non_response(
        deadline=now + timedelta(hours=1),
        status=FollowUpInstanceStatus.SENT,
        reminder_count=0,
        max_reminders=2,
        now=now,
    )
    assert decision == "wait"


def test_decide_waits_when_no_deadline() -> None:
    decision = non_response.decide_non_response(
        deadline=None,
        status=FollowUpInstanceStatus.DELIVERED,
        reminder_count=0,
        max_reminders=2,
        now=_now(),
    )
    assert decision == "wait"


def test_decide_ignores_non_pending_statuses() -> None:
    now = _now()
    for status in (
        FollowUpInstanceStatus.RESPONDED,
        FollowUpInstanceStatus.FAILED,
        FollowUpInstanceStatus.OVERDUE,
        FollowUpInstanceStatus.SCHEDULED,
    ):
        assert (
            non_response.decide_non_response(
                deadline=now - timedelta(hours=1),
                status=status,
                reminder_count=0,
                max_reminders=2,
                now=now,
            )
            == "wait"
        )


def test_decide_reminds_when_deadline_passed_and_reminders_remain() -> None:
    now = _now()
    decision = non_response.decide_non_response(
        deadline=now - timedelta(minutes=1),
        status=FollowUpInstanceStatus.SENT,
        reminder_count=0,
        max_reminders=1,
        now=now,
    )
    assert decision == "remind"


def test_decide_overdue_when_reminders_exhausted() -> None:
    now = _now()
    decision = non_response.decide_non_response(
        deadline=now - timedelta(hours=3),
        status=FollowUpInstanceStatus.READ,
        reminder_count=2,
        max_reminders=2,
        now=now,
    )
    assert decision == "overdue"


def test_decide_overdue_without_reminder_policy() -> None:
    now = _now()
    decision = non_response.decide_non_response(
        deadline=now - timedelta(hours=1),
        status=FollowUpInstanceStatus.DELIVERED,
        reminder_count=0,
        max_reminders=0,
        now=now,
    )
    assert decision == "overdue"


def test_escalation_priority_none_without_policy() -> None:
    assert non_response.escalation_priority(None) is None
    assert non_response.escalation_priority({}) is None


def test_escalation_priority_respects_opt_out() -> None:
    assert non_response.escalation_priority({"escalate_after_deadline": False}) is None


def test_escalation_priority_maps_review_priority() -> None:
    assert non_response.escalation_priority({"review_priority": "urgent"}) == AlertPriority.URGENT
    assert non_response.escalation_priority({"review_priority": "routine"}) == AlertPriority.ROUTINE


def test_escalation_priority_defaults_and_falls_back() -> None:
    assert non_response.escalation_priority({}) is None
    assert (
        non_response.escalation_priority({"review_priority": "nonsense"}) == AlertPriority.PRIORITY
    )
    assert (
        non_response.escalation_priority({"escalate_after_deadline": True})
        == AlertPriority.PRIORITY
    )


def test_follow_up_label_is_human_readable() -> None:
    assert non_response.follow_up_label(FollowUpType.MEAL_CHECK_IN) == "Meal check in"
    assert non_response.follow_up_label(FollowUpType.BLOOD_GLUCOSE) == "Blood glucose"
