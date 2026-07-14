from datetime import date
from decimal import Decimal

from app.services.command_center_service import (
    allocate_fifo_inventory,
    build_metric,
    build_template_summary,
    derive_metric_statuses,
    inventory_warning_source_id,
    preserve_trusted_value,
)
from app.services.sales_metric_service import RETURN_SYNC_COMPLETE_SQL
from app.services.rule_engine import RuleEngine


def test_fifo_inventory_keeps_newest_batches_after_old_stock_is_sold():
    allocation = allocate_fifo_inventory(
        current_qty=Decimal("8"),
        batches=[
            (date(2026, 1, 1), Decimal("10")),
            (date(2026, 6, 1), Decimal("5")),
            (date(2026, 7, 1), Decimal("4")),
        ],
        as_of=date(2026, 7, 13),
    )

    assert allocation == {
        "qty_0_90": Decimal("8"),
        "qty_91_180": Decimal("0"),
        "qty_180_plus": Decimal("0"),
        "qty_unknown": Decimal("0"),
    }


def test_fifo_inventory_exposes_quantity_without_inbound_history():
    allocation = allocate_fifo_inventory(
        current_qty=Decimal("12"),
        batches=[(date(2026, 1, 1), Decimal("5"))],
        as_of=date(2026, 7, 13),
    )

    assert allocation["qty_180_plus"] == Decimal("5")
    assert allocation["qty_unknown"] == Decimal("7")


def test_metric_does_not_turn_missing_data_into_zero():
    metric = build_metric(None, source="online_platform", reason="线上平台待接入")

    assert metric["value"] is None
    assert metric["status"] == "pending_data"
    assert metric["display"] == "待接入"


def test_metric_does_not_mark_missing_data_as_ready():
    metric = build_metric(None, source="baison_return", status="ready")

    assert metric["value"] is None
    assert metric["status"] == "pending_data"
    assert metric["display"] == "待接入"


def test_metric_statuses_follow_each_source_freshness():
    statuses = derive_metric_statuses(
        sales={"etl_at": None, "is_cost_complete": False},
        ticket={"synced_at": None},
        inventory={"updated_at": None, "age_unknown_qty": 3},
        members={"updated_at": None},
    )

    assert statuses == {
        "sales": "stale",
        "sales_detail": "stale",
        "returns": "stale",
        "actual_pay": "stale",
        "gross_profit": "estimated",
        "gross_margin": "pending_data",
        "online_sales": "stale",
        "inventory": "stale",
        "inventory_age": "estimated",
        "vip_balance": "stale",
        "operating_profit": "pending_data",
    }


def test_zero_sales_keeps_gross_profit_ready_but_margin_pending():
    statuses = derive_metric_statuses(
        sales={"etl_at": "2026-07-13T20:00:00Z", "is_cost_complete": True, "net_sales_amount": 0},
        ticket={"synced_at": "2026-07-13T20:00:00Z"},
        inventory={"updated_at": "2026-07-13T20:00:00Z", "age_unknown_qty": 0},
        members={"updated_at": "2026-07-13T20:00:00Z"},
    )

    assert statuses["gross_profit"] == "ready"
    assert statuses["gross_margin"] == "pending_data"


def test_return_metric_is_ready_when_synced_ticket_source_reports_zero_returns():
    statuses = derive_metric_statuses(
        sales={
            "etl_at": "2026-07-13T20:00:00Z",
            "is_cost_complete": True,
        },
        ticket={
            "synced_at": "2026-07-13T20:00:00Z",
            "return_amount": 0,
            "return_sync_completed_at": "2026-07-13T20:05:00Z",
        },
        inventory={"updated_at": "2026-07-13T20:00:00Z", "age_unknown_qty": 0},
        members={"updated_at": "2026-07-13T20:00:00Z"},
    )

    assert statuses["sales_detail"] == "ready"
    assert statuses["returns"] == "ready"


def test_return_metric_stays_stale_without_a_complete_covering_sync_run():
    statuses = derive_metric_statuses(
        sales={"etl_at": "2026-07-13T20:00:00Z", "is_cost_complete": True},
        ticket={"synced_at": "2026-07-13T20:00:00Z", "return_amount": 0},
        inventory={"updated_at": "2026-07-13T20:00:00Z", "age_unknown_qty": 0},
        members={"updated_at": "2026-07-13T20:00:00Z"},
    )

    assert statuses["returns"] == "stale"


def test_return_readiness_uses_latest_overlapping_sync_run():
    assert "ORDER BY r.started_at DESC, r.id DESC" in RETURN_SYNC_COMPLETE_SQL
    assert "LIMIT 1" in RETURN_SYNC_COMPLETE_SQL
    assert "r.status='success'" in RETURN_SYNC_COMPLETE_SQL


def test_metric_rejects_unknown_status():
    try:
        build_metric(1, source="test", status="unknown")
    except ValueError as exc:
        assert "unknown metric status" in str(exc)
    else:
        raise AssertionError("invalid metric status must be rejected")


def test_stale_source_preserves_previous_trusted_value():
    assert preserve_trusted_value(0, source_ready=False, previous=18100) == 18100
    assert preserve_trusted_value(0, source_ready=True, previous=18100) == 0
    assert preserve_trusted_value(0, source_ready=False, previous=None) is None


def test_template_summary_avoids_profit_claim_when_finance_is_incomplete():
    summary = build_template_summary(
        sales=Decimal("26566"),
        gross_profit=Decimal("9000"),
        gross_margin=Decimal("0.3388"),
        finance_complete=False,
        risk_count=3,
        pending_task_count=2,
    )

    assert "销售" in summary
    assert "毛利" in summary
    assert "净利润" not in summary
    assert "赚钱" not in summary
    assert "费用未完整接入" in summary


def test_template_summary_does_not_describe_missing_sales_as_zero():
    summary = build_template_summary(
        sales=None,
        gross_profit=None,
        gross_margin=None,
        finance_complete=False,
        risk_count=0,
        pending_task_count=0,
    )

    assert "销售数据未就绪" in summary
    assert "昨日销售0元" not in summary


def test_rule_thresholds_are_read_from_business_config():
    engine = RuleEngine()
    engine.config = {"R001": {"enabled": True, "thresholds": {"warning": 5200}}}

    assert engine._threshold("R001", "warning", 3000) == 5200
    assert engine._threshold("R001", "risk", 1000) == 1000


def test_rule_task_source_id_is_stable_and_store_specific():
    engine = RuleEngine()

    first = engine._task_source_id("R006", "2026-07-12", "134681")
    repeated = engine._task_source_id("R006", "2026-07-12", "134681")
    other_store = engine._task_source_id("R006", "2026-07-12", "285702")

    assert first == repeated
    assert first != other_store
    assert 0 <= first < 2**63


def test_inventory_warning_source_id_survives_daily_warning_rebuilds():
    first = inventory_warning_source_id(
        date(2026, 7, 13), "134681", "30262T604", None, "negative"
    )
    repeated = inventory_warning_source_id(
        date(2026, 7, 13), "134681", "30262T604", None, "negative"
    )
    other_product = inventory_warning_source_id(
        date(2026, 7, 13), "134681", "31262T613", None, "negative"
    )

    assert first == repeated
    assert first != other_product
    assert 0 <= first < 2**63
