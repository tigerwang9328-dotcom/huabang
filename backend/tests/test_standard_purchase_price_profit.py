import inspect
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.api.v1 import finance as finance_api
from app.services.ai_diagnosis_service import _can_assert_operating_profit
from app.services.command_center_service import build_boss_snapshot, get_command_center_snapshot
from app.services.profit_service import REQUIRED_EXPENSE_TYPES, calculate_profit
from app.services.report_service import ReportService


REPORT_DATE = date(2026, 7, 14)


def _profit(**overrides):
    values = {
        "period_start": REPORT_DATE,
        "period_end": REPORT_DATE,
        "net_sales": Decimal("1000"),
        "cost_of_goods": Decimal("400"),
        "is_cost_complete": True,
        "expenses": [],
    }
    values.update(overrides)
    return calculate_profit(**values)


def test_missing_expenses_return_estimated_operating_profit():
    result = _profit()

    assert result.operating_profit == Decimal("600")
    assert result.operating_margin == Decimal("0.6")
    assert result.operating_profit_status == "estimated"
    assert result.missing_expense_types == REQUIRED_EXPENSE_TYPES


def test_finance_daily_preserves_completed_dingtalk_expenses_when_dwd_is_empty():
    source = (
        Path(__file__).resolve().parents[1]
        / "app/services/etl/dwd_to_dws.py"
    ).read_text(encoding="utf-8")

    assert "if not expenses:" in source
    assert "FROM finance_expense_records" in source
    assert "'other' AS expense_type" in source
    assert "('COMPLETED','APPROVED','FINISHED')" in source


def test_missing_standard_price_coverage_keeps_profit_estimated():
    result = _profit(is_cost_complete=False)

    assert result.gross_profit == Decimal("600")
    assert result.gross_profit_status == "estimated"
    assert result.operating_profit == Decimal("600")
    assert result.operating_profit_status == "estimated"


def test_missing_gross_profit_keeps_operating_profit_pending():
    result = _profit(cost_of_goods=None, is_cost_complete=False)

    assert result.gross_profit is None
    assert result.operating_profit is None
    assert result.operating_profit_status == "pending_data"


def test_estimated_loss_is_visible_but_not_assertable_by_ai():
    result = _profit(cost_of_goods=Decimal("1200"))

    assert result.operating_profit == Decimal("-200")
    assert _can_assert_operating_profit({
        "operating_profit": result.operating_profit,
        "operating_profit_status": result.operating_profit_status,
        "is_expense_complete": False,
        "finance_approved": False,
    }) is False


def test_command_center_report_and_finance_keep_estimated_value_visible():
    command_build = inspect.getsource(build_boss_snapshot)
    command_read = inspect.getsource(get_command_center_snapshot)
    report_source = inspect.getsource(ReportService)
    finance_source = inspect.getsource(finance_api)

    assert "operating_profit_estimate" in command_build
    assert "data.get(\"operating_profit_estimate\")" in command_read
    assert 'data.get("operating_profit") if data.get("is_finance_complete") else None' not in report_source
    assert "if r.operating_profit is not None and r.is_cost_complete" not in finance_source


def test_overview_and_finance_expose_real_standard_price_coverage():
    from app.services import business_overview_service

    overview_source = inspect.getsource(business_overview_service)
    finance_source = inspect.getsource(finance_api)

    assert "is_cost_complete" in overview_source
    assert "cost_coverage_rate" in overview_source
    assert ">= 0.95" not in overview_source
    assert "1.0 if cost_complete else 0.0" not in finance_source
