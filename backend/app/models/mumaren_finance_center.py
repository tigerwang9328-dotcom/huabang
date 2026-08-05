"""牧马人财务中心的独立领域模型。

这些表只属于 ``finance_center_mumaren`` schema，故意不关联华邦既有
``fin_*``、旧财务中心或金蝶来源表。迁移由独立 Alembic revision 负责创建。
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


MUMAREN_FINANCE_SCHEMA = "finance_center_mumaren"


class FinanceCenterMumarenBook(Base):
    __tablename__ = "finance_center_mumaren_books"
    __table_args__ = (
        UniqueConstraint("book_code", name="uq_mumaren_finance_book_code"),
        {"schema": MUMAREN_FINANCE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    book_code: Mapped[str] = mapped_column(String(64), nullable=False)
    book_name: Mapped[str] = mapped_column(String(128), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255))
    accounting_standard: Mapped[str] = mapped_column(String(64), nullable=False, default="小企业会计准则")
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="CNY")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    source_system: Mapped[str | None] = mapped_column(String(32))
    source_database: Mapped[str | None] = mapped_column(String(128))
    source_company_name: Mapped[str | None] = mapped_column(String(255))
    source_key: Mapped[str | None] = mapped_column(String(256))
    source_checksum: Mapped[str | None] = mapped_column(String(64))
    import_batch_key: Mapped[str | None] = mapped_column(String(128))
    is_readonly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FinanceCenterMumarenAccount(Base):
    __tablename__ = "finance_center_mumaren_accounts"
    __table_args__ = (
        UniqueConstraint("book_id", "account_code", name="uq_mumaren_finance_account_code"),
        {"schema": MUMAREN_FINANCE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(f"{MUMAREN_FINANCE_SCHEMA}.finance_center_mumaren_books.id"), nullable=False)
    account_code: Mapped[str] = mapped_column(String(64), nullable=False)
    account_name: Mapped[str] = mapped_column(String(128), nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False, default="debit")
    parent_id: Mapped[int | None] = mapped_column(BigInteger)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_system: Mapped[str | None] = mapped_column(String(32))
    source_key: Mapped[str | None] = mapped_column(String(256))
    source_checksum: Mapped[str | None] = mapped_column(String(64))
    import_batch_key: Mapped[str | None] = mapped_column(String(128))
    is_readonly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_payload: Mapped[dict | None] = mapped_column(JSON)


class FinanceCenterMumarenFiscalPeriod(Base):
    __tablename__ = "finance_center_mumaren_fiscal_periods"
    __table_args__ = (
        UniqueConstraint("book_id", "period_code", name="uq_mumaren_finance_period_code"),
        CheckConstraint("status IN ('open', 'closed')", name="ck_mumaren_finance_period_status"),
        {"schema": MUMAREN_FINANCE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(f"{MUMAREN_FINANCE_SCHEMA}.finance_center_mumaren_books.id"), nullable=False)
    period_code: Mapped[str] = mapped_column(String(7), nullable=False, comment="YYYY-MM")
    start_date: Mapped[object] = mapped_column(Date, nullable=False)
    end_date: Mapped[object] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    closed_by: Mapped[int | None] = mapped_column(BigInteger)
    closed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    source_system: Mapped[str | None] = mapped_column(String(32))
    source_key: Mapped[str | None] = mapped_column(String(256))
    source_checksum: Mapped[str | None] = mapped_column(String(64))
    import_batch_key: Mapped[str | None] = mapped_column(String(128))
    is_readonly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_payload: Mapped[dict | None] = mapped_column(JSON)


class FinanceCenterMumarenVoucher(Base):
    __tablename__ = "finance_center_mumaren_vouchers"
    __table_args__ = (
        UniqueConstraint("book_id", "voucher_no", name="uq_mumaren_finance_voucher_no"),
        CheckConstraint("status IN ('draft', 'reviewed', 'posted')", name="ck_mumaren_finance_voucher_status"),
        {"schema": MUMAREN_FINANCE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(f"{MUMAREN_FINANCE_SCHEMA}.finance_center_mumaren_books.id"), nullable=False)
    voucher_no: Mapped[str] = mapped_column(String(64), nullable=False)
    voucher_type: Mapped[str] = mapped_column(String(16), nullable=False, default="记")
    voucher_date: Mapped[object] = mapped_column(Date, nullable=False)
    summary: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    total_debit: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    total_credit: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    posted_by: Mapped[int | None] = mapped_column(BigInteger)
    posted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    source_system: Mapped[str | None] = mapped_column(String(32))
    source_database: Mapped[str | None] = mapped_column(String(128))
    source_key: Mapped[str | None] = mapped_column(String(256))
    source_checksum: Mapped[str | None] = mapped_column(String(64))
    import_batch_key: Mapped[str | None] = mapped_column(String(128))
    is_readonly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_normalized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceCenterMumarenVoucherLine(Base):
    __tablename__ = "finance_center_mumaren_voucher_lines"
    __table_args__ = (
        UniqueConstraint("voucher_id", "line_no", name="uq_mumaren_finance_voucher_line_no"),
        CheckConstraint(
            "(debit_amount > 0 AND credit_amount = 0) OR (debit_amount = 0 AND credit_amount > 0)",
            name="ck_mumaren_finance_line_one_side",
        ),
        {"schema": MUMAREN_FINANCE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    voucher_id: Mapped[int] = mapped_column(ForeignKey(f"{MUMAREN_FINANCE_SCHEMA}.finance_center_mumaren_vouchers.id", ondelete="CASCADE"), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey(f"{MUMAREN_FINANCE_SCHEMA}.finance_center_mumaren_accounts.id"), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(500))
    summary_explicitly_cleared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    debit_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    credit_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    source_system: Mapped[str | None] = mapped_column(String(32))
    source_key: Mapped[str | None] = mapped_column(String(256))
    source_checksum: Mapped[str | None] = mapped_column(String(64))
    import_batch_key: Mapped[str | None] = mapped_column(String(128))
    is_readonly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_payload: Mapped[dict | None] = mapped_column(JSON)


class FinanceCenterMumarenBalanceSnapshot(Base):
    """Readonly source balance evidence; never included in current-book reports."""

    __tablename__ = "finance_center_mumaren_balance_snapshots"
    __table_args__ = (
        UniqueConstraint("source_system", "source_database", "source_key", name="uq_mumaren_finance_balance_snapshot_source"),
        {"schema": MUMAREN_FINANCE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(f"{MUMAREN_FINANCE_SCHEMA}.finance_center_mumaren_books.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey(f"{MUMAREN_FINANCE_SCHEMA}.finance_center_mumaren_accounts.id"), nullable=False)
    period_code: Mapped[str] = mapped_column(String(7), nullable=False)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, default="kingdee_history")
    source_database: Mapped[str] = mapped_column(String(128), nullable=False)
    source_key: Mapped[str] = mapped_column(String(256), nullable=False)
    source_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    import_batch_key: Mapped[str] = mapped_column(String(128), nullable=False)
    is_readonly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    opening_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    period_debit: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    period_credit: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    closing_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    source_payload: Mapped[dict | None] = mapped_column(JSON)


class FinanceCenterMumarenKingdeeImportBatch(Base):
    __tablename__ = "finance_center_mumaren_kingdee_import_batches"
    __table_args__ = {"schema": MUMAREN_FINANCE_SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, default="kingdee_history")
    manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(16), nullable=False, default="planned")
    expected_book_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_voucher_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_balance_snapshot_count: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    validation_payload: Mapped[dict | None] = mapped_column(JSON)


class FinanceCenterMumarenAuditLog(Base):
    __tablename__ = "finance_center_mumaren_audit_logs"
    __table_args__ = {"schema": MUMAREN_FINANCE_SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    book_id: Mapped[int | None] = mapped_column(BigInteger)
    voucher_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    operator_id: Mapped[int | None] = mapped_column(BigInteger)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceCenterMumarenHistoryImportBatch(Base):
    __tablename__ = "finance_center_mumaren_history_import_batches"
    __table_args__ = (
        UniqueConstraint("source_system", "source_batch_key", name="uq_mumaren_finance_history_batch"),
        {"schema": MUMAREN_FINANCE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_batch_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_checksum: Mapped[str | None] = mapped_column(String(128))
    imported_by: Mapped[int | None] = mapped_column(BigInteger)
    imported_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)


class FinanceCenterMumarenHistoryVoucher(Base):
    __tablename__ = "finance_center_mumaren_history_vouchers"
    __table_args__ = (
        UniqueConstraint("source_system", "source_key", name="uq_mumaren_finance_history_voucher"),
        CheckConstraint("is_readonly = true", name="ck_mumaren_finance_history_readonly"),
        {"schema": MUMAREN_FINANCE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey(f"{MUMAREN_FINANCE_SCHEMA}.finance_center_mumaren_history_import_batches.id"), nullable=False)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_key: Mapped[str] = mapped_column(String(128), nullable=False)
    record_type: Mapped[str] = mapped_column(String(32), nullable=False, default="historical")
    is_readonly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    voucher_no: Mapped[str] = mapped_column(String(64), nullable=False)
    voucher_date: Mapped[object] = mapped_column(Date, nullable=False)
    summary: Mapped[str | None] = mapped_column(String(500))
    source_payload: Mapped[dict | None] = mapped_column(JSON)
    imported_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __init__(self, **kwargs):
        kwargs.setdefault("record_type", "historical")
        kwargs.setdefault("is_readonly", True)
        super().__init__(**kwargs)


class FinanceCenterMumarenHistoryVoucherLine(Base):
    """金蝶历史凭证明细，仅承载导入证据，不关联当前账分录。"""

    __tablename__ = "finance_center_mumaren_history_voucher_lines"
    __table_args__ = (
        UniqueConstraint(
            "history_voucher_id", "source_system", "source_key",
            name="uq_mumaren_finance_history_voucher_line",
        ),
        CheckConstraint(
            "NOT (debit_amount > 0 AND credit_amount > 0)",
            name="ck_mumaren_finance_history_line_one_side",
        ),
        {"schema": MUMAREN_FINANCE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    history_voucher_id: Mapped[int] = mapped_column(
        ForeignKey(
            f"{MUMAREN_FINANCE_SCHEMA}.finance_center_mumaren_history_vouchers.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, default="kingdee")
    source_key: Mapped[str] = mapped_column(String(256), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    account_code: Mapped[str | None] = mapped_column(String(64))
    account_name: Mapped[str | None] = mapped_column(String(128))
    summary: Mapped[str | None] = mapped_column(String(500))
    debit_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    credit_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
