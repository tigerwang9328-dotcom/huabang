"""Task 6: PostgreSQL persistent recalculation job primitives.

Implements v3.1 §2.5 calculation_jobs:
- deduplication_key computation (deterministic, account-isolated)
- lease expiry detection
- exponential backoff with 60s cap
- failure status determination (retryable vs terminal)
- max attempts = 5 (same video same analysis type per batch)
- job lifecycle pure functions: enqueue / claim / complete / fail / recover
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any


class CalculationJobError(ValueError):
    """A calculation job request violates v3.1 §2.5."""


_MAX_ATTEMPTS = 5
_BACKOFF_CAP_SECONDS = 60

# Statuses that make a job eligible for claiming (available for work).
# A retryable_failed job whose backoff (available_at) has elapsed is also
# claimable, mirroring ``FOR UPDATE SKIP LOCKED`` over the available queue.
_CLAIMABLE_STATUSES = ("queued", "retryable_failed")


def compute_deduplication_key(
    *, account_id: int, job_type: str, target_type: str, target_id: str
) -> str:
    """Compute a deterministic deduplication key for a calculation job.

    Same (account_id, job_type, target_type, target_id) always produces
    the same key, enabling idempotent enqueue.
    """

    payload = json.dumps(
        {
            "account_id": account_id,
            "job_type": job_type,
            "target_type": target_type,
            "target_id": target_id,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_lease_expired(job: dict, *, now: datetime) -> bool:
    """Check if a running job's lease has expired.

    Non-running jobs (queued, succeeded, failed) don't have active leases.
    """

    if job.get("status") != "running":
        return False
    lease_expires_at = job.get("lease_expires_at")
    if lease_expires_at is None:
        return False
    # Handle both timezone-aware and naive datetimes
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now
    lease_naive = lease_expires_at.replace(tzinfo=None) if hasattr(lease_expires_at, "tzinfo") and lease_expires_at.tzinfo else lease_expires_at
    return lease_naive <= now_naive


def compute_backoff_seconds(*, attempt: int) -> int:
    """Exponential backoff: min(60, 2^attempt) seconds.

    attempt=0 -> 1s, attempt=1 -> 2s, ..., attempt=6+ -> 60s (capped)
    """

    return min(_BACKOFF_CAP_SECONDS, 2 ** attempt)


def determine_failure_status(*, attempt_count: int, max_attempts: int) -> str:
    """Determine if a failed job should be retried or terminated.

    Returns 'retryable_failed' if below max_attempts, 'terminal_failed' otherwise.
    """

    if attempt_count >= max_attempts:
        return "terminal_failed"
    return "retryable_failed"


def max_allowed_attempts() -> int:
    """v3.1: same video same analysis type max 5 failures per batch."""

    return _MAX_ATTEMPTS


def _normalize_dt(value):
    """Strip tzinfo for safe cross-type comparison (treats all as UTC-naive)."""

    if value is None:
        return None
    if hasattr(value, "tzinfo") and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


def enqueue_job(
    *,
    jobs,
    account_id,
    job_type,
    target_type,
    target_id,
    now,
):
    """Enqueue a calculation job, deduplicating by deduplication_key.

    Pure function: receives the current jobs list and returns
    ``(job, updated_jobs)`` without mutating the input. If a job with the
    same deduplication_key already exists it is returned unchanged
    (idempotent enqueue); otherwise a new ``queued`` job is appended.
    """

    key = compute_deduplication_key(
        account_id=account_id,
        job_type=job_type,
        target_type=target_type,
        target_id=target_id,
    )
    for existing in jobs:
        if existing.get("deduplication_key") == key:
            return existing, jobs
    new_id = max((j.get("id", 0) for j in jobs), default=0) + 1
    new_job = {
        "id": new_id,
        "account_id": account_id,
        "job_type": job_type,
        "target_type": target_type,
        "target_id": target_id,
        "deduplication_key": key,
        "requested_by": None,
        "status": "queued",
        "attempt_count": 0,
        "available_at": now,
        "lease_owner": None,
        "lease_expires_at": None,
        "started_at": None,
        "finished_at": None,
        "sanitized_error_message": None,
        "created_at": now,
    }
    return new_job, [*jobs, new_job]


def claim_job(
    *,
    jobs,
    worker_id,
    lease_seconds,
    now,
):
    """Claim the earliest available job (``FOR UPDATE SKIP LOCKED`` semantics).

    Pure function: picks the job with the earliest ``available_at`` among
    claimable statuses (``queued`` or ``retryable_failed`` whose backoff has
    elapsed), marks it ``running``, assigns the lease, and increments
    ``attempt_count``. Running/succeeded/terminal jobs are skipped (locked).

    Returns ``(claimed_job | None, updated_jobs)``.
    """

    now_naive = _normalize_dt(now)
    candidates = [
        j for j in jobs
        if j.get("status") in _CLAIMABLE_STATUSES
        and j.get("available_at") is not None
        and _normalize_dt(j["available_at"]) <= now_naive
    ]
    if not candidates:
        return None, jobs
    chosen = min(
        candidates,
        key=lambda j: (_normalize_dt(j["available_at"]), j.get("id", 0)),
    )
    updated = {
        **chosen,
        "status": "running",
        "lease_owner": worker_id,
        "lease_expires_at": now + timedelta(seconds=lease_seconds),
        "started_at": chosen.get("started_at") or now,
        "attempt_count": chosen.get("attempt_count", 0) + 1,
    }
    new_jobs = [updated if j.get("id") == chosen["id"] else j for j in jobs]
    return updated, new_jobs


def complete_job(
    *,
    jobs,
    job_id,
    now,
):
    """Mark a job as succeeded and release its lease.

    Pure function: returns ``(job | None, updated_jobs)``. ``None`` if the
    job_id is not found.
    """

    for j in jobs:
        if j.get("id") == job_id:
            updated = {
                **j,
                "status": "succeeded",
                "lease_owner": None,
                "lease_expires_at": None,
                "finished_at": now,
            }
            new_jobs = [updated if x.get("id") == job_id else x for x in jobs]
            return updated, new_jobs
    return None, jobs


def fail_job(
    *,
    jobs,
    job_id,
    error_message,
    now,
):
    """Mark a job as failed, deciding retryable vs terminal.

    Below ``max_attempts`` -> ``retryable_failed`` with
    ``available_at = now + backoff(attempt_count)`` (delays re-claim).
    At/above ``max_attempts`` -> ``terminal_failed`` with ``finished_at = now``.
    The lease is always released.

    Pure function: returns ``(job | None, updated_jobs)``.
    """

    for j in jobs:
        if j.get("id") == job_id:
            attempt_count = j.get("attempt_count", 0)
            status = determine_failure_status(
                attempt_count=attempt_count,
                max_attempts=max_allowed_attempts(),
            )
            if status == "retryable_failed":
                backoff = compute_backoff_seconds(attempt=attempt_count)
                available_at = now + timedelta(seconds=backoff)
                finished_at = None
            else:
                available_at = j.get("available_at")
                finished_at = now
            updated = {
                **j,
                "status": status,
                "sanitized_error_message": error_message,
                "lease_owner": None,
                "lease_expires_at": None,
                "available_at": available_at,
                "finished_at": finished_at,
            }
            new_jobs = [updated if x.get("id") == job_id else x for x in jobs]
            return updated, new_jobs
    return None, jobs


def recover_expired_leases(
    *,
    jobs,
    now,
):
    """Reset running jobs whose leases have expired back to ``queued``.

    Pure function: returns ``(recovered_count, updated_jobs)``. Non-running
    jobs and running jobs with active leases are left untouched.
    """

    recovered = 0
    new_jobs = []
    for j in jobs:
        if is_lease_expired(j, now=now):
            new_jobs.append({
                **j,
                "status": "queued",
                "lease_owner": None,
                "lease_expires_at": None,
            })
            recovered += 1
        else:
            new_jobs.append(j)
    return recovered, new_jobs
