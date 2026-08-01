"""Task 14: 辅助核算 CRUD 路由测试(finance_center_mumaren_auxiliary_accountings)。

覆盖软删除(is_active=true → false)、硬删除(is_active=false → delete)、跨账簿校验、审计日志。
"""
import pytest
from fastapi import HTTPException

from mumaren_crud_helpers import _FakeUser, _MockDb, _MockResult

from app.api.v1.mumaren_finance_center_crud import (
    AuxiliaryAccountingInput,
    AuxiliaryAccountingUpdate,
    create_auxiliary_accounting,
    delete_auxiliary_accounting,
    list_auxiliary_accountings,
    update_auxiliary_accounting,
)
from app.models.mumaren_finance_center_domains import FinanceCenterMumarenAuxiliaryAccounting


def _aux(*, aid=1, book_id=1, aux_type="customer", is_active=True):
    return FinanceCenterMumarenAuxiliaryAccounting(
        id=aid, book_id=book_id, aux_type=aux_type,
        code="C001", name="贵州客户A", parent_id=None,
        is_active=is_active, created_by=5,
    )


@pytest.mark.asyncio
async def test_create_auxiliary_accounting_persists_and_writes_audit_log():
    db = _MockDb()
    res = await create_auxiliary_accounting(
        body=AuxiliaryAccountingInput(
            book_id=1, aux_type="customer", code="C001", name="贵州客户A",
        ),
        current_user=_FakeUser(user_id=5), db=db,
    )
    assert res.data["aux_type"] == "customer"
    assert res.data["is_active"] is True
    logs = db.audit_logs("create_auxiliary_accounting")
    assert len(logs) == 1
    assert logs[0].operator_id == 5


@pytest.mark.asyncio
async def test_create_auxiliary_accounting_rejects_parent_from_another_book():
    foreign_parent = _aux(aid=8, book_id=2)
    db = _MockDb(get_map={FinanceCenterMumarenAuxiliaryAccounting: {8: foreign_parent}})
    with pytest.raises(HTTPException) as exc:
        await create_auxiliary_accounting(
            body=AuxiliaryAccountingInput(book_id=1, aux_type="customer", code="C002", name="客户B", parent_id=8),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_list_auxiliary_accountings_filters_by_aux_type():
    rows = [_aux(aid=1, aux_type="customer"), _aux(aid=2, aux_type="supplier")]
    db = _MockDb(execute_results=[_MockResult(scalars=rows)])
    res = await list_auxiliary_accountings(book_id=1, aux_type="customer", limit=100, _=_FakeUser(), db=db)
    assert len(res.data) == 2


@pytest.mark.asyncio
async def test_update_auxiliary_accounting_rejects_cross_book_and_writes_audit_log():
    aux = _aux(aid=1, book_id=1)
    db = _MockDb(get_map={FinanceCenterMumarenAuxiliaryAccounting: {1: aux}})
    with pytest.raises(HTTPException) as exc:
        await update_auxiliary_accounting(
            aux_id=1, body=AuxiliaryAccountingUpdate(book_id=2, name="新名"),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 400
    assert db.audit_logs() == []

    aux2 = _aux(aid=1, book_id=1)
    db2 = _MockDb(get_map={FinanceCenterMumarenAuxiliaryAccounting: {1: aux2}})
    updated = await update_auxiliary_accounting(
        aux_id=1, body=AuxiliaryAccountingUpdate(book_id=1, name="新名"),
        current_user=_FakeUser(user_id=8), db=db2,
    )
    assert updated.data["name"] == "新名"
    assert len(db2.audit_logs("update_auxiliary_accounting")) == 1


@pytest.mark.asyncio
async def test_delete_soft_deletes_active_auxiliary_accounting():
    """活跃账户软删除:is_active 置 false,不真正删除。"""
    aux = _aux(aid=1, is_active=True)
    db = _MockDb(get_map={FinanceCenterMumarenAuxiliaryAccounting: {1: aux}})
    res = await delete_auxiliary_accounting(aux_id=1, book_id=1, current_user=_FakeUser(user_id=9), db=db)
    assert res.success
    assert res.data["is_active"] is False
    assert len(db.deleted) == 0  # 未真正删除
    assert len(db.audit_logs("delete_auxiliary_accounting")) == 1


@pytest.mark.asyncio
async def test_delete_hard_deletes_inactive_auxiliary_accounting():
    """已停用账户硬删除:真正从数据库删除。"""
    aux = _aux(aid=1, is_active=False)
    db = _MockDb(get_map={FinanceCenterMumarenAuxiliaryAccounting: {1: aux}})
    res = await delete_auxiliary_accounting(aux_id=1, book_id=1, current_user=_FakeUser(user_id=9), db=db)
    assert res.success
    assert len(db.deleted) == 1  # 真正删除
    assert len(db.audit_logs("delete_auxiliary_accounting")) == 1


@pytest.mark.asyncio
async def test_delete_auxiliary_accounting_rejects_cross_book():
    aux = _aux(aid=1, book_id=1, is_active=False)
    db = _MockDb(get_map={FinanceCenterMumarenAuxiliaryAccounting: {1: aux}})
    with pytest.raises(HTTPException) as exc:
        await delete_auxiliary_accounting(aux_id=1, book_id=99, current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_auxiliary_accounting_returns_404_when_missing():
    db = _MockDb(get_map={FinanceCenterMumarenAuxiliaryAccounting: {}})
    with pytest.raises(HTTPException) as exc:
        await update_auxiliary_accounting(
            aux_id=999, body=AuxiliaryAccountingUpdate(book_id=1, name="x"),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 404
