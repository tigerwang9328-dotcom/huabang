"""Task 12: 销售月报 CRUD 路由测试(finance_center_mumaren_sales_monthly_reports)。"""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from mumaren_crud_helpers import _FakeUser, _MockDb, _MockResult

from app.api.v1.mumaren_finance_center_crud import (
    SalesMonthlyReportInput,
    SalesMonthlyReportUpdate,
    create_sales_monthly_report,
    delete_sales_monthly_report,
    list_sales_monthly_reports,
    update_sales_monthly_report,
)
from app.models.mumaren_finance_center_domains import FinanceCenterMumarenSalesMonthlyReport


def _report(*, rid=1, book_id=1, period="2026-07", store="134681"):
    return FinanceCenterMumarenSalesMonthlyReport(
        id=rid, book_id=book_id, period=period,
        store_code=store, store_name="花果园锐煌写字楼店",
        sales_amount=Decimal("13519.00"), remark="7月销售",
        created_by=5,
    )


@pytest.mark.asyncio
async def test_create_sales_monthly_report_persists_and_writes_audit_log():
    db = _MockDb()
    res = await create_sales_monthly_report(
        body=SalesMonthlyReportInput(
            book_id=1, period="2026-07", store_code="134681",
            store_name="花果园锐煌写字楼店", sales_amount=Decimal("13519"),
        ),
        current_user=_FakeUser(user_id=5), db=db,
    )
    assert res.data["store_code"] == "134681"
    assert res.data["sales_amount"] == Decimal("13519")
    logs = db.audit_logs("create_sales_monthly_report")
    assert len(logs) == 1
    assert logs[0].operator_id == 5


@pytest.mark.asyncio
async def test_list_sales_monthly_reports_filters_by_period():
    rows = [_report(rid=1, period="2026-07"), _report(rid=2, period="2026-06")]
    db = _MockDb(execute_results=[_MockResult(scalars=rows)])
    res = await list_sales_monthly_reports(book_id=1, period="2026-07", limit=100, _=_FakeUser(), db=db)
    assert len(res.data) == 2
    assert res.data[0]["period"] == "2026-07"


@pytest.mark.asyncio
async def test_update_sales_monthly_report_rejects_cross_book_and_writes_audit_log():
    report = _report(rid=1, book_id=1)
    db = _MockDb(get_map={FinanceCenterMumarenSalesMonthlyReport: {1: report}})
    with pytest.raises(HTTPException) as exc:
        await update_sales_monthly_report(
            report_id=1, body=SalesMonthlyReportUpdate(book_id=2, store_name="新名"),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 400
    assert db.audit_logs() == []

    report2 = _report(rid=1, book_id=1)
    db2 = _MockDb(get_map={FinanceCenterMumarenSalesMonthlyReport: {1: report2}})
    updated = await update_sales_monthly_report(
        report_id=1, body=SalesMonthlyReportUpdate(book_id=1, store_name="新名"),
        current_user=_FakeUser(user_id=8), db=db2,
    )
    assert updated.data["store_name"] == "新名"
    assert len(db2.audit_logs("update_sales_monthly_report")) == 1


@pytest.mark.asyncio
async def test_update_sales_monthly_report_returns_404_when_missing():
    db = _MockDb(get_map={FinanceCenterMumarenSalesMonthlyReport: {}})
    with pytest.raises(HTTPException) as exc:
        await update_sales_monthly_report(
            report_id=999, body=SalesMonthlyReportUpdate(book_id=1, store_name="x"),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_sales_monthly_report_writes_audit_log_and_rejects_cross_book():
    report = _report(rid=1, book_id=1)
    db = _MockDb(get_map={FinanceCenterMumarenSalesMonthlyReport: {1: report}})
    res = await delete_sales_monthly_report(report_id=1, book_id=1, current_user=_FakeUser(user_id=9), db=db)
    assert res.success
    assert len(db.deleted) == 1
    assert len(db.audit_logs("delete_sales_monthly_report")) == 1

    report2 = _report(rid=2, book_id=1)
    db2 = _MockDb(get_map={FinanceCenterMumarenSalesMonthlyReport: {2: report2}})
    with pytest.raises(HTTPException) as exc:
        await delete_sales_monthly_report(report_id=2, book_id=99, current_user=_FakeUser(), db=db2)
    assert exc.value.status_code == 400
