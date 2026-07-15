from datetime import date
from decimal import Decimal

import pytest
import app.services.command_center_service as command_center_service

from app.services.command_center_service import (
    allocate_fifo_inventory,
    build_metric,
    build_template_summary,
    derive_metric_statuses,
    inventory_warning_source_id,
    preserve_trusted_value,
    get_command_center_snapshot,
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
        sales={
            "etl_at": "2026-07-13T20:00:00Z",
            "is_cost_complete": True,
            "cost_coverage_rate": Decimal("0"),
            "total_sales_amount": 0,
        },
        ticket={"synced_at": "2026-07-13T20:00:00Z"},
        inventory={"updated_at": "2026-07-13T20:00:00Z", "age_unknown_qty": 0},
        members={"updated_at": "2026-07-13T20:00:00Z"},
    )

    assert statuses["gross_profit"] == "ready"
    assert statuses["gross_margin"] == "pending_data"


def test_positive_company_sales_marks_gross_margin_with_cost_status():
    statuses = derive_metric_statuses(
        sales={
            "etl_at": "2026-07-13T20:00:00Z",
            "is_cost_complete": True,
            "cost_coverage_rate": Decimal("1"),
            "total_sales_amount": 8521,
        },
        ticket={"synced_at": "2026-07-13T20:00:00Z"},
        inventory={"updated_at": "2026-07-13T20:00:00Z", "age_unknown_qty": 0},
        members={"updated_at": "2026-07-13T20:00:00Z"},
    )

    assert statuses["gross_margin"] == "ready"


def test_incomplete_cost_marks_positive_sales_margin_estimated():
    statuses = derive_metric_statuses(
        sales={
            "etl_at": "2026-07-13T20:00:00Z",
            "is_cost_complete": False,
            "cost_coverage_rate": Decimal("1"),
            "total_sales_amount": 8521,
        },
        ticket={"synced_at": "2026-07-13T20:00:00Z"},
        inventory={"updated_at": "2026-07-13T20:00:00Z", "age_unknown_qty": 0},
        members={"updated_at": "2026-07-13T20:00:00Z"},
    )

    assert statuses["gross_profit"] == "estimated"
    assert statuses["gross_margin"] == "estimated"


def test_partial_standard_price_coverage_overrides_stale_complete_flag():
    statuses = derive_metric_statuses(
        sales={
            "etl_at": "2026-07-13T20:00:00Z",
            "is_cost_complete": True,
            "cost_coverage_rate": Decimal("0.948"),
            "total_sales_amount": 18066,
        },
        ticket={"synced_at": "2026-07-13T20:00:00Z"},
        inventory={"updated_at": "2026-07-13T20:00:00Z", "age_unknown_qty": 0},
        members={"updated_at": "2026-07-13T20:00:00Z"},
    )

    assert statuses["gross_profit"] == "estimated"
    assert statuses["gross_margin"] == "estimated"


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmed", [True, False])
async def test_daily_command_center_refreshes_finance_only_after_confirmed_sales(
    monkeypatch, confirmed
):
    events = []

    class Result:
        def scalar(self):
            return True

    class Db:
        commit_count = 0

        async def execute(self, *_args, **_kwargs):
            return Result()

        async def commit(self):
            self.commit_count += 1
            events.append("commit")

    async def record(name, value=None):
        events.append(name)
        return value

    monkeypatch.setattr(
        command_center_service,
        "rebuild_inventory_age",
        lambda *_args, **_kwargs: record("inventory_age", {}),
    )
    monkeypatch.setattr(
        command_center_service,
        "rebuild_inventory_warnings",
        lambda *_args, **_kwargs: record("inventory_warnings", {}),
    )
    monkeypatch.setattr(
        command_center_service,
        "create_inventory_warning_task_drafts",
        lambda *_args, **_kwargs: record("inventory_drafts", []),
    )
    monkeypatch.setattr(
        command_center_service,
        "rebuild_confirmed_sales_dws",
        lambda *_args, **_kwargs: record("confirmed_sales", confirmed),
    )
    monkeypatch.setattr(
        command_center_service,
        "build_boss_snapshot",
        lambda *_args, **_kwargs: record("snapshot", {}),
    )
    monkeypatch.setattr(
        command_center_service,
        "_persist_rule_results",
        lambda *_args, **_kwargs: record("persist_rules", 0),
    )

    class Finance:
        async def rebuild_finance_daily(self, *_args, **_kwargs):
            return await record("finance", 1)

    class Engine:
        async def run_all(self, *_args, **_kwargs):
            return await record("rules", {"results": []})

        async def create_task_drafts(self, *_args, **_kwargs):
            return await record("rule_drafts", [])

    monkeypatch.setattr(command_center_service, "DwdToDws", lambda: Finance())
    monkeypatch.setattr("app.services.rule_engine.RuleEngine", Engine)

    db = Db()
    await command_center_service.run_daily_command_center(
        db, date(2026, 7, 14), date(2026, 7, 15)
    )

    expected_prefix = [
        "inventory_age",
        "inventory_warnings",
        "inventory_drafts",
        "confirmed_sales",
    ]
    assert events[:4] == expected_prefix
    assert ("finance" in events) is confirmed
    if confirmed:
        assert events.index("confirmed_sales") < events.index("finance") < events.index("snapshot")
    assert events[-1] == "commit"
    assert db.commit_count == 1


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


class _FakeMappings:
    def __init__(self, first=None, rows=None):
        self._first = first
        self._rows = rows or []

    def first(self):
        return self._first

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, first=None, rows=None):
        self._mappings = _FakeMappings(first=first, rows=rows)

    def mappings(self):
        return self._mappings


class _SnapshotDb:
    def __init__(self, report):
        self._results = [
            _FakeResult(first=report),
            _FakeResult(rows=[]),
            _FakeResult(rows=[]),
        ]

    async def execute(self, *_args, **_kwargs):
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_command_center_snapshot_exposes_mobile_first_screen_counts():
    report = {
        "report_date": date(2026, 7, 13),
        "source_freshness": {},
        "metric_status": {},
        "major_exception_count": 12,
        "pending_task_count": 7,
    }

    snapshot = await get_command_center_snapshot(_SnapshotDb(report), report["report_date"])

    assert snapshot["core_metrics"]["major_exception_count"]["value"] == 12
    assert snapshot["core_metrics"]["pending_task_count"]["value"] == 7


@pytest.mark.asyncio
async def test_command_center_snapshot_uses_gross_margin_status():
    report = {
        "report_date": date(2026, 7, 13),
        "source_freshness": {},
        "metric_status": {
            "gross_profit": "ready",
            "gross_margin": "pending_data",
        },
        "gross_profit": Decimal("6346.32"),
        "gross_margin": Decimal("0.7448"),
    }

    snapshot = await get_command_center_snapshot(_SnapshotDb(report), report["report_date"])

    assert snapshot["core_metrics"]["gross_profit"]["status"] == "ready"
    assert snapshot["core_metrics"]["gross_margin"]["status"] == "pending_data"
