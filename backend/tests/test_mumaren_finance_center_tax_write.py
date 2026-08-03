"""税务独立写入 API 的 TDD 测试。

验证新模块在 ``finance_center_mumaren`` schema 内提供"草稿 → 财务审核 →
人工缴税"的固定流程,且严格不产生任何凭证分录、不跨账簿关联 tax type。
所有用例只通过 mock Db 验证服务层行为,不触碰真实数据库。
"""
import os
from datetime import date
from decimal import Decimal

import pytest


os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("DB_PASSWORD", "test-only-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")

from app.models.mumaren_finance_center import (
    FinanceCenterMumarenVoucher,
    FinanceCenterMumarenVoucherLine,
)
from app.models.mumaren_finance_center_domains import (
    FinanceCenterMumarenTaxRecord,
    FinanceCenterMumarenTaxType,
)


class _Result:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _MockDb:
    def __init__(self, *, tax_type=None, record=None):
        self.added = []
        self.deleted = []
        self.tax_type = tax_type
        self.record = record
        self._next_id = 100

    async def execute(self, statement):
        text = str(statement)
        if "finance_center_mumaren_tax_types" in text:
            return _Result(self.tax_type)
        if "finance_center_mumaren_tax_records" in text:
            return _Result(self.record)
        return _Result(None)

    def add(self, item):
        self.added.append(item)

    async def delete(self, item):
        self.deleted.append(item)

    async def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None:
                self._next_id += 1
                item.id = self._next_id

    async def get(self, model, primary_id):
        if model is FinanceCenterMumarenTaxRecord and self.record is not None:
            return self.record
        return None

    @property
    def voucher_entries(self):
        return [item for item in self.added if isinstance(item, (FinanceCenterMumarenVoucher, FinanceCenterMumarenVoucherLine))]


def _tax_type(book_id=1, tt_id=10):
    return FinanceCenterMumarenTaxType(
        id=tt_id, book_id=book_id, tax_code="VAT", tax_name="增值税",
        default_rate=Decimal("0.13"), is_active=True,
    )


# ---------------------------------------------------------------------------
# SubTask 3.1: 创建税务草稿
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_tax_draft_persists_record_in_draft_status_without_voucher_entries():
    from app.services.mumaren_finance_center.tax import create_tax_record

    db = _MockDb(tax_type=_tax_type(book_id=1))
    record = await create_tax_record(
        db,
        book_id=1,
        tax_type_id=10,
        period="2026-07",
        tax_amount=Decimal("500.00"),
        operator_id=5,
        due_date=date(2026, 8, 15),
    )

    assert isinstance(record, FinanceCenterMumarenTaxRecord)
    assert record.book_id == 1
    assert record.workflow_status == "draft"
    assert record.status == "pending"
    assert record.paid_amount == Decimal("0")
    assert record.tax_amount == Decimal("500.00")
    assert record.voucher_id is None
    assert db.voucher_entries == []


@pytest.mark.asyncio
async def test_delete_tax_draft_deletes_only_draft_record():
    from app.services.mumaren_finance_center.tax import InvalidTaxTransition, delete_tax_record

    draft = FinanceCenterMumarenTaxRecord(
        id=1, book_id=1, tax_type_id=10, period="2026-07",
        tax_amount=Decimal("100.00"), paid_amount=Decimal("0"),
        status="pending", workflow_status="draft",
    )
    db = _MockDb(record=draft)
    await delete_tax_record(db, record_id=1, book_id=1)
    assert draft in db.deleted

    reviewed = FinanceCenterMumarenTaxRecord(
        id=2, book_id=1, tax_type_id=10, period="2026-07",
        tax_amount=Decimal("100.00"), paid_amount=Decimal("0"),
        status="pending", workflow_status="reviewed",
    )
    with pytest.raises(InvalidTaxTransition):
        await delete_tax_record(_MockDb(record=reviewed), record_id=2, book_id=1)


