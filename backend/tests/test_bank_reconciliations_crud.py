"""Task 13: 银行调节表 CRUD 路由测试(finance_center_mumaren_bank_reconciliations)。

覆盖状态机:仅 draft 可改/可删,跨账簿校验,审计日志写入。
"""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from mumaren_crud_helpers import _FakeUser, _MockDb, _MockResult

from app.api.v1.mumaren_finance_center_crud import (
    BankReconciliationInput,
    BankReconciliationUpdate,
    create_bank_reconciliation,
    delete_bank_reconciliation,
    list_bank_reconciliations,
    update_bank_reconciliation,
)
from app.models.mumaren_finance_center_domains import FinanceCenterMumarenBankReconciliation
from app.models.mumaren_finance_center import FinanceCenterMumarenAccount


def _rec(*, rid=1, book_id=1, status="draft"):
    return FinanceCenterMumarenBankReconciliation(
        id=rid, book_id=book_id, cash_account_id=10, period="2026-07",
        bank_balance=Decimal("100000.00"), book_balance=Decimal("99800.00"),
        adjusted_balance=Decimal("100000.00"), items_json={"items": []},
        workflow_status=status, created_by=5,
    )


@pytest.mark.asyncio
async def test_create_bank_reconciliation_persists_draft_and_writes_audit_log():
    account = FinanceCenterMumarenAccount(id=10, book_id=1, account_code="1002", account_name="银行存款", account_type="asset")
    db = _MockDb(get_map={FinanceCenterMumarenAccount: {10: account}})
    res = await create_bank_reconciliation(
        body=BankReconciliationInput(
            book_id=1, cash_account_id=10, period="2026-07",
            bank_balance=Decimal("100000"), book_balance=Decimal("99800"),
            adjusted_balance=Decimal("100000"), items_json={"items": []},
        ),
        current_user=_FakeUser(user_id=5), db=db,
    )
    assert res.data["workflow_status"] == "draft"
    logs = db.audit_logs("create_bank_reconciliation")
    assert len(logs) == 1
    assert logs[0].operator_id == 5


@pytest.mark.asyncio
async def test_create_bank_reconciliation_rejects_cash_account_from_another_book():
    foreign_account = FinanceCenterMumarenAccount(id=10, book_id=2, account_code="1002", account_name="银行存款", account_type="asset")
    db = _MockDb(get_map={FinanceCenterMumarenAccount: {10: foreign_account}})
    with pytest.raises(HTTPException) as exc:
        await create_bank_reconciliation(
            body=BankReconciliationInput(book_id=1, cash_account_id=10, period="2026-07", bank_balance=Decimal("1"), book_balance=Decimal("1"), adjusted_balance=Decimal("1")),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_list_bank_reconciliations_filters_by_period():
    rows = [_rec(rid=1, status="draft")]
    db = _MockDb(execute_results=[_MockResult(scalars=rows)])
    res = await list_bank_reconciliations(book_id=1, period="2026-07", limit=100, _=_FakeUser(), db=db)
    assert len(res.data) == 1
    assert res.data[0]["period"] == "2026-07"


@pytest.mark.asyncio
async def test_update_bank_reconciliation_only_allowed_in_draft():
    posted = _rec(rid=1, status="posted")
    db = _MockDb(get_map={FinanceCenterMumarenBankReconciliation: {1: posted}})
    with pytest.raises(HTTPException) as exc:
        await update_bank_reconciliation(
            rec_id=1, body=BankReconciliationUpdate(book_id=1, bank_balance=Decimal("99999")),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 409
    assert db.audit_logs() == []

    draft = _rec(rid=1, status="draft")
    db2 = _MockDb(get_map={FinanceCenterMumarenBankReconciliation: {1: draft}})
    res = await update_bank_reconciliation(
        rec_id=1, body=BankReconciliationUpdate(book_id=1, bank_balance=Decimal("99999")),
        current_user=_FakeUser(), db=db2,
    )
    assert res.data["bank_balance"] == Decimal("99999")
    assert len(db2.audit_logs("update_bank_reconciliation")) == 1


@pytest.mark.asyncio
async def test_update_bank_reconciliation_rejects_cross_book():
    rec = _rec(rid=1, book_id=1)
    db = _MockDb(get_map={FinanceCenterMumarenBankReconciliation: {1: rec}})
    with pytest.raises(HTTPException) as exc:
        await update_bank_reconciliation(
            rec_id=1, body=BankReconciliationUpdate(book_id=2, bank_balance=Decimal("1")),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_bank_reconciliation_only_allowed_in_draft():
    reviewed = _rec(rid=1, status="reviewed")
    db = _MockDb(get_map={FinanceCenterMumarenBankReconciliation: {1: reviewed}})
    with pytest.raises(HTTPException) as exc:
        await delete_bank_reconciliation(rec_id=1, book_id=1, current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 409

    draft = _rec(rid=1, status="draft")
    db2 = _MockDb(get_map={FinanceCenterMumarenBankReconciliation: {1: draft}})
    res = await delete_bank_reconciliation(rec_id=1, book_id=1, current_user=_FakeUser(user_id=9), db=db2)
    assert res.success
    assert len(db2.deleted) == 1
    assert len(db2.audit_logs("delete_bank_reconciliation")) == 1


@pytest.mark.asyncio
async def test_delete_bank_reconciliation_rejects_cross_book():
    rec = _rec(rid=1, book_id=1, status="draft")
    db = _MockDb(get_map={FinanceCenterMumarenBankReconciliation: {1: rec}})
    with pytest.raises(HTTPException) as exc:
        await delete_bank_reconciliation(rec_id=1, book_id=99, current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 400
