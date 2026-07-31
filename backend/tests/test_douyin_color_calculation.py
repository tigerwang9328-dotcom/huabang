"""Task 6: PostgreSQL persistent recalculation worker primitives.

Covers v3.1 §2.5 calculation_jobs:
- deduplication_key computation
- lease expiry detection
- backoff calculation (exponential with cap)
- failure status determination (retryable vs terminal)
- job enqueue/claim/complete/fail/recover logic (pure functions for testability)
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.services.douyin_color_calculation_service import (
    CalculationJobError,
    compute_backoff_seconds,
    compute_deduplication_key,
    determine_failure_status,
    is_lease_expired,
    max_allowed_attempts,
)


def test_compute_deduplication_key_is_deterministic():
    """Same inputs produce the same deduplication_key."""

    key1 = compute_deduplication_key(
        account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="123:456:t7",
    )
    key2 = compute_deduplication_key(
        account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="123:456:t7",
    )
    assert key1 == key2


def test_compute_deduplication_key_differs_for_different_targets():
    """Different targets produce different keys."""

    key1 = compute_deduplication_key(
        account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="123:456:t7",
    )
    key2 = compute_deduplication_key(
        account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="123:456:t30",
    )
    assert key1 != key2


def test_compute_deduplication_key_differs_for_different_accounts():
    """Cross-account jobs must not deduplicate together."""

    key1 = compute_deduplication_key(
        account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="123:456:t7",
    )
    key2 = compute_deduplication_key(
        account_id=2, job_type="recalculate_metric",
        target_type="video_color", target_id="123:456:t7",
    )
    assert key1 != key2


def test_is_lease_expired_returns_true_when_past_expiry():
    """A job whose lease_expires_at is in the past is expired."""

    now = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
    job = {
        "status": "running",
        "lease_expires_at": datetime(2026, 7, 31, 11, 0, tzinfo=timezone.utc),
    }
    assert is_lease_expired(job, now=now) is True


def test_is_lease_expired_returns_false_when_still_active():
    """A job whose lease_expires_at is in the future is not expired."""

    now = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
    job = {
        "status": "running",
        "lease_expires_at": datetime(2026, 7, 31, 13, 0, tzinfo=timezone.utc),
    }
    assert is_lease_expired(job, now=now) is False


def test_is_lease_expired_returns_false_for_non_running_job():
    """Queued or completed jobs don't have active leases."""

    now = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
    assert is_lease_expired({"status": "queued", "lease_expires_at": None}, now=now) is False
    assert is_lease_expired({"status": "succeeded", "lease_expires_at": None}, now=now) is False


def test_compute_backoff_seconds_is_exponential_with_cap():
    """Backoff = min(60, 2^attempt) with attempt starting at 0."""

    assert compute_backoff_seconds(attempt=0) == 1
    assert compute_backoff_seconds(attempt=1) == 2
    assert compute_backoff_seconds(attempt=2) == 4
    assert compute_backoff_seconds(attempt=3) == 8
    assert compute_backoff_seconds(attempt=4) == 16
    assert compute_backoff_seconds(attempt=5) == 32
    assert compute_backoff_seconds(attempt=6) == 60  # capped at 60
    assert compute_backoff_seconds(attempt=10) == 60  # still capped


def test_determine_failure_status_returns_retryable_below_max():
    """Below max attempts -> retryable_failed."""

    assert determine_failure_status(attempt_count=1, max_attempts=5) == "retryable_failed"
    assert determine_failure_status(attempt_count=4, max_attempts=5) == "retryable_failed"


def test_determine_failure_status_returns_terminal_at_max():
    """At or above max attempts -> terminal_failed."""

    assert determine_failure_status(attempt_count=5, max_attempts=5) == "terminal_failed"
    assert determine_failure_status(attempt_count=6, max_attempts=5) == "terminal_failed"


def test_max_allowed_attempts_is_5():
    """v3.1: same video same analysis type max 5 failures per batch."""

    assert max_allowed_attempts() == 5
