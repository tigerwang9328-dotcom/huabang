import asyncio
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


def test_report_endpoints_scope_the_service_read_to_the_requested_book():
    from app.api.v1 import mumaren_finance_center

    source = __import__("inspect").getsource(mumaren_finance_center)

    assert "get_trial_balance(db, book_id=book_id, period=period)" in source
    assert "get_profit_statement(db, book_id=book_id, period=period)" in source
    assert "get_cash_flow_statement(db, book_id=book_id, period=period)" in source


def test_new_router_exposes_readonly_kingdee_balance_snapshot_endpoint():
    from app.api.v1.mumaren_finance_center import router

    paths = {route.path for route in router.routes}

    assert "/finance-center/mumaren/history/balance-snapshots" in paths


def test_new_router_exposes_posted_voucher_line_ledger_endpoint():
    from app.api.v1.mumaren_finance_center import router

    paths = {route.path for route in router.routes}

    assert "/finance-center/mumaren/ledger/lines" in paths


def test_ledger_line_endpoint_rejects_an_account_from_another_book():
    from fastapi import HTTPException
    from app.api.v1.mumaren_finance_center import get_ledger_lines

    class CrossBookDb:
        def __init__(self):
            self.values = [SimpleNamespace(id=1), SimpleNamespace(book_id=2)]

        async def get(self, _model, _id):
            return self.values.pop(0)

    with pytest.raises(HTTPException) as error:
        asyncio.run(get_ledger_lines(book_id=1, account_id=99, limit=500, _=None, db=CrossBookDb()))

    assert error.value.status_code == 404


def test_ledger_line_endpoint_calculates_directional_running_balance_with_pagination():
    from app.api.v1 import mumaren_finance_center

    source = __import__("inspect").getsource(mumaren_finance_center.get_ledger_lines)

    assert "offset: int = Query(default=0, ge=0)" in source
    assert "FinanceCenterMumarenAccount.direction == \"credit\"" in source
    assert "func.sum" in source
    assert '"has_more"' in source


def test_history_snapshot_endpoint_supports_offset_pagination():
    from app.api.v1 import mumaren_finance_center

    source = __import__("inspect").getsource(mumaren_finance_center.get_history_balance_snapshots)

    assert "offset: int = Query(default=0, ge=0)" in source
    assert ".offset(offset)" in source


def test_voucher_list_endpoint_supports_bounded_pagination():
    from app.api.v1 import mumaren_finance_center

    source = __import__("inspect").getsource(mumaren_finance_center.get_vouchers)

    assert "limit: int = Query(default=200, ge=1, le=500)" in source
    assert "offset: int = Query(default=0, ge=0)" in source
    assert ".offset(offset).limit(limit)" in source


def test_balance_snapshot_query_joins_account_within_the_same_book():
    from app.api.v1 import mumaren_finance_center

    source = __import__("inspect").getsource(mumaren_finance_center.get_history_balance_snapshots)

    assert "FinanceCenterMumarenAccount.book_id == FinanceCenterMumarenBalanceSnapshot.book_id" in source
    assert "余额快照仅适用于金蝶迁移只读账簿" in source


def test_balance_snapshot_endpoint_rejects_a_current_book():
    from fastapi import HTTPException
    from app.api.v1.mumaren_finance_center import get_history_balance_snapshots

    class CurrentBookDb:
        async def get(self, _model, _book_id):
            return SimpleNamespace(is_readonly=False)

    with pytest.raises(HTTPException) as error:
        asyncio.run(get_history_balance_snapshots(book_id=1, period=None, limit=500, _=None, db=CurrentBookDb()))

    assert error.value.status_code == 409


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
    # Task 16: 平衡校验字段
    assert report["assets_total"] == Decimal("90")
    assert report["liabilities_total"] == Decimal("0")
    assert report["equity_total"] == Decimal("0")
    assert report["balance_check"]["is_balanced"] is False  # 资产 90 ≠ 负债+权益 0


def test_empty_posted_ledger_returns_zero_trial_balance_and_profit_statement():
    accounts = [_account(1, "6001", "主营业务收入", "income", "credit")]

    trial_balance = build_trial_balance(accounts, [])
    profit_statement = build_profit_statement(accounts, [])

    assert trial_balance["rows"] == [{"account_id": 1, "account_code": "6001", "account_name": "主营业务收入", "direction": "credit", "debit_amount": Decimal("0"), "credit_amount": Decimal("0"), "closing_debit": Decimal("0"), "closing_credit": Decimal("0")}]
    assert trial_balance["total_debit"] == Decimal("0")
    assert trial_balance["total_credit"] == Decimal("0")
    assert trial_balance["is_balanced"] is True
    assert trial_balance["assets_total"] == Decimal("0")
    assert trial_balance["liabilities_total"] == Decimal("0")
    assert trial_balance["equity_total"] == Decimal("0")
    assert trial_balance["balance_check"]["is_balanced"] is True
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
