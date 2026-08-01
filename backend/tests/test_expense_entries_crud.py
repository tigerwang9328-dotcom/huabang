"""Task 11: 费用明细 CRUD 路由测试(finance_center_mumaren_expense_entries)。

覆盖状态机:draft → reviewed → posted,跨账簿校验,审计日志写入。
"""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from mumaren_crud_helpers import _FakeUser, _MockDb, _MockResult

from app.api.v1.mumaren_finance_center_crud import (
    ExpenseEntryInput,
    ExpenseEntryUpdate,
    create_expense_entry,
    delete_expense_entry,
    list_expense_entries,
    post_expense_entry,
    review_expense_entry,
    update_expense_entry,
)
from app.models.mumaren_finance_center_domains import FinanceCenterMumarenExpenseEntry


def _entry(*, eid=1, book_id=1, status="draft"):
    return FinanceCenterMumarenExpenseEntry(
        id=eid, book_id=book_id, period="2026-07",
        account_code="6601", account_name="管理费用-办公费",
        amount=Decimal("1500.00"), remark="7月办公费",
        workflow_status=status, created_by=5,
    )


@pytest.mark.asyncio
async def test_create_expense_entry_persists_draft_and_writes_audit_log():
    db = _MockDb()
    res = await create_expense_entry(
        body=ExpenseEntryInput(
            book_id=1, period="2026-07", account_code="6601",
            account_name="管理费用-办公费", amount=Decimal("1500"),
        ),
        current_user=_FakeUser(user_id=5), db=db,
    )
    assert res.data["workflow_status"] == "draft"
    logs = db.audit_logs("create_expense_entry")
    assert len(logs) == 1
    assert logs[0].operator_id == 5


@pytest.mark.asyncio
async def test_list_expense_entries_filters_by_period():
    rows = [_entry(eid=1)]
    db = _MockDb(execute_results=[_MockResult(scalars=rows)])
    res = await list_expense_entries(book_id=1, period="2026-07", limit=100, _=_FakeUser(), db=db)
    assert len(res.data) == 1
    assert res.data[0]["period"] == "2026-07"


@pytest.mark.asyncio
async def test_update_expense_entry_only_allowed_in_draft():
    posted = _entry(eid=1, status="posted")
    db = _MockDb(get_map={FinanceCenterMumarenExpenseEntry: {1: posted}})
    with pytest.raises(HTTPException) as exc:
        await update_expense_entry(
            entry_id=1, body=ExpenseEntryUpdate(book_id=1, account_name="新名"),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 409
    assert db.audit_logs() == []

    draft = _entry(eid=1, status="draft")
    db2 = _MockDb(get_map={FinanceCenterMumarenExpenseEntry: {1: draft}})
    res = await update_expense_entry(
        entry_id=1, body=ExpenseEntryUpdate(book_id=1, account_name="新名"),
        current_user=_FakeUser(), db=db2,
    )
    assert res.data["account_name"] == "新名"
    assert len(db2.audit_logs("update_expense_entry")) == 1


@pytest.mark.asyncio
async def test_update_expense_entry_rejects_cross_book():
    entry = _entry(eid=1, book_id=1)
    db = _MockDb(get_map={FinanceCenterMumarenExpenseEntry: {1: entry}})
    with pytest.raises(HTTPException) as exc:
        await update_expense_entry(
            entry_id=1, body=ExpenseEntryUpdate(book_id=2, account_name="x"),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_expense_entry_only_allowed_in_draft():
    reviewed = _entry(eid=1, status="reviewed")
    db = _MockDb(get_map={FinanceCenterMumarenExpenseEntry: {1: reviewed}})
    with pytest.raises(HTTPException) as exc:
        await delete_expense_entry(entry_id=1, book_id=1, current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 409

    draft = _entry(eid=1, status="draft")
    db2 = _MockDb(get_map={FinanceCenterMumarenExpenseEntry: {1: draft}})
    res = await delete_expense_entry(entry_id=1, book_id=1, current_user=_FakeUser(), db=db2)
    assert res.success
    assert len(db2.deleted) == 1
    assert len(db2.audit_logs("delete_expense_entry")) == 1


@pytest.mark.asyncio
async def test_review_expense_entry_transitions_draft_to_reviewed():
    draft = _entry(eid=1, status="draft")
    db = _MockDb(get_map={FinanceCenterMumarenExpenseEntry: {1: draft}})
    res = await review_expense_entry(entry_id=1, book_id=1, current_user=_FakeUser(user_id=6), db=db)
    assert res.data["workflow_status"] == "reviewed"
    assert len(db.audit_logs("review_expense_entry")) == 1

    # 已审核再审核应被拒绝
    reviewed = _entry(eid=1, status="reviewed")
    db2 = _MockDb(get_map={FinanceCenterMumarenExpenseEntry: {1: reviewed}})
    with pytest.raises(HTTPException) as exc:
        await review_expense_entry(entry_id=1, book_id=1, current_user=_FakeUser(), db=db2)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_post_expense_entry_rejects_draft_and_transitions_reviewed_to_posted():
    # draft 直接 post 返回 409
    draft = _entry(eid=1, status="draft")
    db = _MockDb(get_map={FinanceCenterMumarenExpenseEntry: {1: draft}})
    with pytest.raises(HTTPException) as exc:
        await post_expense_entry(entry_id=1, book_id=1, current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 409
    assert db.audit_logs() == []

    # reviewed → posted 成功
    reviewed = _entry(eid=1, status="reviewed")
    db2 = _MockDb(get_map={FinanceCenterMumarenExpenseEntry: {1: reviewed}})
    res = await post_expense_entry(entry_id=1, book_id=1, current_user=_FakeUser(user_id=7), db=db2)
    assert res.data["workflow_status"] == "posted"
    assert len(db2.audit_logs("post_expense_entry")) == 1


@pytest.mark.asyncio
async def test_review_and_post_reject_cross_book():
    draft = _entry(eid=1, book_id=1)
    db = _MockDb(get_map={FinanceCenterMumarenExpenseEntry: {1: draft}})
    with pytest.raises(HTTPException) as exc:
        await review_expense_entry(entry_id=1, book_id=99, current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 400

    reviewed = _entry(eid=1, status="reviewed")
    db2 = _MockDb(get_map={FinanceCenterMumarenExpenseEntry: {1: reviewed}})
    with pytest.raises(HTTPException) as exc:
        await post_expense_entry(entry_id=1, book_id=99, current_user=_FakeUser(), db=db2)
    assert exc.value.status_code == 400
