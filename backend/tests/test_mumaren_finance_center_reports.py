from decimal import Decimal
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("APP_SECRET_KEY", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test")

from app.services.mumaren_finance_center.reports import (
    build_profit_statement,
    build_trial_balance,
)


def test_new_router_exposes_isolated_trial_balance_and_profit_statement_endpoints():
    from app.api.v1.mumaren_finance_center import router

    paths = {route.path for route in router.routes}

    assert "/finance-center/mumaren/reports/trial-balance" in paths
    assert "/finance-center/mumaren/reports/profit-statement" in paths


def _account(account_id: int, code: str, name: str, account_type: str, direction: str = "debit"):
    return SimpleNamespace(
        id=account_id,
        account_code=code,
        account_name=name,
        account_type=account_type,
        direction=direction,
    )


def test_trial_balance_uses_only_posted_current_voucher_lines_and_keeps_zero_accounts():
    accounts = [
        _account(1, "1001", "库存现金", "asset"),
        _account(2, "6001", "主营业务收入", "income", "credit"),
        _account(3, "6601", "销售费用", "expense"),
        _account(4, "9999", "尚未发生", "asset"),
    ]
    posted_lines = [
        {"account_id": 1, "debit_amount": Decimal("120"), "credit_amount": Decimal("0")},
        {"account_id": 2, "debit_amount": Decimal("0"), "credit_amount": Decimal("120")},
        {"account_id": 3, "debit_amount": Decimal("30"), "credit_amount": Decimal("0")},
        {"account_id": 1, "debit_amount": Decimal("0"), "credit_amount": Decimal("30")},
    ]

    report = build_trial_balance(accounts, posted_lines)

    assert report["total_debit"] == Decimal("150")
    assert report["total_credit"] == Decimal("150")
    assert report["is_balanced"] is True
    assert report["rows"] == [
        {"account_id": 1, "account_code": "1001", "account_name": "库存现金", "direction": "debit", "debit_amount": Decimal("120"), "credit_amount": Decimal("30"), "closing_debit": Decimal("90"), "closing_credit": Decimal("0")},
        {"account_id": 2, "account_code": "6001", "account_name": "主营业务收入", "direction": "credit", "debit_amount": Decimal("0"), "credit_amount": Decimal("120"), "closing_debit": Decimal("0"), "closing_credit": Decimal("120")},
        {"account_id": 3, "account_code": "6601", "account_name": "销售费用", "direction": "debit", "debit_amount": Decimal("30"), "credit_amount": Decimal("0"), "closing_debit": Decimal("30"), "closing_credit": Decimal("0")},
        {"account_id": 4, "account_code": "9999", "account_name": "尚未发生", "direction": "debit", "debit_amount": Decimal("0"), "credit_amount": Decimal("0"), "closing_debit": Decimal("0"), "closing_credit": Decimal("0")},
    ]


def test_empty_posted_ledger_returns_zero_trial_balance_and_profit_statement():
    accounts = [_account(1, "6001", "主营业务收入", "income", "credit")]

    trial_balance = build_trial_balance(accounts, [])
    profit_statement = build_profit_statement(accounts, [])

    assert trial_balance == {
        "rows": [{"account_id": 1, "account_code": "6001", "account_name": "主营业务收入", "direction": "credit", "debit_amount": Decimal("0"), "credit_amount": Decimal("0"), "closing_debit": Decimal("0"), "closing_credit": Decimal("0")}],
        "total_debit": Decimal("0"),
        "total_credit": Decimal("0"),
        "is_balanced": True,
    }
    assert profit_statement == {
        "income_rows": [{"account_id": 1, "account_code": "6001", "account_name": "主营业务收入", "amount": Decimal("0")}],
        "expense_rows": [],
        "total_income": Decimal("0"),
        "total_expense": Decimal("0"),
        "net_profit": Decimal("0"),
    }


def test_profit_statement_uses_income_credit_minus_debit_and_expense_debit_minus_credit():
    accounts = [
        _account(1, "6001", "主营业务收入", "income", "credit"),
        _account(2, "6401", "主营业务成本", "expense"),
        _account(3, "6601", "销售费用", "expense"),
    ]
    posted_lines = [
        {"account_id": 1, "debit_amount": "20", "credit_amount": "200"},
        {"account_id": 2, "debit_amount": "80", "credit_amount": "0"},
        {"account_id": 3, "debit_amount": "10", "credit_amount": "2"},
    ]

    statement = build_profit_statement(accounts, posted_lines)

    assert statement["total_income"] == Decimal("180")
    assert statement["total_expense"] == Decimal("88")
    assert statement["net_profit"] == Decimal("92")
    assert statement["income_rows"][0]["amount"] == Decimal("180")
    assert [row["amount"] for row in statement["expense_rows"]] == [Decimal("80"), Decimal("8")]
