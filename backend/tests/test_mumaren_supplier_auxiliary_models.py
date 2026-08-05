from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.mumaren_finance_center import (
    MUMAREN_FINANCE_SCHEMA,
    FinanceCenterMumarenAccount,
    FinanceCenterMumarenBook,
    FinanceCenterMumarenVoucher,
    FinanceCenterMumarenVoucherLine,
)
from app.models.mumaren_finance_center_domains import FinanceCenterMumarenAuxiliaryAccounting
from app.models.mumaren_finance_center_auxiliary import (
    FinanceCenterMumarenAccountAuxiliaryDimension,
    FinanceCenterMumarenVoucherLineAuxiliary,
)


def test_supplier_auxiliary_configuration_and_line_value_are_book_scoped():
    engine = create_engine(
        "sqlite:///:memory:",
        execution_options={"schema_translate_map": {MUMAREN_FINANCE_SCHEMA: None}},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            FinanceCenterMumarenBook.__table__,
            FinanceCenterMumarenAccount.__table__,
            FinanceCenterMumarenVoucher.__table__,
            FinanceCenterMumarenVoucherLine.__table__,
            FinanceCenterMumarenAuxiliaryAccounting.__table__,
            FinanceCenterMumarenAccountAuxiliaryDimension.__table__,
            FinanceCenterMumarenVoucherLineAuxiliary.__table__,
        ],
    )
    with Session(engine) as db:
        book = FinanceCenterMumarenBook(id=1, book_code="CURRENT", book_name="当前账", is_readonly=False)
        db.add(book)
        db.flush()
        account = FinanceCenterMumarenAccount(
            id=2, book_id=book.id, account_code="2202", account_name="应付账款", account_type="liability", direction="credit",
        )
        supplier = FinanceCenterMumarenAuxiliaryAccounting(
            id=3, book_id=book.id, aux_type="supplier", code="S001", name="供应商 A", is_active=True,
        )
        db.add_all([account, supplier])
        db.flush()
        config = FinanceCenterMumarenAccountAuxiliaryDimension(
            id=4, account_id=account.id, book_id=book.id, aux_type="supplier", is_required=True,
        )
        voucher = FinanceCenterMumarenVoucher(
            id=5, book_id=book.id, voucher_no="记-001", voucher_date=date(2026, 8, 4), status="draft",
            total_debit=Decimal("100"), total_credit=Decimal("100"),
        )
        db.add_all([config, voucher])
        db.flush()
        line = FinanceCenterMumarenVoucherLine(
            id=6, voucher_id=voucher.id, line_no=1, account_id=account.id, credit_amount=Decimal("100"), debit_amount=Decimal("0"),
        )
        db.add(line)
        db.flush()
        db.add(FinanceCenterMumarenVoucherLineAuxiliary(
            id=7, voucher_line_id=line.id, book_id=book.id, aux_type="supplier", auxiliary_id=supplier.id,
            auxiliary_code_snapshot="S001", auxiliary_name_snapshot="供应商 A",
        ))
        db.commit()

        values = list(db.execute(select(FinanceCenterMumarenVoucherLineAuxiliary)).scalars())
        assert len(values) == 1
        assert values[0].auxiliary_name_snapshot == "供应商 A"
    engine.dispose()
