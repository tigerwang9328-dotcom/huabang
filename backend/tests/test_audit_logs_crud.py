"""Task 8: 审计日志查询路由测试(复用 audit_logs)。"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from mumaren_crud_helpers import _FakeUser, _MockDb, _MockResult

from app.api.v1.mumaren_finance_center_domains import list_audit_logs
from app.models.mumaren_finance_center import FinanceCenterMumarenAuditLog


def _log(*, log_id=1, book_id=1, action="create_invoice", operator_id=5, detail="x"):
    return FinanceCenterMumarenAuditLog(
        id=log_id, book_id=book_id, voucher_id=None, action=action,
        operator_id=operator_id, detail=detail,
        created_at=datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_list_audit_logs_returns_rows_with_expected_fields():
    rows = [_log(log_id=1), _log(log_id=2, action="verify_invoice", operator_id=6)]
    db = _MockDb(execute_results=[_MockResult(scalars=rows)])
    res = await list_audit_logs(book_id=1, limit=100, _=_FakeUser(), db=db)
    assert res.success
    assert len(res.data) == 2
    first = res.data[0]
    for key in ("id", "book_id", "voucher_id", "action", "operator_id", "detail", "created_at"):
        assert key in first


@pytest.mark.asyncio
async def test_list_audit_logs_accepts_optional_filters():
    rows = [_log(log_id=1, action="create_fixed_asset")]
    db = _MockDb(execute_results=[_MockResult(scalars=rows)])
    res = await list_audit_logs(
        book_id=1, action="create_fixed_asset", operator_id=5,
        start_date=None, end_date=None, limit=50, _=_FakeUser(), db=db,
    )
    assert len(res.data) == 1
    assert res.data[0]["action"] == "create_fixed_asset"


@pytest.mark.asyncio
async def test_list_audit_logs_default_limit_bounded():
    # 直接调用路由需显式传 limit(Query 默认值只在 HTTP 层解析);
    # limit 约束(默认100/最大500)由 test_domain_read_routes_apply_a_bounded_response_limit 覆盖
    db = _MockDb(execute_results=[_MockResult(scalars=[])])
    res = await list_audit_logs(limit=100, _=_FakeUser(), db=db)
    assert res.data == []
