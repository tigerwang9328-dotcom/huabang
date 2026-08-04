import os
from datetime import date as real_date
from decimal import Decimal
from types import SimpleNamespace

import pytest


# 模型导入会加载华邦配置；这些仅是单测导入所需的无效占位值。
os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("DB_PASSWORD", "test-only-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")

from app.models.mumaren_finance_center import FinanceCenterMumarenHistoryVoucher, FinanceCenterMumarenVoucher
from app.services.mumaren_finance_center.workflow import (
    HistoricalRecordReadonlyError,
    InvalidVoucherTransition,
    UnbalancedVoucherError,
    assert_history_readonly,
    create_voucher,
    next_voucher_number,
    post_voucher,
    review_voucher,
    validate_voucher_lines,
)
from mumaren_crud_helpers import _MockDb, _MockResult


@pytest.mark.asyncio
async def test_next_voucher_number_fills_first_gap_for_book_date_and_type():
    db = _MockDb(execute_results=[_MockResult(scalars=[
        "记-202608-001", "记-202608-003", "记-202607-099",
    ])])

    number = await next_voucher_number(db, book_id=7, voucher_date=real_date(2026, 8, 2), voucher_type="记")

    assert number == "记-202608-002"


def test_draft_voucher_must_be_reviewed_before_manual_posting():
    voucher = FinanceCenterMumarenVoucher(status="draft")

    with pytest.raises(InvalidVoucherTransition, match="审核"):
        post_voucher(voucher, operator_id=8)

    review_voucher(voucher, operator_id=7)
    post_voucher(voucher, operator_id=8)

    assert voucher.status == "posted"
    assert voucher.reviewed_by == 7
    assert voucher.posted_by == 8


def test_voucher_lines_must_balance_and_each_line_has_one_side_only():
    balanced = [
        {"debit_amount": Decimal("100.00"), "credit_amount": Decimal("0")},
        {"debit_amount": Decimal("0"), "credit_amount": Decimal("100.00")},
    ]
    validate_voucher_lines(balanced)

    with pytest.raises(UnbalancedVoucherError, match="借贷不平衡"):
        validate_voucher_lines([
            {"debit_amount": Decimal("100.00"), "credit_amount": Decimal("0")},
            {"debit_amount": Decimal("0"), "credit_amount": Decimal("99.99")},
        ])

    with pytest.raises(UnbalancedVoucherError, match="同一分录"):
        validate_voucher_lines([{"debit_amount": Decimal("1"), "credit_amount": Decimal("1")}])

    with pytest.raises(UnbalancedVoucherError, match="必须填写借方或贷方金额"):
        validate_voucher_lines([
            {"debit_amount": Decimal("100"), "credit_amount": Decimal("0")},
            {"debit_amount": Decimal("0"), "credit_amount": Decimal("0")},
            {"debit_amount": Decimal("0"), "credit_amount": Decimal("100")},
        ])


def test_historical_voucher_cannot_enter_current_workflow():
    history = FinanceCenterMumarenHistoryVoucher(
        source_system="kingdee",
        source_key="KD-2024-0002",
        voucher_no="记-2024-0002",
        voucher_date="2024-02-29",
        summary="历史凭证",
    )

    with pytest.raises(HistoricalRecordReadonlyError, match="历史数据只读"):
        assert_history_readonly(history)


@pytest.mark.asyncio
async def test_create_voucher_rejects_an_account_from_another_book():
    class Result:
        def scalar_one_or_none(self):
            return None

    class Db:
        def add(self, _item):
            pass

        async def flush(self):
            pass

        async def execute(self, _statement):
            assert "finance_center_mumaren_accounts.book_id" in str(_statement)
            return Result()

    with pytest.raises(ValueError, match="不属于账簿"):
        await create_voucher(
            Db(),
            book_id=1,
            voucher_no="记-001",
            voucher_date="2026-07-31",
            operator_id=1,
            lines=[
                {"account_id": 9, "debit_amount": "100", "credit_amount": "0"},
                {"account_id": 9, "debit_amount": "0", "credit_amount": "100"},
            ],
        )


