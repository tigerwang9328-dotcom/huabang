from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from mumaren_crud_helpers import _FakeUser, _MockDb, _MockResult
from app.api.v1.mumaren_finance_center_domains import (
    initialize_fiscal_period,
    precheck_fiscal_period,
    close_fiscal_period,
)
from app.models.mumaren_finance_center import FinanceCenterMumarenFiscalPeriod


def _period(*, pid=1, book_id=1, status="open"):
    return FinanceCenterMumarenFiscalPeriod(
        id=pid, book_id=book_id, period_code="2026-07",
        start_date=date(2026, 7, 1), end_date=date(2026, 7, 31), status=status,
    )


@pytest.mark.asyncio
async def test_initialize_period_is_idempotent_for_same_book_and_period():
    existing = _period()
    db = _MockDb(execute_results=[_MockResult(scalar=existing)])
    result = await initialize_fiscal_period(
        book_id=1, period="2026-07", current_user=_FakeUser(), db=db,
    )
    assert result.data["period_code"] == "2026-07"
    assert db.added == []


@pytest.mark.asyncio
async def test_precheck_reports_unposted_vouchers_as_blocking():
    period = _period()
    db = _MockDb(
        get_map={FinanceCenterMumarenFiscalPeriod: {1: period}},
        execute_results=[
            _MockResult(scalar=period),  # initialized period
            _MockResult(scalar=2),  # unposted vouchers
            _MockResult(scalar=0),  # unbalanced vouchers
            _MockResult(scalar=0),  # payroll
            _MockResult(scalar=0),  # tax
            _MockResult(scalar=0),  # invoices
            _MockResult(scalar=0),  # cash flows
            _MockResult(scalar=0),  # receivable/payable
            _MockResult(scalar=0),  # fixed assets
            _MockResult(scalar=0),  # profit/loss amount
        ],
    )
    result = await precheck_fiscal_period(
        book_id=1, period="2026-07", current_user=_FakeUser(), db=db,
    )
    assert result.data["can_close"] is False
    assert result.data["blocking_count"] == 1
    assert next(item for item in result.data["checks"] if item["key"] == "unposted_vouchers")["passed"] is False


@pytest.mark.asyncio
async def test_close_rejects_period_from_another_book():
    period = _period(book_id=2)
    db = _MockDb(get_map={FinanceCenterMumarenFiscalPeriod: {1: period}})
    with pytest.raises(HTTPException) as exc:
        await close_fiscal_period(
            period_id=1, book_id=1, current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 400
