import os
from decimal import Decimal

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
    post_voucher,
    review_voucher,
    validate_voucher_lines,
)


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