@pytest.mark.asyncio
async def test_create_voucher_rejects_unbalanced_lines_before_persistence():
    from unittest.mock import AsyncMock

    from app.services.mumaren_finance_center.workflow import create_voucher

    db = AsyncMock()
    with pytest.raises(UnbalancedVoucherError, match="借贷不平衡"):
        await create_voucher(
            db,
            book_id=1,
            voucher_no="记-0001",
            voucher_date="2026-07-31",
            lines=[
                {"account_id": 1, "debit_amount": "100.00", "credit_amount": "0"},
                {"account_id": 2, "debit_amount": "0", "credit_amount": "99.99"},
            ],
            operator_id=1,
        )
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_book_initializes_a_writable_book_with_current_year_periods_and_audit(monkeypatch):
    from app.models.mumaren_finance_center import (
        FinanceCenterMumarenAccount,
        FinanceCenterMumarenAuditLog,
        FinanceCenterMumarenBook,
        FinanceCenterMumarenFiscalPeriod,
    )
    from app.services.mumaren_finance_center import workflow

    class CurrentDate(real_date):
        @classmethod
        def today(cls):
            return cls(2027, 3, 15)

    monkeypatch.setattr(workflow, "date", CurrentDate)
    db = _MockDb(execute_results=[_MockResult(scalar=None)])

    book = await workflow.create_book(
        db, book_code="CURRENT-2027", book_name="2027 当前账", company_name="华邦",
        status="active", operator_id=7,
    )

    assert book.id == 1001
    assert book.is_readonly is False
    accounts = [item for item in db.added if isinstance(item, FinanceCenterMumarenAccount)]
    periods = [item for item in db.added if isinstance(item, FinanceCenterMumarenFiscalPeriod)]
    audits = [item for item in db.added if isinstance(item, FinanceCenterMumarenAuditLog)]
    assert len(accounts) == 15
    assert {period.period_code for period in periods} == {f"2027-{month:02d}" for month in range(1, 13)}
    assert all(period.book_id == book.id and period.status == "open" for period in periods)
    assert [(audit.book_id, audit.action, audit.operator_id, audit.detail) for audit in audits] == [
        (book.id, "create_book", 7, "CURRENT-2027")
    ]


@pytest.mark.asyncio
async def test_delete_voucher_endpoint_deletes_only_writable_drafts_and_retains_audit():
    from fastapi import HTTPException

    from app.api.v1.mumaren_finance_center import delete_draft_voucher
    from app.models.mumaren_finance_center import FinanceCenterMumarenAuditLog

    draft = FinanceCenterMumarenVoucher(id=41, book_id=9, voucher_no="记-001", status="draft", is_readonly=False)
    db = _MockDb(get_map={FinanceCenterMumarenVoucher: {41: draft}})
    result = await delete_draft_voucher(41, SimpleNamespace(id=8), db)

    assert draft in db.deleted
    audit = next(item for item in db.added if isinstance(item, FinanceCenterMumarenAuditLog))
    assert (audit.book_id, audit.voucher_id, audit.action, audit.operator_id, audit.detail) == (9, 41, "delete_voucher", 8, "记-001")
    assert result.message == "草稿凭证已删除"

    for voucher in (
        FinanceCenterMumarenVoucher(id=42, book_id=9, voucher_no="记-历史", status="posted", is_readonly=True),
        FinanceCenterMumarenVoucher(id=43, book_id=9, voucher_no="记-已审", status="reviewed", is_readonly=False),
    ):
        with pytest.raises(HTTPException, match="禁止删除|仅草稿") as error:
            await delete_draft_voucher(voucher.id, SimpleNamespace(id=8), _MockDb(get_map={FinanceCenterMumarenVoucher: {voucher.id: voucher}}))
        assert error.value.status_code == 409
