"""Task 6: 会计期间结账/反结账路由测试(复用 fiscal_periods)。"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from mumaren_crud_helpers import _FakeUser, _MockDb, _MockResult

from app.api.v1.mumaren_finance_center_domains import (
    close_fiscal_period,
    list_fiscal_periods,
    reopen_fiscal_period,
)
from app.models.mumaren_finance_center import FinanceCenterMumarenFiscalPeriod


def _period(*, pid=1, book_id=1, status="open"):
    return FinanceCenterMumarenFiscalPeriod(
        id=pid, book_id=book_id, period_code="2026-07",
        start_date=date(2026, 7, 1), end_date=date(2026, 7, 31),
        status=status, closed_by=None, closed_at=None,
    )


@pytest.mark.asyncio
async def test_list_fiscal_periods_returns_rows():
    db = _MockDb(execute_results=[_MockResult(scalars=[_period(pid=1)])])
    res = await list_fiscal_periods(book_id=1, limit=100, _=_FakeUser(), db=db)
    assert len(res.data) == 1
    assert res.data[0]["period_code"] == "2026-07"


@pytest.mark.asyncio
async def test_close_period_succeeds_when_all_posted_and_balanced():
    period = _period(pid=1, status="open")
    db = _MockDb(
        get_map={FinanceCenterMumarenFiscalPeriod: {1: period}},
        execute_results=[
            _MockResult(scalar=0),                       # 未过账凭证数
            _MockResult(one=(Decimal("100"), Decimal("100"))),  # 借贷合计
        ],
    )
    res = await close_fiscal_period(period_id=1, current_user=_FakeUser(user_id=7), db=db)
    assert res.data["status"] == "closed"
    assert res.data["closed_by"] == 7
    assert res.data["closed_at"] is not None
    assert len(db.audit_logs("close_period")) == 1


@pytest.mark.asyncio
async def test_close_period_rejects_when_unposted_vouchers_exist():
    period = _period(pid=1, status="open")
    db = _MockDb(
        get_map={FinanceCenterMumarenFiscalPeriod: {1: period}},
        execute_results=[_MockResult(scalar=2)],  # 存在未过账凭证
    )
    with pytest.raises(HTTPException) as exc:
        await close_fiscal_period(period_id=1, current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 409
    assert db.audit_logs() == []


@pytest.mark.asyncio
async def test_close_period_rejects_unbalanced_trial():
    period = _period(pid=1, status="open")
    db = _MockDb(
        get_map={FinanceCenterMumarenFiscalPeriod: {1: period}},
        execute_results=[
            _MockResult(scalar=0),
            _MockResult(one=(Decimal("100"), Decimal("90"))),  # 借贷不平
        ],
    )
    with pytest.raises(HTTPException) as exc:
        await close_fiscal_period(period_id=1, current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_close_period_rejects_non_open_status():
    period = _period(pid=1, status="closed")
    db = _MockDb(get_map={FinanceCenterMumarenFiscalPeriod: {1: period}})
    with pytest.raises(HTTPException) as exc:
        await close_fiscal_period(period_id=1, current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_reopen_period_requires_admin():
    closed = _period(pid=1, status="closed")
    db = _MockDb(get_map={FinanceCenterMumarenFiscalPeriod: {1: closed}})
    with pytest.raises(HTTPException) as exc:
        await reopen_fiscal_period(period_id=1, current_user=_FakeUser(is_admin=False), db=db)
    assert exc.value.status_code == 403
    assert db.audit_logs() == []


@pytest.mark.asyncio
async def test_reopen_period_transitions_closed_to_open_for_admin():
    closed = _period(pid=1, status="closed")
    closed.closed_by = 7
    closed.closed_at = datetime.now(timezone.utc)
    db = _MockDb(get_map={FinanceCenterMumarenFiscalPeriod: {1: closed}})
    res = await reopen_fiscal_period(period_id=1, current_user=_FakeUser(user_id=9, is_admin=True), db=db)
    assert res.data["status"] == "open"
    assert res.data["closed_by"] is None
    assert res.data["closed_at"] is None
    assert len(db.audit_logs("reopen_period")) == 1
