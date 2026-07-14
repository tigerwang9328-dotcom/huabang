from datetime import date, datetime, timezone

import pytest

from app.services.member_segment_service import (
    DEFAULT_MEMBER_SEGMENT_RULES,
    build_member_segment_result,
    merge_member_segment_rules,
    normalize_member_segment_store_codes,
    resolve_member_segment_rebuild_date,
    snapshot_key,
)


def _metrics(**overrides):
    base = {
        "member_no": "VIP001",
        "store_code": "285204",
        "current_balance": 0,
        "total_amount": 0,
        "total_count": 0,
        "recency_days": 10,
        "avg_order_value": 0,
        "current_period_orders": 0,
        "previous_period_orders": 0,
        "ticket_history_days": 43,
        "avg_discount_rate": None,
        "discount_order_count": 0,
        "return_rate": None,
        "return_orders": 0,
        "sales_order_count": 0,
        "latest_recharge_date": None,
        "days_since_recharge": None,
        "post_recharge_order_count": 0,
        "gross_margin": None,
        "cost_coverage": 0,
        "preferences": [],
        "suggested_products": [],
        "candidate_guide_ids": [],
    }
    base.update(overrides)
    return base


def _codes(items):
    return {item["code"] for item in items}


def test_member_can_receive_multiple_labels_with_evidence():
    result = build_member_segment_result(
        _metrics(
            current_balance=8000,
            total_amount=30000,
            total_count=30,
            avg_order_value=1000,
            recency_days=120,
        ),
        date(2026, 7, 14),
    )

    assert {"HIGH_VALUE", "HIGH_BALANCE", "HIGH_REPURCHASE", "HIGH_AOV", "DORMANT"} <= _codes(result["labels"])
    assert all(item["calc_date"] == "2026-07-14" for item in result["labels"])
    assert all(item["rule_version"] for item in result["labels"])
    assert all(item["evidence"] for item in result["labels"])


def test_ninety_day_boundary_creates_dormant_and_high_value_risk():
    result = build_member_segment_result(
        _metrics(total_amount=15000, recency_days=90), date(2026, 7, 14)
    )

    assert "DORMANT" in _codes(result["labels"])
    assert "HIGH_VALUE_INACTIVE" in _codes(result["risks"])


def test_frequency_decline_requires_full_comparison_history():
    pending = build_member_segment_result(
        _metrics(
            ticket_history_days=179,
            previous_period_orders=10,
            current_period_orders=2,
        ),
        date(2026, 7, 14),
    )
    ready = build_member_segment_result(
        _metrics(
            ticket_history_days=180,
            previous_period_orders=10,
            current_period_orders=2,
        ),
        date(2026, 7, 14),
    )

    assert "FREQUENCY_DECLINE" not in _codes(pending["risks"])
    assert pending["data_quality"]["frequency_trend"]["status"] == "pending_data"
    assert "FREQUENCY_DECLINE" in _codes(ready["risks"])


def test_recharge_without_second_consumption_becomes_risk():
    result = build_member_segment_result(
        _metrics(
            latest_recharge_date="2026-06-01",
            days_since_recharge=43,
            post_recharge_order_count=1,
        ),
        date(2026, 7, 14),
    )

    assert "RECHARGE_NO_SECOND_CONSUME" in _codes(result["risks"])


def test_very_old_recharge_is_not_an_actionable_wakeup_risk():
    result = build_member_segment_result(
        _metrics(
            latest_recharge_date="2025-01-01",
            days_since_recharge=400,
            post_recharge_order_count=0,
        ),
        date(2026, 7, 14),
    )

    assert "RECHARGE_NO_SECOND_CONSUME" not in _codes(result["risks"])


def test_negative_balance_is_isolated_as_risk():
    result = build_member_segment_result(
        _metrics(current_balance=-120), date(2026, 7, 14)
    )

    assert "NEGATIVE_BALANCE" in _codes(result["risks"])
    assert "HIGH_BALANCE" not in _codes(result["labels"])


def test_discount_and_return_risks_require_observed_orders():
    result = build_member_segment_result(
        _metrics(
            avg_discount_rate=0.5,
            discount_order_count=3,
            return_rate=0.3,
            return_orders=2,
            sales_order_count=4,
        ),
        date(2026, 7, 14),
    )

    assert {"EXCESSIVE_DISCOUNT", "RETURN_ANOMALY"} <= _codes(result["risks"])


