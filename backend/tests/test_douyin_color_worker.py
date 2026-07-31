"""Task 6: PostgreSQL persistent recalculation worker DB operations.

Pure-function tests for the calculation job lifecycle (v3.1 §2.5):
- enqueue_job (deduplication by deduplication_key)
- claim_job (FOR UPDATE SKIP LOCKED semantics: earliest available, skip running)
- complete_job (succeeded + lease release)
- fail_job (retryable_failed + backoff, or terminal_failed at max attempts)
- recover_expired_leases (stuck running -> queued)
"""

from datetime import datetime, timedelta, timezone

from app.services.douyin_color_calculation_service import (
    claim_job,
    complete_job,
    compute_backoff_seconds,
    enqueue_job,
    fail_job,
    max_allowed_attempts,
    recover_expired_leases,
)


NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# enqueue_job
# ---------------------------------------------------------------------------

def test_enqueue_job_creates_new_queued_job():
    job, jobs = enqueue_job(
        jobs=[], account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="123:456:t7", now=NOW,
    )
    assert job["account_id"] == 1
    assert job["job_type"] == "recalculate_metric"
    assert job["target_type"] == "video_color"
    assert job["target_id"] == "123:456:t7"
    assert job["status"] == "queued"
    assert job["attempt_count"] == 0
    assert job["available_at"] == NOW
    assert job["deduplication_key"]
    assert job["lease_expires_at"] is None
    assert len(jobs) == 1


def test_enqueue_job_deduplicates_same_key():
    """Re-enqueueing the same target returns the existing job, no duplicate."""
    job1, jobs = enqueue_job(
        jobs=[], account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="123:456:t7", now=NOW,
    )
    job2, jobs = enqueue_job(
        jobs=jobs, account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="123:456:t7", now=NOW,
    )
    assert job2["id"] == job1["id"]
    assert len(jobs) == 1


def test_enqueue_job_different_target_creates_new_job():
    job1, jobs = enqueue_job(
        jobs=[], account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="123:456:t7", now=NOW,
    )
    job2, jobs = enqueue_job(
        jobs=jobs, account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="123:456:t30", now=NOW,
    )
    assert job2["id"] != job1["id"]
    assert len(jobs) == 2


def test_enqueue_job_isolates_accounts():
    """Same target across accounts must not deduplicate together."""
    job1, jobs = enqueue_job(
        jobs=[], account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="t7", now=NOW,
    )
    job2, jobs = enqueue_job(
        jobs=jobs, account_id=2, job_type="recalculate_metric",
        target_type="video_color", target_id="t7", now=NOW,
    )
    assert job2["id"] != job1["id"]
    assert len(jobs) == 2


# ---------------------------------------------------------------------------
# claim_job
# ---------------------------------------------------------------------------

def test_claim_job_returns_none_when_nothing_claimable():
    claimed, jobs = claim_job(jobs=[], worker_id="w1", lease_seconds=30, now=NOW)
    assert claimed is None


def test_claim_job_marks_queued_as_running():
    job, jobs = enqueue_job(
        jobs=[], account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="a", now=NOW,
    )
    claimed, jobs = claim_job(jobs=jobs, worker_id="w1", lease_seconds=30, now=NOW)
    assert claimed is not None
    assert claimed["id"] == job["id"]
    assert claimed["status"] == "running"
    assert claimed["lease_owner"] == "w1"
    assert claimed["lease_expires_at"] == NOW + timedelta(seconds=30)
    assert claimed["started_at"] == NOW
    assert claimed["attempt_count"] == 1


def test_claim_job_picks_earliest_available():
    """Among multiple queued jobs, the earliest available_at is claimed first."""
    _, jobs = enqueue_job(
        jobs=[], account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="later", now=NOW,
    )
    earlier_job, jobs = enqueue_job(
        jobs=jobs, account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="earlier",
        now=NOW - timedelta(seconds=60),
    )
    claimed, jobs = claim_job(jobs=jobs, worker_id="w1", lease_seconds=30, now=NOW)
    assert claimed["id"] == earlier_job["id"]


def test_claim_job_skips_running_jobs():
    """A running job is locked and not claimable by another worker (SKIP LOCKED)."""
    _, jobs = enqueue_job(
        jobs=[], account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="a", now=NOW,
    )
    _, jobs = claim_job(jobs=jobs, worker_id="w1", lease_seconds=30, now=NOW)
    claimed_again, jobs = claim_job(jobs=jobs, worker_id="w2", lease_seconds=30, now=NOW)
    assert claimed_again is None


def test_claim_job_skips_retryable_failed_in_backoff():
    """A retryable_failed job still in backoff (available_at > now) is skipped."""
    job, jobs = enqueue_job(
        jobs=[], account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="a", now=NOW,
    )
    claimed, jobs = claim_job(jobs=jobs, worker_id="w1", lease_seconds=30, now=NOW)
    failed, jobs = fail_job(
        jobs=jobs, job_id=claimed["id"], error_message="boom", now=NOW,
    )
    assert failed["status"] == "retryable_failed"
    backoff = compute_backoff_seconds(attempt=failed["attempt_count"])
    # before backoff elapses -> not claimable
    claimed_early, jobs = claim_job(
        jobs=jobs, worker_id="w2", lease_seconds=30,
        now=NOW + timedelta(seconds=backoff - 1),
    )
    assert claimed_early is None
    # after backoff elapses -> claimable again
    claimed_late, jobs = claim_job(
        jobs=jobs, worker_id="w3", lease_seconds=30,
        now=NOW + timedelta(seconds=backoff + 1),
    )
    assert claimed_late is not None
    assert claimed_late["id"] == job["id"]
    assert claimed_late["status"] == "running"
    assert claimed_late["attempt_count"] == 2