# ---------------------------------------------------------------------------
# SubTask 3.2: 财务审核税务单据
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_review_tax_draft_transitions_to_reviewed_and_blocks_non_draft():
    from app.services.mumaren_finance_center.tax import (
        InvalidTaxTransition,
        review_tax_record,
    )

    record = FinanceCenterMumarenTaxRecord(
        id=1, book_id=1, tax_type_id=10, period="2026-07",
        tax_amount=Decimal("500.00"), paid_amount=Decimal("0"),
        due_date=date(2026, 8, 15), status="pending", workflow_status="draft",
    )
    db = _MockDb(record=record)

    reviewed = await review_tax_record(db, record_id=1, operator_id=7)
    assert reviewed.workflow_status == "reviewed"
    assert db.voucher_entries == []

    # 已审核再审核应被拒绝
    db2 = _MockDb(record=reviewed)
    with pytest.raises(InvalidTaxTransition):
        await review_tax_record(db2, record_id=1, operator_id=7)


# ---------------------------------------------------------------------------
# SubTask 3.3: 人工缴税防超额
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pay_tax_rejects_overpayment_and_updates_status():
    from app.services.mumaren_finance_center.tax import pay_tax_record

    record = FinanceCenterMumarenTaxRecord(
        id=1, book_id=1, tax_type_id=10, period="2026-07",
        tax_amount=Decimal("1000.00"), paid_amount=Decimal("700.00"),
        due_date=date(2026, 8, 15), status="pending", workflow_status="reviewed",
    )
    # 超额缴税应被拒绝
    db_over = _MockDb(record=record)
    with pytest.raises(ValueError, match="超过"):
        await pay_tax_record(
            db_over, record_id=1, payment_date=date(2026, 8, 10),
            amount=Decimal("400.00"), operator_id=8,
        )
    assert not any(isinstance(item, FinanceCenterMumarenTaxRecord) for item in db_over.added)

    # 正常缴税
    db_ok = _MockDb(record=record)
    await pay_tax_record(
        db_ok, record_id=1, payment_date=date(2026, 8, 10),
        amount=Decimal("300.00"), operator_id=8,
    )
    assert record.paid_amount == Decimal("1000.00")
    assert record.status == "paid"
    assert db_ok.voucher_entries == []


# ---------------------------------------------------------------------------
# SubTask 3.4: 税务跨账簿 tax type 校验
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_tax_rejects_tax_type_from_another_book():
    from app.services.mumaren_finance_center.tax import (
        CrossBookTaxViolationError,
        create_tax_record,
    )

    # tax_type 属于 book_id=2,但记录要写到 book_id=1
    db = _MockDb(tax_type=_tax_type(book_id=2, tt_id=10))
    with pytest.raises(CrossBookTaxViolationError):
        await create_tax_record(
            db,
            book_id=1,
            tax_type_id=10,
            period="2026-07",
            tax_amount=Decimal("100.00"),
            operator_id=5,
        )
    assert db.added == []


# ---------------------------------------------------------------------------
# SubTask 3.5: 校验新写入不产生任何凭证分录
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tax_full_write_flow_never_creates_voucher_or_voucher_line():
    from app.services.mumaren_finance_center.tax import (
        create_tax_record,
        pay_tax_record,
        review_tax_record,
    )

    db = _MockDb(tax_type=_tax_type(book_id=1))
    record = await create_tax_record(
        db, book_id=1, tax_type_id=10, period="2026-07",
        tax_amount=Decimal("200.00"), operator_id=5, due_date=date(2026, 8, 15),
    )
    record.id = 1
    db.record = record
    await review_tax_record(db, record_id=1, operator_id=7)
    await pay_tax_record(
        db, record_id=1, payment_date=date(2026, 8, 10),
        amount=Decimal("200.00"), operator_id=8,
    )

    assert db.voucher_entries == []
