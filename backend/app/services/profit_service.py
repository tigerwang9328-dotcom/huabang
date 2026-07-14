"""Deterministic gross-profit and operating-profit calculations."""

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable


REQUIRED_EXPENSE_TYPES = (
    "rent",
    "wages",
    "social_security",
    "platform_fee",
    "utilities",
    "logistics",
    "marketing",
    "other",
)


def _decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass(frozen=True)
class ExpenseAllocation:
    """An expense declaration and its inclusive allocation period."""

    expense_type: str
    amount: Decimal
    allocation_start: date
    allocation_end: date
    data_type: str = "estimate"

    def __post_init__(self):
        object.__setattr__(self, "amount", _decimal(self.amount))
        if self.allocation_end < self.allocation_start:
            raise ValueError("allocation_end must be on or after allocation_start")


@dataclass(frozen=True)
class ProfitResult:
    net_sales: Decimal
    cost_of_goods: Decimal | None
    gross_profit: Decimal | None
    gross_margin: Decimal | None
    gross_profit_status: str
    expense_by_type: dict[str, Decimal]
    total_expense: Decimal
    expense_coverage_rate: Decimal
    missing_expense_types: tuple[str, ...]
    finance_approved: bool
    operating_profit: Decimal | None
    operating_margin: Decimal | None
    operating_profit_status: str
    reasons: tuple[str, ...]

    @property
    def status(self) -> str:
        return self.operating_profit_status

    def as_dict(self) -> dict:
        result = asdict(self)
        result["status"] = self.status
        return result


def calculate_profit(
    *,
    period_start: date,
    period_end: date,
    net_sales,
    cost_of_goods,
    is_cost_complete: bool,
    expenses: Iterable[ExpenseAllocation],
) -> ProfitResult:
    """Calculate profit while preserving incomplete-data states.

    Expense coverage is measured as declared category-days divided by all
    required category-days. A declaration counts even when its amount is zero.
    """
    if period_end < period_start:
        raise ValueError("period_end must be on or after period_start")

    net_sales_value = _decimal(net_sales)
    cost_value = None if cost_of_goods is None else _decimal(cost_of_goods)
    gross_profit = None if cost_value is None else net_sales_value - cost_value
    gross_margin = (
        gross_profit / net_sales_value
        if gross_profit is not None and net_sales_value > 0
        else None
    )
    gross_profit_status = "ready" if is_cost_complete and cost_value is not None else "estimated"

    expense_by_type = {expense_type: Decimal("0") for expense_type in REQUIRED_EXPENSE_TYPES}
    covered_dates = {expense_type: set() for expense_type in REQUIRED_EXPENSE_TYPES}
    allocated_expenses = []

    for expense in expenses:
        if expense.expense_type not in expense_by_type:
            continue
        overlap_start = max(period_start, expense.allocation_start)
        overlap_end = min(period_end, expense.allocation_end)
        if overlap_end < overlap_start:
            continue

        allocation_days = (expense.allocation_end - expense.allocation_start).days + 1
        overlap_days = (overlap_end - overlap_start).days + 1
        expense_by_type[expense.expense_type] += (
            expense.amount * Decimal(overlap_days) / Decimal(allocation_days)
        )
        allocated_expenses.append(expense)

        current_date = overlap_start
        while current_date <= overlap_end:
            covered_dates[expense.expense_type].add(current_date)
            current_date += timedelta(days=1)

    period_days = (period_end - period_start).days + 1
    declared_category_days = sum(len(days) for days in covered_dates.values())
    required_category_days = len(REQUIRED_EXPENSE_TYPES) * period_days
    expense_coverage_rate = Decimal(declared_category_days) / Decimal(required_category_days)
    missing_expense_types = tuple(
        expense_type
        for expense_type in REQUIRED_EXPENSE_TYPES
        if not covered_dates[expense_type]
    )
    total_expense = sum(expense_by_type.values(), Decimal("0"))
    finance_approved = bool(allocated_expenses) and all(
        expense.data_type == "actual" for expense in allocated_expenses
    )

    reasons = []
    if not is_cost_complete or cost_value is None:
        reasons.append("cost_incomplete")
    if expense_coverage_rate < Decimal("1"):
        reasons.append("expense_coverage_incomplete")
    if not finance_approved:
        reasons.append("finance_not_approved")
    if net_sales_value <= 0:
        reasons.append("net_sales_not_positive")

    operating_profit = None
    operating_margin = None
    operating_profit_status = "pending_data"
    if not reasons and gross_profit is not None:
        operating_profit = gross_profit - total_expense
        operating_margin = operating_profit / net_sales_value
        operating_profit_status = "ready"

    return ProfitResult(
        net_sales=net_sales_value,
        cost_of_goods=cost_value,
        gross_profit=gross_profit,
        gross_margin=gross_margin,
        gross_profit_status=gross_profit_status,
        expense_by_type=expense_by_type,
        total_expense=total_expense,
        expense_coverage_rate=expense_coverage_rate,
        missing_expense_types=missing_expense_types,
        finance_approved=finance_approved,
        operating_profit=operating_profit,
        operating_margin=operating_margin,
        operating_profit_status=operating_profit_status,
        reasons=tuple(reasons),
    )
