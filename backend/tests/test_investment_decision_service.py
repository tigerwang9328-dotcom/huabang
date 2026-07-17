"""Guardrail tests for persisted DeepSeek investment decisions."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.investment_decision import DeepSeekInvestmentPayload
from app.services.ai_engine import AIEngine
from app.services import investment_decision_service as decision_service
from app.services.investment_decision_service import (
    ModelAdviceRejected,
    build_rule_envelope,
    investment_input_hash,
    validate_model_payload,
)


ACCOUNT_ID = "1798826701211732"


def snapshot(snapshot_id: int, **metrics):
    defaults = {
        "id": snapshot_id,
        "account_id": ACCOUNT_ID,
        "stat_start": date(2026, 7, 10),
        "stat_end": date(2026, 7, 16),
        "dimension_type": "account",
        "dimension_key": ACCOUNT_ID,
        "dimension_label": "账户整体",
        "spend_fen": None,
        "ad_pay_gmv_fen": None,
        "verified_gmv_fen": None,
        "verified_count": None,
        "refund_gmv_fen": None,
        "attribution_quality": "period_estimate",
        "input_hash": f"hash-{snapshot_id}",
    }
    defaults.update(metrics)
    return SimpleNamespace(**defaults)


def payload(**recommendation_overrides):
    recommendation = {
        "action": "reduce",
        "target_type": "account",
        "target_key": ACCOUNT_ID,
        "title": "降低无效消耗",
        "reasoning": "实际核销回报不足",
        "budget_min_fen": 3000,
        "budget_max_fen": 8000,
        "review_window_hours": 24,
        "stop_loss": "新增消耗10000分仍无新增核销时停止",
        "confidence": "medium",
        "evidence_refs": ["snapshot:1", "snapshot:2"],
    }
    recommendation.update(recommendation_overrides)
    return DeepSeekInvestmentPayload.model_validate(
        {
            "decision_summary": "降低消耗并继续观察实际核销",
            "recommendations": [recommendation],
            "pattern_observations": [],
            "data_limitations": ["素材到核销为同期归因估算"],
        }
    )


def test_missing_required_metrics_blocks_model_and_collects_more_data():
    envelope = build_rule_envelope([snapshot(1, spend_fen=114187)])

    assert envelope.block_model is True
    assert envelope.rule_recommendations[0]["action"] == "collect_more_data"
    assert envelope.attribution_quality == "missing"


def test_low_verify_roi_allows_only_safe_actions_and_caps_estimated_confidence():
    envelope = build_rule_envelope(
        [
            snapshot(1, spend_fen=114187),
            snapshot(2, verified_gmv_fen=990, refund_gmv_fen=18100),
        ]
    )

    assert envelope.block_model is False
    assert envelope.allowed_actions == frozenset({"stop", "reduce", "maintain"})
    assert envelope.max_confidence == "medium"
    assert envelope.verify_roi == 0.01


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"budget_max_fen": 30_001}, "budget"),
        ({"evidence_refs": ["snapshot:999"]}, "evidence"),
        ({"action": "increase"}, "action"),
        ({"confidence": "high"}, "confidence"),
    ],
)
def test_invalid_model_advice_is_rejected(overrides, reason):
    snapshots = [
        snapshot(1, spend_fen=114187),
        snapshot(2, verified_gmv_fen=990),
    ]
    envelope = build_rule_envelope(snapshots)

    with pytest.raises(ModelAdviceRejected, match=reason):
        validate_model_payload(payload(**overrides), envelope, max_budget_fen=30_000)


def test_input_hash_is_stable_when_snapshot_order_changes():
    left = [snapshot(2, verified_gmv_fen=990), snapshot(1, spend_fen=114187)]
    right = list(reversed(left))

    assert investment_input_hash(left) == investment_input_hash(right)


def test_rule_envelope_uses_account_totals_not_dimension_maxima():
    envelope = build_rule_envelope(
        [
            snapshot(1, spend_fen=10_000, verified_gmv_fen=20_000),
            snapshot(
                2,
                dimension_type="region",
                dimension_key="贵阳",
                spend_fen=99_000,
                verified_gmv_fen=100,
                attribution_quality="exact",
            ),
        ]
    )

    assert envelope.summary["spend_fen"] == 10_000
    assert envelope.verify_roi == 2.0
    assert envelope.attribution_quality == "period_estimate"


def test_model_call_rate_limit_uses_last_completed_model_run():
    now = datetime(2026, 7, 17, 8, 0, tzinfo=timezone.utc)

    assert decision_service.is_model_call_rate_limited(now - timedelta(minutes=59), now, 60) is True
    assert decision_service.is_model_call_rate_limited(now - timedelta(minutes=60), now, 60) is False
    assert decision_service.is_model_call_rate_limited(None, now, 60) is False


@pytest.mark.asyncio
async def test_business_advice_supports_investment_model_token_and_timeout_overrides():
    engine = AIEngine(None)
    engine._call_openai_compatible = AsyncMock(return_value={"content": "{}"})

    await engine._call_business_advice(
        "system", "user", model="deepseek-chat", max_tokens=2500, timeout_seconds=45
    )

    kwargs = engine._call_openai_compatible.await_args.kwargs
    assert kwargs["model"] == "deepseek-chat"
    assert kwargs["max_tokens"] == 2500
    assert kwargs["timeout_seconds"] == 45


def test_history_rows_include_human_decision_execution_and_fixed_outcomes():
    run = SimpleNamespace(
        id=1, stat_start=date(2026, 7, 10), stat_end=date(2026, 7, 16),
        trigger_type="period_complete", attribution_quality="period_estimate",
        status="generated", provider="deepseek", model_used="deepseek-chat",
        rule_version="v1", prompt_version="p1", fallback_reason=None, created_at=None,
    )
    recommendation = SimpleNamespace(
        id=2, decision_run_id=1, action="reduce", target_type="account",
        target_key=ACCOUNT_ID, target_label="账户整体", title="降低消耗",
        reasoning="核销ROI偏低", budget_min_fen=3000, budget_max_fen=8000,
        review_window_hours=24, stop_loss="止损", confidence="medium",
        evidence_refs=["snapshot:1"], requires_human_confirm=True, executed=True,
    )
    execution = SimpleNamespace(
        id=3, recommendation_id=2, decision="accepted", actual_budget_fen=6000,
        executed_at=datetime(2026, 7, 17, tzinfo=timezone.utc), execution_note=None,
    )
    outcome = SimpleNamespace(
        execution_record_id=3, window_hours=24,
        observed_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
        incremental_spend_fen=1000, incremental_verified_gmv_fen=1500,
        verified_roi=1.5, attribution_quality="period_estimate",
    )

    rows = decision_service.build_history_rows(
        [run], [recommendation], [execution], [outcome]
    )

    assert rows[0]["recommendations"][0]["execution"]["decision"] == "accepted"
    assert rows[0]["recommendations"][0]["outcomes"][0]["window_hours"] == 24
    assert rows[0]["recommendations"][0]["outcomes"][0]["verified_roi"] == 1.5
