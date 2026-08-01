"""Task 7: 应收应付单据补充路由测试(复用 receivable_orders + payable_orders)。"""
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException, Query

from mumaren_crud_helpers import _FakeUser, _MockDb, _MockResult

from app.api.v1.mumaren_finance_center_domains import (
    ArApOrderUpdate,
    _ar_ap_filter_conditions,
    delete_ar_ap_order,
    list_ar_ap_orders,
    update_ar_ap_order,
)
from app.models.mumaren_finance_center_domains import (
    FinanceCenterMumarenPayableOrder,
    FinanceCenterMumarenReceivableOrder,
)


def _receivable(*, oid=1, book_id=1, status="draft"):
    return FinanceCenterMumarenReceivableOrder(
        id=oid, book_id=book_id, order_no="AR-2026-0001", order_date=date(2026, 7, 31),
        period="2026-07", counterparty_name="客户甲", total_amount=Decimal("1000.00"),
        settled_amount=Decimal("0"), settlement_status="open", workflow_status=status,
    )


def _payable(*, oid=1, book_id=1, status="draft"):
    return FinanceCenterMumarenPayableOrder(
        id=oid, book_id=book_id, order_no="AP-2026-0001", order_date=date(2026, 7, 31),
        period="2026-07", counterparty_name="供应商乙", total_amount=Decimal("500.00"),
        settled_amount=Decimal("0"), settlement_status="open", workflow_status=status,
    )


def test_ar_ap_filters_ignore_unresolved_fastapi_optional_query_defaults():
    conditions = _ar_ap_filter_conditions(
        FinanceCenterMumarenReceivableOrder,
        book_id=1,
        period=Query(default=None),
        status=Query(default=None),
        counterparty_name=Query(default=None),
    )
    assert len(conditions) == 1


@pytest.mark.asyncio
async def test_list_ar_ap_orders_returns_rows_by_type():
    db = _MockDb(execute_results=[_MockResult(scalars=[_receivable(oid=1)])])
    res = await list_ar_ap_orders(book_id=1, order_type="receivable", limit=100, _=_FakeUser(), db=db)
    assert len(res.data) == 1
    assert res.data[0]["order_no"] == "AR-2026-0001"


@pytest.mark.asyncio
async def test_update_receivable_order_only_in_draft_and_writes_audit_log():
    reviewed = _receivable(oid=1, status="reviewed")
    db = _MockDb(get_map={FinanceCenterMumarenReceivableOrder: {1: reviewed}})
    with pytest.raises(HTTPException) as exc:
        await update_ar_ap_order(
            order_id=1, body=ArApOrderUpdate(book_id=1, total_amount=Decimal("2000")),
            order_type="receivable", current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 409
    assert db.audit_logs() == []

    draft = _receivable(oid=1, status="draft")
    db2 = _MockDb(get_map={FinanceCenterMumarenReceivableOrder: {1: draft}})
    res = await update_ar_ap_order(
        order_id=1, body=ArApOrderUpdate(book_id=1, total_amount=Decimal("2000"), order_date=date(2026, 8, 1)),
        order_type="receivable", current_user=_FakeUser(user_id=4), db=db2,
    )
    assert res.data["total_amount"] == Decimal("2000")
    assert res.data["order_date"] == date(2026, 8, 1)
    # 期间随 order_date 重算
    assert draft.period == "2026-08"
    logs = db2.audit_logs("update_receivable_order")
    assert len(logs) == 1
    assert logs[0].operator_id == 4


@pytest.mark.asyncio
async def test_update_receivable_order_rejects_cross_book():
    order = _receivable(oid=1, book_id=1)
    db = _MockDb(get_map={FinanceCenterMumarenReceivableOrder: {1: order}})
    with pytest.raises(HTTPException) as exc:
        await update_ar_ap_order(
            order_id=1, body=ArApOrderUpdate(book_id=2, total_amount=Decimal("2000")),
            order_type="receivable", current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_receivable_order_rejects_total_below_settled():
    order = _receivable(oid=1, status="draft")
    order.settled_amount = Decimal("800")
    db = _MockDb(get_map={FinanceCenterMumarenReceivableOrder: {1: order}})
    with pytest.raises(HTTPException) as exc:
        await update_ar_ap_order(
            order_id=1, body=ArApOrderUpdate(book_id=1, total_amount=Decimal("500")),
            order_type="receivable", current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_payable_order_only_in_draft():
    reviewed = _payable(oid=1, status="reviewed")
    db = _MockDb(get_map={FinanceCenterMumarenPayableOrder: {1: reviewed}})
    with pytest.raises(HTTPException) as exc:
        await delete_ar_ap_order(order_id=1, order_type="payable", book_id=1, current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 409

    draft = _payable(oid=1, status="draft")
    db2 = _MockDb(get_map={FinanceCenterMumarenPayableOrder: {1: draft}})
    res = await delete_ar_ap_order(order_id=1, order_type="payable", book_id=1, current_user=_FakeUser(), db=db2)
    assert res.success
    assert len(db2.deleted) == 1
    logs = db2.audit_logs("delete_payable_order")
    assert len(logs) == 1
