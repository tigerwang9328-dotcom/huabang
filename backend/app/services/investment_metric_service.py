"""Normalize retained LifeData JSON into long-lived investment facts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Mapping

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.life_data import InvestmentMetricSnapshot
from app.services.life_data_analysis_service import (
    _analyze_capture,
    _capture_value,
    _demographics,
    _materials,
    _number,
    _select_summary_metric,
)


REGION_MODULES = {
    "ProvinceDistribution": ("region_province", "province_resident"),
    "CityDistribution": ("region_city", "city_resident"),
}


@dataclass(frozen=True)
class MetricFact:
    account_id: str
    stat_start: date
    stat_end: date
    dimension_type: str
    dimension_key: str
    dimension_label: str
    captured_at: datetime
    attribution_quality: str
    source_capture_ids: list[int]
    input_hash: str = ""
    spend_fen: int | None = None
    ad_orders: int | None = None
    ad_pay_gmv_fen: int | None = None
    pay_gmv_fen: int | None = None
    verified_gmv_fen: int | None = None
    verified_count: int | None = None
    refund_gmv_fen: int | None = None
    plays: int | None = None
    interactions: int | None = None
    completion_rate: float | None = None
    metrics_extra: dict[str, Any] = field(default_factory=dict)


def _walk(value: Any):
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, Mapping):
            yield current
            pending.extend(reversed(list(current.values())))
        elif isinstance(current, list):
            pending.extend(reversed(current))


def _period(request_payload: Any, captured_at: datetime) -> tuple[date, date]:
    for row in _walk(request_payload):
        start = row.get("start_date")
        end = row.get("end_date")
        if isinstance(start, str) and isinstance(end, str):
            try:
                return date.fromisoformat(start), date.fromisoformat(end)
            except ValueError:
                continue
    fallback = captured_at.date()
    return fallback, fallback


def _rows_below_named_module(value: Any, module_name: str) -> Iterable[Mapping[str, Any]]:
    for row in _walk(value):
        module = row.get(module_name)
        if not isinstance(module, Mapping):
            continue
        data = module.get("data")
        if isinstance(data, list):
            yield from (item for item in data if isinstance(item, Mapping))


def _hash_fact(fact: MetricFact) -> str:
    payload = asdict(fact)
    payload.pop("input_hash", None)
    payload.pop("source_capture_ids", None)
    payload.pop("captured_at", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _with_hash(fact: MetricFact) -> MetricFact:
    values = asdict(fact)
    values["input_hash"] = _hash_fact(fact)
    return MetricFact(**values)


def normalize_capture(capture: Any) -> list[MetricFact]:
    """Return deterministic facts without mutating or persisting the raw capture."""

    capture_id = int(_capture_value(capture, "id"))
    account_id = str(_capture_value(capture, "account_id"))
    captured_at = _capture_value(capture, "captured_at")
    stat_start, stat_end = _period(
        _capture_value(capture, "request_payload", {}), captured_at
    )
    response = _capture_value(capture, "response_payload", {})
    analysis = _analyze_capture(capture)
    quality = "exact" if analysis.exact_link else "period_estimate"
    facts: list[MetricFact] = []

    metrics = {
        name: _select_summary_metric([analysis], name)[0]
        for name in (
            "spend_fen",
            "ad_orders",
            "ad_pay_gmv_fen",
            "pay_gmv_fen",
            "verified_gmv_fen",
            "verified_count",
            "refund_gmv_fen",
            "plays",
        )
    }
    if any(value is not None for value in metrics.values()):
        facts.append(
            MetricFact(
                account_id=account_id,
                stat_start=stat_start,
                stat_end=stat_end,
                dimension_type="account",
                dimension_key=account_id,
                dimension_label="账户整体",
                captured_at=captured_at,
                attribution_quality=quality,
                source_capture_ids=[capture_id],
                **metrics,
            )
        )

    for module_name, (dimension_type, label_key) in REGION_MODULES.items():
        for row in _rows_below_named_module(response, module_name):
            label = row.get(label_key)
            spend = _number(row.get("sub_ad_cost"))
            if not label or spend is None:
                continue
            facts.append(
                MetricFact(
                    account_id=account_id,
                    stat_start=stat_start,
                    stat_end=stat_end,
                    dimension_type=dimension_type,
                    dimension_key=str(label),
                    dimension_label=str(label),
                    spend_fen=spend,
                    captured_at=captured_at,
                    attribution_quality="period_estimate",
                    source_capture_ids=[capture_id],
                    metrics_extra={"spend_rate": row.get("sub_ad_cost_rate")},
                )
            )

    for row in _materials(analysis.rows):
        key = row.get("item_id") or row.get("title")
        facts.append(
            MetricFact(
                account_id=account_id,
                stat_start=stat_start,
                stat_end=stat_end,
                dimension_type="material",
                dimension_key=str(key),
                dimension_label=str(row.get("title") or key),
                spend_fen=row.get("ad_cost_fen"),
                ad_pay_gmv_fen=row.get("ad_pay_gmv_fen"),
                plays=row.get("play_count"),
                captured_at=captured_at,
                attribution_quality="period_estimate",
                source_capture_ids=[capture_id],
            )
        )

    for row in _demographics(analysis.rows):
        age = str(row["age"])
        facts.append(
            MetricFact(
                account_id=account_id,
                stat_start=stat_start,
                stat_end=stat_end,
                dimension_type="audience_age_gender",
                dimension_key=age,
                dimension_label=age,
                spend_fen=(row.get("male_cost_fen") or 0) + (row.get("female_cost_fen") or 0),
                captured_at=captured_at,
                attribution_quality="period_estimate",
                source_capture_ids=[capture_id],
                metrics_extra={
                    "male_spend_fen": row.get("male_cost_fen") or 0,
                    "female_spend_fen": row.get("female_cost_fen") or 0,
                },
            )
        )

    return [_with_hash(fact) for fact in facts]


async def persist_metric_snapshots(
    db: AsyncSession,
    account_id: str,
    captures: Iterable[Any],
) -> list[int]:
    """Persist normalized facts idempotently and return newly inserted IDs."""

    inserted: list[int] = []
    for capture in captures:
        if str(_capture_value(capture, "account_id")) != account_id:
            continue
        for fact in normalize_capture(capture):
            statement = (
                pg_insert(InvestmentMetricSnapshot)
                .values(**asdict(fact))
                .on_conflict_do_nothing(constraint="uq_investment_metric_snapshot_input")
                .returning(InvestmentMetricSnapshot.id)
            )
            value = (await db.execute(statement)).scalar_one_or_none()
            if value is not None:
                inserted.append(int(value))
    return inserted
