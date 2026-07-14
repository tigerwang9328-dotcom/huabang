import asyncio
from types import SimpleNamespace

import pytest

from app.api.v1.finance import (
    ExpenseCreateRequest,
    approve_manual_expense,
    create_manual_expense,
)
from app.services.etl.dws_to_dm import DwsToDm
from app.services.ai_diagnosis_service import _can_assert_operating_profit


class _FakeDb:
    def __init__(self):
        self.added = None

    def add(self, value):
        self.added = value

    async def flush(self):
        self.added.id = 17


class _ApprovalDb:
    def __init__(self, expense=None, error=None):
        self.expense = expense
        self.error = error
        self.rolled_back = False

    async def get(self, model, record_id):
        return self.expense

    async def flush(self):
        return None

    async def execute(self, statement, params=None):
        if self.error:
            raise self.error

    async def rollback(self):
        self.rolled_back = True


class _EtlLog:
    def start_task(self, *args):
        return 1

    def fail_task(self, *args):
        return None


def test_manual_expense_cannot_self_approve_even_with_explicit_zero_declaration():
    db = _FakeDb()
    body = ExpenseCreateRequest(
        expense_date="2026-07-01",
        allocation_start="2026-07-01",
        allocation_end="2026-07-31",
        expense_type="platform_fee",
        expense_amount=0,
        data_type="actual",
    )

    response = asyncio.run(
        create_manual_expense(body=body, current_user=SimpleNamespace(id=9), db=db)
    )

    assert response.success is False
    assert db.added is None


def test_manual_expense_is_created_pending_finance_approval():
    db = _FakeDb()
    body = ExpenseCreateRequest(
        expense_date="2026-07-01",
        allocation_start="2026-07-01",
        allocation_end="2026-07-31",
        expense_type="platform_fee",
        expense_amount=0,
    )

    response = asyncio.run(create_manual_expense(
        body=body, current_user=SimpleNamespace(id=9), db=db
    ))

    assert response.success is True
    assert db.added.data_type == "estimate"
    assert "待财务核准" in response.message


def test_finance_approver_records_identity_and_time():
    expense = SimpleNamespace(id=17, data_type="estimate", approved_by=None, approved_at=None)
    db = _ApprovalDb(expense=expense)

    response = asyncio.run(approve_manual_expense(
        expense_id=17, current_user=SimpleNamespace(id=21), db=db
    ))

    assert response.success is True
    assert expense.data_type == "actual"
    assert expense.approved_by == 21
    assert expense.approved_at is not None


def test_dm_finance_refresh_propagates_database_failures():
    db = _ApprovalDb(error=RuntimeError("write failed"))

    with pytest.raises(RuntimeError, match="write failed"):
        asyncio.run(DwsToDm()._finance_profit("2026-07-13", db, _EtlLog()))

    assert db.rolled_back is True


def test_ai_only_asserts_operating_profit_when_cost_expense_and_approval_are_complete():
    ready = {
        "operating_profit": -100,
        "is_cost_complete": True,
        "is_expense_complete": True,
        "finance_approved": True,
    }

    assert _can_assert_operating_profit(ready) is True
    for key in ("is_cost_complete", "is_expense_complete", "finance_approved"):
        incomplete = {**ready, key: False}
        assert _can_assert_operating_profit(incomplete) is False
    assert _can_assert_operating_profit({**ready, "operating_profit": None}) is False
