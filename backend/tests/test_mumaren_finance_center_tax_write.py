"""税务独立写入 API 的 TDD 测试。

验证新模块在 ``finance_center_mumaren`` schema 内提供"草稿 → 财务审核 →
人工缴税"的固定流程,且严格不产生任何凭证分录、不跨账簿关联 tax type。
所有用例只通过 mock Db 验证服务层行为,不触碰真实数据库。
"""
import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

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
        self.book = SimpleNamespace(is_readonly=False)

    async def execute(self, statement):
        text = str(statement)
        if "finance_center_mumaren_tax_types" in text:
            return _Result(self.tax_type)
        if "finance_center_mumaren_tax_records" in text:
            return _Result(self.record)
        return _Result(None)

    async def get(self, model, primary_id):
        if model.__name__ == "FinanceCenterMumarenBook":
            return self.book
        if model is FinanceCenterMumarenTaxRecord and self.record is not None:
            return self.record
        return None

    def add(self, item):
        self.added.append(item)

    async def delete(self, item):
        self.deleted.append(item)

    async def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None:
                self._next_id += 1
                item.id = self._next_id

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


@pytest.mark.asyncio
async def test_delete_tax_draft_uses_real_database_and_preserves_book_and_workflow_guards(monkeypatch):
    """Only a current-book draft can be deleted, with an in-transaction audit record."""
    from fastapi import HTTPException
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.api.v1 import mumaren_finance_center_domains
    from app.core.database import Base
    from app.models.mumaren_finance_center import (
        MUMAREN_FINANCE_SCHEMA,
        FinanceCenterMumarenAuditLog,
        FinanceCenterMumarenBook,
    )

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        execution_options={"schema_translate_map": {MUMAREN_FINANCE_SCHEMA: None}},
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=[
                        FinanceCenterMumarenBook.__table__,
                        FinanceCenterMumarenTaxType.__table__,
                        FinanceCenterMumarenTaxRecord.__table__,
                        FinanceCenterMumarenAuditLog.__table__,
                    ],
                )
            )

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as db:
            original_add_audit_log = mumaren_finance_center_domains._add_audit_log

            def add_sqlite_compatible_audit_log(*args, **kwargs):
                original_add_audit_log(*args, **kwargs)
                audit_log = next(
                    row for row in reversed(list(db.new))
                    if isinstance(row, FinanceCenterMumarenAuditLog)
                )
                audit_log.id = 1

            monkeypatch.setattr(
                mumaren_finance_center_domains,
                "_add_audit_log",
                add_sqlite_compatible_audit_log,
            )
            current = FinanceCenterMumarenBook(id=1, book_code="CURRENT", book_name="当前账", status="active", is_readonly=False)
            other = FinanceCenterMumarenBook(id=2, book_code="OTHER", book_name="另一账", status="active", is_readonly=False)
            history = FinanceCenterMumarenBook(id=3, book_code="K3", book_name="金蝶账", status="active", is_readonly=True, source_system="kingdee_history")
            db.add_all([current, other, history])
            db.add_all([
                _tax_type(book_id=1, tt_id=11),
                _tax_type(book_id=2, tt_id=22),
                _tax_type(book_id=3, tt_id=33),
            ])
            db.add_all([
                FinanceCenterMumarenTaxRecord(id=101, book_id=1, tax_type_id=11, period="2026-07", tax_amount=Decimal("100"), paid_amount=Decimal("0"), status="pending", workflow_status="draft"),
                FinanceCenterMumarenTaxRecord(id=102, book_id=1, tax_type_id=11, period="2026-08", tax_amount=Decimal("100"), paid_amount=Decimal("0"), status="pending", workflow_status="reviewed"),
                FinanceCenterMumarenTaxRecord(id=201, book_id=2, tax_type_id=22, period="2026-07", tax_amount=Decimal("100"), paid_amount=Decimal("0"), status="pending", workflow_status="draft"),
                FinanceCenterMumarenTaxRecord(id=301, book_id=3, tax_type_id=33, period="2026-07", tax_amount=Decimal("100"), paid_amount=Decimal("0"), status="pending", workflow_status="draft"),
            ])
            await db.commit()

            response = await mumaren_finance_center_domains.delete_tax_record_endpoint(
                record_id=101, book_id=1, current_user=SimpleNamespace(id=42), db=db,
            )
            assert response.message == "税务草稿已删除"
            assert await db.get(FinanceCenterMumarenTaxRecord, 101) is None
            audit_logs = list((await db.execute(select(FinanceCenterMumarenAuditLog))).scalars())
            assert [(log.book_id, log.action, log.operator_id, log.detail) for log in audit_logs] == [
                (1, "delete_tax_record", 42, "删除税务草稿 101"),
            ]

            with pytest.raises(HTTPException) as cross_book:
                await mumaren_finance_center_domains.delete_tax_record_endpoint(record_id=201, book_id=1, current_user=SimpleNamespace(id=42), db=db)
            assert cross_book.value.status_code == 400
            assert await db.get(FinanceCenterMumarenTaxRecord, 201) is not None

            with pytest.raises(HTTPException) as reviewed:
                await mumaren_finance_center_domains.delete_tax_record_endpoint(record_id=102, book_id=1, current_user=SimpleNamespace(id=42), db=db)
            assert reviewed.value.status_code == 409
            assert await db.get(FinanceCenterMumarenTaxRecord, 102) is not None

            with pytest.raises(HTTPException) as readonly:
                await mumaren_finance_center_domains.delete_tax_record_endpoint(record_id=301, book_id=3, current_user=SimpleNamespace(id=42), db=db)
            assert readonly.value.status_code == 409
            assert await db.get(FinanceCenterMumarenTaxRecord, 301) is not None

            with pytest.raises(HTTPException) as missing:
                await mumaren_finance_center_domains.delete_tax_record_endpoint(record_id=999, book_id=1, current_user=SimpleNamespace(id=42), db=db)
            assert missing.value.status_code == 404
    finally:
        await engine.dispose()