# ---------------------------------------------------------------------------
# complete_job
# ---------------------------------------------------------------------------

def test_complete_job_marks_succeeded_and_releases_lease():
    _, jobs = enqueue_job(
        jobs=[], account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="a", now=NOW,
    )
    claimed, jobs = claim_job(jobs=jobs, worker_id="w1", lease_seconds=30, now=NOW)
    done_at = NOW + timedelta(seconds=5)
    completed, jobs = complete_job(jobs=jobs, job_id=claimed["id"], now=done_at)
    assert completed is not None
    assert completed["status"] == "succeeded"
    assert completed["lease_owner"] is None
    assert completed["lease_expires_at"] is None
    assert completed["finished_at"] == done_at


def test_complete_job_unknown_id_returns_none():
    completed, jobs = complete_job(jobs=[], job_id=999, now=NOW)
    assert completed is None


# ---------------------------------------------------------------------------
# fail_job
# ---------------------------------------------------------------------------

def test_fail_job_retryable_below_max_attempts():
    _, jobs = enqueue_job(
        jobs=[], account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="a", now=NOW,
    )
    claimed, jobs = claim_job(jobs=jobs, worker_id="w1", lease_seconds=30, now=NOW)
    failed, jobs = fail_job(
        jobs=jobs, job_id=claimed["id"], error_message="transient error", now=NOW,
    )
    assert failed is not None
    assert failed["status"] == "retryable_failed"
    assert failed["attempt_count"] == 1
    expected_backoff = compute_backoff_seconds(attempt=1)
    assert failed["available_at"] == NOW + timedelta(seconds=expected_backoff)
    assert failed["sanitized_error_message"] == "transient error"
    assert failed["lease_owner"] is None
    assert failed["lease_expires_at"] is None
    assert failed["finished_at"] is None


def test_fail_job_terminal_at_max_attempts():
    """After max_allowed_attempts() claims, failure is terminal."""
    _, jobs = enqueue_job(
        jobs=[], account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="a", now=NOW,
    )
    job_id = jobs[0]["id"]
    current = NOW
    last_failed = None
    for i in range(max_allowed_attempts()):
        # advance well past any backoff (max backoff is 60s)
        current = current + timedelta(seconds=120)
        claimed, jobs = claim_job(
            jobs=jobs, worker_id=f"w{i}", lease_seconds=30, now=current,
        )
        assert claimed is not None
        last_failed, jobs = fail_job(
            jobs=jobs, job_id=job_id, error_message=f"err{i}", now=current,
        )
    assert last_failed["status"] == "terminal_failed"
    assert last_failed["attempt_count"] == max_allowed_attempts()
    assert last_failed["finished_at"] == current
    assert last_failed["lease_expires_at"] is None
    # terminal job is no longer claimable
    claimed_again, jobs = claim_job(
        jobs=jobs, worker_id="wx", lease_seconds=30,
        now=current + timedelta(seconds=9999),
    )
    assert claimed_again is None


# ---------------------------------------------------------------------------
# recover_expired_leases
# ---------------------------------------------------------------------------

def test_recover_expired_leases_resets_stuck_running_to_queued():
    _, jobs = enqueue_job(
        jobs=[], account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="a", now=NOW,
    )
    claimed, jobs = claim_job(jobs=jobs, worker_id="w1", lease_seconds=30, now=NOW)
    # lease expires at NOW+30; advance well past it
    recovered_count, jobs = recover_expired_leases(
        jobs=jobs, now=NOW + timedelta(seconds=120),
    )
    assert recovered_count == 1
    assert jobs[0]["status"] == "queued"
    assert jobs[0]["lease_owner"] is None
    assert jobs[0]["lease_expires_at"] is None


def test_recover_expired_leases_skips_active_leases():
    _, jobs = enqueue_job(
        jobs=[], account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="a", now=NOW,
    )
    _, jobs = claim_job(jobs=jobs, worker_id="w1", lease_seconds=30, now=NOW)
    # lease still active at NOW+10
    recovered_count, jobs = recover_expired_leases(
        jobs=jobs, now=NOW + timedelta(seconds=10),
    )
    assert recovered_count == 0
    assert jobs[0]["status"] == "running"


def test_recover_expired_leases_ignores_non_running_jobs():
    _, jobs = enqueue_job(
        jobs=[], account_id=1, job_type="recalculate_metric",
        target_type="video_color", target_id="a", now=NOW,
    )
    # queued job (never claimed) is not recoverable
    recovered_count, jobs = recover_expired_leases(
        jobs=jobs, now=NOW + timedelta(seconds=9999),
    )
    assert recovered_count == 0
    assert jobs[0]["status"] == "queued"
