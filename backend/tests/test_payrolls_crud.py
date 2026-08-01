"""Task 5: 工资 CRUD 路由测试(复用 payrolls)。"""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from mumaren_crud_helpers import _FakeUser, _MockDb, _MockResult

from app.api.v1.mumaren_finance_center_domains import (
    PayrollInput,
    PayrollUpdate,
    create_payroll,
    delete_payroll,
    list_payrolls,
    pay_payroll,
    update_payroll,
)
from app.models.mumaren_finance_center_domains import FinanceCenterMumarenPayroll


def _payroll(*, pid=1, book_id=1, status="draft"):
    return FinanceCenterMumarenPayroll(
        id=pid, book_id=book_id, period="2026-07", employee_no="E001", employee_name="张三",
        gross_amount=Decimal("10000.00"), deduction_amount=Decimal("1000.00"),
        net_amount=Decimal("9000.00"), workflow_status=status,
    )


@pytest.mark.asyncio
async def test_create_payroll_persists_draft_and_writes_audit_log():
    db = _MockDb()
    res = await create_payroll(
        body=PayrollInput(book_id=1, period="2026-07", employee_no="E001", employee_name="张三",
                          gross_amount=Decimal("10000"), deduction_amount=Decimal("1000"),
                          net_amount=Decimal("9000")),
        current_user=_FakeUser(user_id=5), db=db,
    )
    assert res.data["workflow_status"] == "draft"
    logs = db.audit_logs("create_payroll")
    assert len(logs) == 1
    assert logs[0].operator_id == 5


@pytest.mark.asyncio
async def test_list_payrolls_filters_by_period():
    db = _MockDb(execute_results=[_MockResult(scalars=[_payroll(pid=1)])])
    res = await list_payrolls(book_id=1, period="2026-07", limit=100, _=_FakeUser(), db=db)
    assert len(res.data) == 1
    assert res.data[0]["period"] == "2026-07"


@pytest.mark.asyncio
async def test_update_payroll_only_allowed_in_draft():
    paid = _payroll(pid=1, status="paid")
    db = _MockDb(get_map={FinanceCenterMumarenPayroll: {1: paid}})
    with pytest.raises(HTTPException) as exc:
        await update_payroll(
            payroll_id=1, body=PayrollUpdate(book_id=1, employee_name="李四"),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 409
    assert db.audit_logs() == []

    draft = _payroll(pid=1, status="draft")
    db2 = _MockDb(get_map={FinanceCenterMumarenPayroll: {1: draft}})
    res = await update_payroll(
        payroll_id=1, body=PayrollUpdate(book_id=1, employee_name="李四"),
        current_user=_FakeUser(), db=db2,
    )
    assert res.data["employee_name"] == "李四"
    assert len(db2.audit_logs("update_payroll")) == 1


@pytest.mark.asyncio
async def test_update_payroll_rejects_cross_book():
    pr = _payroll(pid=1, book_id=1)
    db = _MockDb(get_map={FinanceCenterMumarenPayroll: {1: pr}})
    with pytest.raises(HTTPException) as exc:
        await update_payroll(
            payroll_id=1, body=PayrollUpdate(book_id=2, employee_name="x"),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_payroll_only_allowed_in_draft():
    paid = _payroll(pid=1, status="paid")
    db = _MockDb(get_map={FinanceCenterMumarenPayroll: {1: paid}})
    with pytest.raises(HTTPException) as exc:
        await delete_payroll(payroll_id=1, book_id=1, current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 409

    draft = _payroll(pid=1, status="draft")
    db2 = _MockDb(get_map={FinanceCenterMumarenPayroll: {1: draft}})
    res = await delete_payroll(payroll_id=1, book_id=1, current_user=_FakeUser(), db=db2)
    assert res.success
    assert len(db2.deleted) == 1
    assert len(db2.audit_logs("delete_payroll")) == 1


@pytest.mark.asyncio
async def test_pay_payroll_transitions_draft_to_paid():
    draft = _payroll(pid=1, status="draft")
    db = _MockDb(get_map={FinanceCenterMumarenPayroll: {1: draft}})
    res = await pay_payroll(payroll_id=1, book_id=1, current_user=_FakeUser(user_id=6), db=db)
    assert res.data["workflow_status"] == "paid"
    assert len(db.audit_logs("pay_payroll")) == 1

    # 已发放再发放应被拒绝
    db2 = _MockDb(get_map={FinanceCenterMumarenPayroll: {1: draft}})
    with pytest.raises(HTTPException) as exc:
        await pay_payroll(payroll_id=1, book_id=1, current_user=_FakeUser(), db=db2)
    assert exc.value.status_code == 409
