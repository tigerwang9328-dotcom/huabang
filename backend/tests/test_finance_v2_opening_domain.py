from decimal import Decimal

import pytest

from app.services.finance_v2.opening_balance_domain import (
    OpeningBalanceError,
    OpeningBalanceLine,
    OpeningBalanceState,
    approve_opening_balance,
    assert_current_writes_allowed,
    validate_opening_balance,
)


def _lines() -> list[OpeningBalanceLine]:
    return [
        OpeningBalanceLine("1001", "empty", "CNY", Decimal("100"), Decimal("0"), "kingdee"),
        OpeningBalanceLine("3001", "empty", "CNY", Decimal("0"), Decimal("100"), "kingdee"),
    ]


def test_final_opening_balance_must_be_balanced_and_locked_before_current_writes():
    approved = approve_opening_balance(
        OpeningBalanceState("final", "validated", coverage_continuous=True),
        _lines(),
        approver="finance-manager",
    )

    assert approved.status == "locked"
    assert_current_writes_allowed(approved)


def test_provisional_or_unapproved_opening_never_enables_current_writes():
    with pytest.raises(OpeningBalanceError, match="final locked"):
        assert_current_writes_allowed(OpeningBalanceState("provisional", "validated", coverage_continuous=True))
    with pytest.raises(OpeningBalanceError, match="not balanced"):
        validate_opening_balance([OpeningBalanceLine("1001", "empty", "CNY", Decimal("1"), Decimal("0"), "kingdee")])


def test_coverage_gap_requires_explicit_approval_and_blocks_formal_reports_not_current_writes():
    with pytest.raises(OpeningBalanceError, match="coverage gap"):
        approve_opening_balance(
            OpeningBalanceState("final", "validated", coverage_continuous=False),
            _lines(),
            approver="finance-manager",
        )
    approved = approve_opening_balance(
        OpeningBalanceState(
            "final",
            "validated",
            coverage_continuous=False,
            coverage_gap_approved=True,
            formal_report_blocked=True,
        ),
        _lines(),
        approver="finance-manager",
    )

    assert approved.status == "locked"
    assert_current_writes_allowed(approved)
