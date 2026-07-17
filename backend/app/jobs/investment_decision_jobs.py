"""Scheduled investment decision generation, outcomes, and environment summaries."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.life_data import (
    InvestmentDecisionRun,
    InvestmentExecutionRecord,
    InvestmentMetricSnapshot,
    InvestmentOutcomeSnapshot,
    InvestmentRecommendation,
)
from app.services.investment_decision_service import InvestmentDecisionService
from app.services.investment_environment_service import InvestmentEnvironmentService


logger = logging.getLogger(__name__)
OUTCOME_WINDOWS = (24, 72, 168)


def due_outcome_windows(
    executed_at: datetime | None,
    now: datetime,
    *,
    existing: set[int],
) -> list[int]:
    if executed_at is None:
        return []
    if executed_at.tzinfo is None:
        executed_at = executed_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    elapsed_hours = (now - executed_at).total_seconds() / 3600
    return [window for window in OUTCOME_WINDOWS if window <= elapsed_hours and window not in existing]


def outcome_window_end(executed_at: datetime, window_hours: int) -> datetime:
    return executed_at + timedelta(hours=window_hours)


@contextmanager
def _single_process_lock(name: str):
    if fcntl is None:
        yield True
        return
    with open(f"/tmp/huabang_{name}.lock", "w") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


async def run_investment_period_generation():
    with _single_process_lock("investment_period_generation") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "locked"}
        async with AsyncSessionLocal() as db:
            result = await InvestmentDecisionService(db).generate_for_latest_period(
                settings.LIFE_DATA_ACCOUNT_ID
            )
            return {"run_id": result.run_id, "status": result.status, "cached": result.cached}


def _metric_max(rows, field: str) -> int:
    values = [getattr(item, field, None) for item in rows]
    return max((int(value) for value in values if value is not None), default=0)


async def capture_due_outcomes(now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    created = 0
    with _single_process_lock("investment_outcomes") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "locked"}
        async with AsyncSessionLocal() as db:
            executions = list(
                (
                    await db.execute(
                        select(InvestmentExecutionRecord).where(
                            InvestmentExecutionRecord.executed_at.is_not(None)
                        )
                    )
                ).scalars().all()
            )
            for execution in executions:
                existing = set(
                    (
                        await db.execute(
                            select(InvestmentOutcomeSnapshot.window_hours).where(
                                InvestmentOutcomeSnapshot.execution_record_id == execution.id
                            )
                        )
                    ).scalars().all()
                )
                windows = due_outcome_windows(execution.executed_at, now, existing=existing)
                if not windows:
                    continue
                recommendation = await db.get(InvestmentRecommendation, execution.recommendation_id)
                run = await db.get(InvestmentDecisionRun, recommendation.decision_run_id)
                baseline = list(
                    (
                        await db.execute(
                            select(InvestmentMetricSnapshot).where(
                                InvestmentMetricSnapshot.id.in_(run.source_snapshot_ids),
                                InvestmentMetricSnapshot.dimension_type == "account",
                            )
                        )
                    ).scalars().all()
                )
                for window in windows:
                    cutoff = outcome_window_end(execution.executed_at, window)
                    latest = list(
                        (
                            await db.execute(
                                select(InvestmentMetricSnapshot).where(
                                    InvestmentMetricSnapshot.account_id == run.account_id,
                                    InvestmentMetricSnapshot.dimension_type == "account",
                                    InvestmentMetricSnapshot.captured_at >= execution.executed_at,
                                    InvestmentMetricSnapshot.captured_at <= cutoff,
                                )
                            )
                        ).scalars().all()
                    )
                    spend = max(0, _metric_max(latest, "spend_fen") - _metric_max(baseline, "spend_fen"))
                    verified = max(0, _metric_max(latest, "verified_gmv_fen") - _metric_max(baseline, "verified_gmv_fen"))
                    ad_pay = max(0, _metric_max(latest, "ad_pay_gmv_fen") - _metric_max(baseline, "ad_pay_gmv_fen"))
                    refund = max(0, _metric_max(latest, "refund_gmv_fen") - _metric_max(baseline, "refund_gmv_fen"))
                    verified_count = max(0, _metric_max(latest, "verified_count") - _metric_max(baseline, "verified_count"))
                    source_ids = [int(item.id) for item in latest]
                    statement = (
                        pg_insert(InvestmentOutcomeSnapshot)
                        .values(
                            execution_record_id=execution.id,
                            window_hours=window,
                            observed_at=now,
                            incremental_spend_fen=spend,
                            incremental_ad_pay_gmv_fen=ad_pay,
                            incremental_verified_gmv_fen=verified,
                            incremental_verified_count=verified_count,
                            incremental_refund_gmv_fen=refund,
                            ad_pay_roi=round(ad_pay / spend, 2) if spend else None,
                            verified_roi=round(verified / spend, 2) if spend else None,
                            refund_adjusted_verified_roi=(
                                round(max(0, verified - refund) / spend, 2) if spend else None
                            ),
                            attribution_quality="period_estimate",
                            source_snapshot_ids=source_ids,
                        )
                        .on_conflict_do_nothing(constraint="uq_investment_outcome_window")
                    )
                    result = await db.execute(statement)
                    created += result.rowcount or 0
            await db.commit()
    return {"created": created}


async def run_daily_investment_summary(summary_date: date | None = None):
    target = summary_date or date.today()
    with _single_process_lock("investment_daily_summary") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "locked"}
        async with AsyncSessionLocal() as db:
            service = InvestmentEnvironmentService(db)
            results = []
            for lookback in (7, 30, 90):
                item = await service.summarize(
                    settings.LIFE_DATA_ACCOUNT_ID, target, lookback
                )
                results.append({"id": int(item.id), "lookback_days": lookback})
            return {"summaries": results}
