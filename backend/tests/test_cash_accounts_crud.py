"""Task 4: 出纳账户与资金流水 CRUD 路由测试(复用 cash_accounts + cash_flows)。"""
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from mumaren_crud_helpers import _FakeUser, _MockDb, _MockResult

from app.api.v1.mumaren_finance_center_domains import (
    CashAccountInput,
    CashAccountUpdate,
    CashFlowInput,
    create_cash_account,
    create_cash_flow,
    delete_cash_account,
    list_cash_accounts,
    list_cash_flows,
    update_cash_account,
)
from app.models.mumaren_finance_center_domains import (
    FinanceCenterMumarenCashAccount,
    FinanceCenterMumarenCashFlow,
)


def _account(*, acc_id=1, book_id=1, is_active=True):
    return FinanceCenterMumarenCashAccount(
        id=acc_id, book_id=book_id, account_code="B001", account_name="建行基本户",
        account_type="bank", currency="CNY", is_active=is_active,
    )


@pytest.mark.asyncio
async def test_create_cash_account_writes_audit_log():
    db = _MockDb()
    res = await create_cash_account(
        body=CashAccountInput(book_id=1, account_code="B001", account_name="建行基本户"),
        current_user=_FakeUser(user_id=3), db=db,
    )
    assert res.data["is_active"] is True
    assert len(db.audit_logs("create_cash_account")) == 1


@pytest.mark.asyncio
async def test_list_cash_accounts_returns_rows():
    db = _MockDb(execute_results=[_MockResult(scalars=[_account(acc_id=1)])])
    res = await list_cash_accounts(book_id=1, limit=100, _=_FakeUser(), db=db)
    assert len(res.data) == 1


@pytest.mark.asyncio
async def test_list_cash_accounts_excludes_soft_deleted_rows():
    db = _MockDb(execute_results=[_MockResult(scalars=[_account(acc_id=1)])])
    await list_cash_accounts(book_id=1, limit=100, _=_FakeUser(), db=db)
    statement = db.executed[0]
    assert "is_active" in str(statement)


@pytest.mark.asyncio
async def test_update_cash_account_rejects_cross_book():
    acc = _account(acc_id=1, book_id=1)
    db = _MockDb(get_map={FinanceCenterMumarenCashAccount: {1: acc}})
    with pytest.raises(HTTPException) as exc:
        await update_cash_account(
            account_id=1, body=CashAccountUpdate(book_id=2, account_name="x"),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 400

    db2 = _MockDb(get_map={FinanceCenterMumarenCashAccount: {1: acc}})
    res = await update_cash_account(
        account_id=1, body=CashAccountUpdate(book_id=1, account_name="工户"),
        current_user=_FakeUser(), db=db2,
    )
    assert res.data["account_name"] == "工户"
    assert len(db2.audit_logs("update_cash_account")) == 1


@pytest.mark.asyncio
async def test_delete_cash_account_soft_deletes_active_then_hard_deletes_inactive():
    active = _account(acc_id=1, is_active=True)
    db = _MockDb(get_map={FinanceCenterMumarenCashAccount: {1: active}})
    res = await delete_cash_account(account_id=1, book_id=1, current_user=_FakeUser(), db=db)
    assert res.data["is_active"] is False
    assert len(db.audit_logs("delete_cash_account")) == 1
    assert db.deleted == []  # 软删除,未硬删

    inactive = _account(acc_id=1, is_active=False)
    db2 = _MockDb(get_map={FinanceCenterMumarenCashAccount: {1: inactive}})
    res2 = await delete_cash_account(account_id=1, book_id=1, current_user=_FakeUser(), db=db2)
    assert res2.success
    assert len(db2.deleted) == 1  # 硬删除
    assert len(db2.audit_logs("delete_cash_account")) == 1


@pytest.mark.asyncio
async def test_list_cash_flows_supports_account_filter():
    db = _MockDb(execute_results=[_MockResult(scalars=[
        FinanceCenterMumarenCashFlow(id=1, book_id=1, cash_account_id=10, flow_date=date(2026, 7, 1),
                                      direction="in", amount=Decimal("100"), workflow_status="draft"),
    ])])
    res = await list_cash_flows(book_id=1, cash_account_id=10, limit=100, _=_FakeUser(), db=db)
    assert len(res.data) == 1
    assert res.data[0]["cash_account_id"] == 10


@pytest.mark.asyncio
async def test_create_cash_flow_rejects_cross_book_account():
    other_book_account = _account(acc_id=10, book_id=2)
    db = _MockDb(get_map={FinanceCenterMumarenCashAccount: {10: other_book_account}})
    with pytest.raises(HTTPException) as exc:
        await create_cash_flow(
            body=CashFlowInput(book_id=1, cash_account_id=10, flow_date=date(2026, 7, 1),
                               direction="in", amount=Decimal("100")),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 400
    assert db.audit_logs() == []

    same_book_account = _account(acc_id=10, book_id=1)
    db2 = _MockDb(get_map={FinanceCenterMumarenCashAccount: {10: same_book_account}})
    res = await create_cash_flow(
        body=CashFlowInput(book_id=1, cash_account_id=10, flow_date=date(2026, 7, 1),
                           direction="in", amount=Decimal("100")),
        current_user=_FakeUser(user_id=4), db=db2,
    )
    assert res.data["workflow_status"] == "draft"
    assert len(db2.audit_logs("create_cash_flow")) == 1


@pytest.mark.asyncio
async def test_create_cash_flow_404_when_account_missing():
    db = _MockDb(get_map={FinanceCenterMumarenCashAccount: {}})
    with pytest.raises(HTTPException) as exc:
        await create_cash_flow(
            body=CashFlowInput(book_id=1, cash_account_id=99, flow_date=date(2026, 7, 1),
                               direction="out", amount=Decimal("50")),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 404