def test_high_margin_is_not_assigned_without_cost_coverage():
    pending = build_member_segment_result(
        _metrics(gross_margin=0.8, cost_coverage=0.8), date(2026, 7, 14)
    )
    ready = build_member_segment_result(
        _metrics(gross_margin=0.8, cost_coverage=0.96), date(2026, 7, 14)
    )

    assert "HIGH_MARGIN" not in _codes(pending["labels"])
    assert pending["data_quality"]["gross_margin"]["status"] == "pending_data"
    assert "HIGH_MARGIN" in _codes(ready["labels"])
    assert [item["code"] for item in ready["labels"]].count("HIGH_MARGIN") == 1


def test_wakeup_candidate_never_auto_assigns_unreliable_guide():
    result = build_member_segment_result(
        _metrics(
            current_balance=9000,
            recency_days=120,
            candidate_guide_ids=["G001"],
        ),
        date(2026, 7, 14),
    )

    assert result["is_wakeup_candidate"] is True
    assert result["responsibility_status"] == "unconfirmed"
    assert result["responsible_employee_no"] is None
    assert result["candidate_guide_ids"] == ["G001"]


def test_rules_can_be_overridden_without_dropping_defaults():
    rules = merge_member_segment_rules({"high_balance_amount": 1000})
    assert rules["high_balance_amount"] == 1000
    assert rules["sleeping_days"] == DEFAULT_MEMBER_SEGMENT_RULES["sleeping_days"]


def test_invalid_rule_values_fall_back_to_safe_defaults():
    rules = merge_member_segment_rules({
        "high_value_amount": 0,
        "high_balance_amount": 0,
        "high_avg_order_value": 0,
        "frequency_period_days": 0,
        "frequency_baseline_min_orders": 0,
        "frequency_decline_ratio": -1,
        "gross_margin_min_coverage": 2,
    })
    assert rules["high_value_amount"] == DEFAULT_MEMBER_SEGMENT_RULES["high_value_amount"]
    assert rules["high_balance_amount"] == DEFAULT_MEMBER_SEGMENT_RULES["high_balance_amount"]
    assert rules["high_avg_order_value"] == DEFAULT_MEMBER_SEGMENT_RULES["high_avg_order_value"]
    assert rules["frequency_period_days"] == DEFAULT_MEMBER_SEGMENT_RULES["frequency_period_days"]
    assert rules["frequency_baseline_min_orders"] == DEFAULT_MEMBER_SEGMENT_RULES["frequency_baseline_min_orders"]
    assert rules["frequency_decline_ratio"] == DEFAULT_MEMBER_SEGMENT_RULES["frequency_decline_ratio"]
    assert rules["gross_margin_min_coverage"] == DEFAULT_MEMBER_SEGMENT_RULES["gross_margin_min_coverage"]


def test_invalid_cross_field_rule_ranges_are_clamped_to_valid_pairs():
    rules = merge_member_segment_rules({
        "sleeping_days": 180,
        "churn_risk_days": 90,
        "recharge_no_second_consume_days": 60,
        "recharge_risk_lookback_days": 30,
    })
    assert rules["churn_risk_days"] == 180
    assert rules["recharge_risk_lookback_days"] == 60

    large_rules = merge_member_segment_rules({
        "sleeping_days": 300,
        "churn_risk_days": 200,
        "recharge_no_second_consume_days": 300,
        "recharge_risk_lookback_days": 200,
    })
    assert large_rules["churn_risk_days"] == 300
    assert large_rules["recharge_risk_lookback_days"] == 300


def test_snapshot_key_is_idempotent_per_date_and_member():
    assert snapshot_key(date(2026, 7, 14), "VIP001") == "2026-07-14:VIP001"


def test_rebuild_date_is_beijing_today_and_rejects_historical_recalculation():
    now = datetime(2026, 7, 13, 22, 30, tzinfo=timezone.utc)
    assert resolve_member_segment_rebuild_date(None, now=now) == date(2026, 7, 14)
    assert resolve_member_segment_rebuild_date(date(2026, 7, 14), now=now) == date(2026, 7, 14)
    with pytest.raises(ValueError, match="仅支持重算北京时间当天"):
        resolve_member_segment_rebuild_date(date(2026, 7, 13), now=now)


def test_explicit_empty_store_scope_never_falls_back_to_company_scope():
    assert normalize_member_segment_store_codes([]) == []
    assert "285204" in normalize_member_segment_store_codes(None)
