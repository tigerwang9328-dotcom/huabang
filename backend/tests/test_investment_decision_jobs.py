"""Scheduler helper tests for outcome windows."""

from datetime import datetime, timedelta, timezone

from app.jobs.investment_decision_jobs import due_outcome_windows


def test_due_outcome_windows_are_fixed_and_idempotent():
    executed_at = datetime(2026, 7, 17, tzinfo=timezone.utc)
    now = executed_at + timedelta(hours=169)

    assert due_outcome_windows(executed_at, now, existing=set()) == [24, 72, 168]
    assert due_outcome_windows(executed_at, now, existing={24, 72}) == [168]


def test_future_or_unexecuted_records_have_no_due_windows():
    now = datetime(2026, 7, 17, tzinfo=timezone.utc)

    assert due_outcome_windows(None, now, existing=set()) == []
    assert due_outcome_windows(now + timedelta(hours=1), now, existing=set()) == []
