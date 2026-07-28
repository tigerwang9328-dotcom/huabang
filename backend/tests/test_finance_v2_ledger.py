from decimal import Decimal

from app.services.finance_v2.ledger_service import LedgerLine, aggregate_period_balances


def test_posted_lines_are_aggregated_by_account_dimension_and_currency():
    balances = aggregate_period_balances(
        [
            LedgerLine(101, 1, "CNY", Decimal("100"), Decimal("0")),
            LedgerLine(101, 1, "CNY", Decimal("20"), Decimal("0")),
            LedgerLine(601, 1, "CNY", Decimal("0"), Decimal("120")),
        ]
    )

    assert balances[(101, 1, "CNY")].period_debit == Decimal("120")
    assert balances[(601, 1, "CNY")].period_credit == Decimal("120")
