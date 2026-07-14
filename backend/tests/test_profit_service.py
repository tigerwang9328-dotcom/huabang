from datetime import date
from decimal import Decimal

import pytest

from app.models.dm import DmFinanceProfitDaily
from app.models.dwd import DwdFinanceExpense
from app.models.dws import DwsFinanceDaily
from app.services.profit_service import (
    REQUIRED_EXPENSE_TYPES,
    ExpenseAllocation,
    calculate_profit,
)


REPORT_DATE = date(2026, 7, 14)


def _expenses(*, amount="0", data_type="actual"):
    return [
        ExpenseAllocation(
            expense_type=expense_type,
            amount=Decimal(amount),
            allocation_start=REPORT_DATE,
            allocation_end=REPORT_DATE,
            data_type=data_type,
        )
        for expense_type in REQUIRED_EXPENSE_TYPES
    ]


def _calculate(expenses, **overrides):
    values = {
        "period_start": REPORT_DATE,
        "period_end": REPORT_DATE,
        "net_sales": Decimal("1000"),
        "cost_of_goods": Decimal("400"),
        "is_cost_complete": True,
        "expenses": expenses,
    }
    values.update(overrides)
    return calculate_profit(**values)


def test_required_expense_types_are_the_eight_finance_categories():
    assert REQUIRED_EXPENSE_TYPES == (
        "rent",
        "wages",
        "social_security",
        "platform_fee",
        "utilities",
        "logistics",
        "marketing",
        "other",
    )


def test_explicit_zero_amount_declares_a_required_expense_category():
    result = _calculate(_expenses(amount="0"))

    assert result.expense_coverage_rate == Decimal("1")
    assert result.missing_expense_types == ()
    assert result.total_expense == Decimal("0")
    assert result.operating_profit == Decimal("600")
    assert result.operating_profit_status == "ready"
    assert result.reasons == ()


def test_missing_required_category_keeps_operating_profit_pending():
    expenses = [
        expense for expense in _expenses(amount="10")
        if expense.expense_type != "other"
    ]

    result = _calculate(expenses)

    assert result.expense_coverage_rate == Decimal("0.875")
    assert result.missing_expense_types == ("other",)
    assert result.operating_profit is None
    assert result.operating_profit_status == "pending_data"
    assert "expense_coverage_incomplete" in result.reasons


def test_cross_period_expense_is_allocated_by_inclusive_calendar_days():
    expenses = [
        ExpenseAllocation(
            expense_type=expense_type,
            amount=Decimal("0"),
            allocation_start=date(2026, 7, 1),
            allocation_end=date(2026, 7, 31),
            data_type="actual",
        )
        for expense_type in REQUIRED_EXPENSE_TYPES
    ]
    expenses[0] = ExpenseAllocation(
        expense_type="rent",
        amount=Decimal("3100"),
        allocation_start=date(2026, 7, 1),
        allocation_end=date(2026, 7, 31),
        data_type="actual",
    )

    result = calculate_profit(
        period_start=date(2026, 7, 10),
        period_end=date(2026, 7, 19),
        net_sales=Decimal("5000"),
        cost_of_goods=Decimal("2000"),
        is_cost_complete=True,
        expenses=expenses,
    )

    assert result.expense_by_type["rent"] == Decimal("1000")
    assert result.total_expense == Decimal("1000")
    assert result.operating_profit == Decimal("2000")


def test_partial_date_coverage_is_reported_even_when_all_categories_exist():
    expenses = [
        ExpenseAllocation(
            expense_type=expense_type,
            amount=Decimal("0"),
            allocation_start=date(2026, 7, 1),
            allocation_end=date(2026, 7, 5),
            data_type="actual",
        )
        for expense_type in REQUIRED_EXPENSE_TYPES
    ]

    result = calculate_profit(
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 10),
        net_sales=Decimal("1000"),
        cost_of_goods=Decimal("400"),
        is_cost_complete=True,
        expenses=expenses,
    )

    assert result.expense_coverage_rate == Decimal("0.5")
    assert result.missing_expense_types == ()
    assert result.operating_profit is None
    assert "expense_coverage_incomplete" in result.reasons


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"is_cost_complete": False}, "cost_incomplete"),
        ({"net_sales": Decimal("0")}, "net_sales_not_positive"),
        ({"net_sales": Decimal("-1")}, "net_sales_not_positive"),
    ],
)
def test_invalid_profit_inputs_never_produce_operating_profit(overrides, reason):
    result = _calculate(_expenses(), **overrides)

    assert result.operating_profit is None
    assert result.operating_profit_status == "pending_data"
    assert reason in result.reasons


def test_all_allocated_expenses_must_be_finance_approved_actuals():
    expenses = _expenses()
    expenses[3] = ExpenseAllocation(
        expense_type="platform_fee",
        amount=Decimal("0"),
        allocation_start=REPORT_DATE,
        allocation_end=REPORT_DATE,
        data_type="estimate",
    )

    result = _calculate(expenses)

    assert result.finance_approved is False
    assert result.operating_profit is None
    assert result.operating_profit_status == "pending_data"
    assert "finance_not_approved" in result.reasons


def test_gross_profit_has_an_independent_estimated_or_ready_status():
    estimated = _calculate(_expenses(), is_cost_complete=False)
    ready = _calculate(_expenses(), is_cost_complete=True)

    assert estimated.gross_profit == Decimal("600")
    assert estimated.gross_profit_status == "estimated"
    assert ready.gross_profit == Decimal("600")
    assert ready.gross_profit_status == "ready"


def test_profit_foundation_model_columns_are_available():
    assert {"allocation_start", "allocation_end"} <= set(DwdFinanceExpense.__table__.columns.keys())

    required_rollup_columns = {
        "rent_expense",
        "wages_expense",
        "social_security_expense",
        "platform_fee_expense",
        "utilities_expense",
        "logistics_expense",
        "marketing_expense",
        "other_expense",
        "expense_coverage_rate",
        "missing_expense_types",
        "finance_approved",
        "gross_profit_status",
        "operating_profit_status",
        "profit_reasons",
    }
    assert required_rollup_columns <= set(DwsFinanceDaily.__table__.columns.keys())
    assert required_rollup_columns <= set(DmFinanceProfitDaily.__table__.columns.keys())
