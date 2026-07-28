"""Isolated persistent model for the Finance V2.0 accounting core.

Legacy ``fin`` tables remain untouched during the read-only validation phase.
All new current-account facts live in ``fin_current``; history is introduced in
``fin_history`` by the controlled import phase.
"""

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


AMOUNT = Numeric(20, 2)


class _TimestampMixin:
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class FinanceV2AccountingBook(_TimestampMixin, Base):
    __tablename__ = "accounting_book"
    __table_args__ = (
        UniqueConstraint("book_code", name="uq_fin_current_book_code"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_code = Column(String(64), nullable=False)
    book_name = Column(String(256), nullable=False)
    legal_entity_name = Column(String(256), nullable=False)
    base_currency = Column(String(16), nullable=False, server_default="CNY")
    history_coverage_end_date = Column(Date)
    current_book_go_live_date = Column(Date)
    formal_report_blocked = Column(Boolean, nullable=False, server_default="true")
    status = Column(String(24), nullable=False, server_default="preparing")


class FinanceV2FiscalPeriod(_TimestampMixin, Base):
    __tablename__ = "fiscal_period"
    __table_args__ = (
        UniqueConstraint("book_id", "period_code", name="uq_fin_current_period_book_code"),
        CheckConstraint("status IN ('open','closing','closed','reopening')", name="ck_fin_current_period_status"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"), nullable=False)
    period_code = Column(String(7), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(16), nullable=False, server_default="open")
    version = Column(Integer, nullable=False, server_default="1")


class FinanceV2AccountVersion(_TimestampMixin, Base):
    __tablename__ = "account_version"
    __table_args__ = (
        UniqueConstraint("book_id", "version_code", "account_code", name="uq_fin_current_account_version_code"),
        CheckConstraint("normal_balance IN ('debit','credit')", name="ck_fin_current_account_normal_balance"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"), nullable=False)
    version_code = Column(String(64), nullable=False)
    account_code = Column(String(64), nullable=False)
    account_name = Column(String(256), nullable=False)
    parent_account_version_id = Column(BigInteger, ForeignKey("fin_current.account_version.id"))
    normal_balance = Column(String(8), nullable=False)
    is_postable = Column(Boolean, nullable=False, server_default="true")
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)


class FinanceV2DimensionSet(_TimestampMixin, Base):
    __tablename__ = "dimension_set"
    __table_args__ = (
        UniqueConstraint("book_id", "stable_hash", name="uq_fin_current_dimension_set_hash"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"), nullable=False)
    stable_hash = Column(String(64), nullable=False)


class FinanceV2DimensionSetItem(Base):
    __tablename__ = "dimension_set_item"
    __table_args__ = (
        UniqueConstraint("dimension_set_id", "dimension_code", name="uq_fin_current_dimension_set_item"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dimension_set_id = Column(BigInteger, ForeignKey("fin_current.dimension_set.id"), nullable=False)
    dimension_code = Column(String(64), nullable=False)
    dimension_value_code = Column(String(128), nullable=False)


class FinanceV2Voucher(_TimestampMixin, Base):
    __tablename__ = "voucher"
    __table_args__ = (
        UniqueConstraint("book_id", "request_id", name="uq_fin_current_voucher_request"),
        CheckConstraint(
            "status IN ('draft','submitted','reviewing','approved','rejected','cancelled','posted')",
            name="ck_fin_current_voucher_status",
        ),
        CheckConstraint("total_debit >= 0 AND total_credit >= 0", name="ck_fin_current_voucher_nonnegative"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"), nullable=False)
    period_id = Column(BigInteger, ForeignKey("fin_current.fiscal_period.id"), nullable=False)
    voucher_group = Column(String(16), nullable=False, server_default="记")
    voucher_no = Column(String(64))
    voucher_date = Column(Date, nullable=False)
    status = Column(String(16), nullable=False, server_default="draft")
    version = Column(Integer, nullable=False, server_default="1")
    request_id = Column(String(128), nullable=False)
    idempotency_key = Column(String(128))
    prepared_by = Column(String(128), nullable=False)
    reviewer_id = Column(String(128))
    approved_by = Column(String(128))
    posted_by = Column(String(128))
    total_debit = Column(AMOUNT, nullable=False, server_default="0")
    total_credit = Column(AMOUNT, nullable=False, server_default="0")
    reversal_voucher_id = Column(BigInteger, ForeignKey("fin_current.voucher.id"))
    source_system = Column(String(32), nullable=False, server_default="manual")


class FinanceV2VoucherLine(Base):
    __tablename__ = "voucher_line"
    __table_args__ = (
        UniqueConstraint("voucher_id", "line_no", name="uq_fin_current_voucher_line_no"),
        CheckConstraint("debit_amount >= 0 AND credit_amount >= 0", name="ck_fin_current_voucher_line_nonnegative"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    voucher_id = Column(BigInteger, ForeignKey("fin_current.voucher.id"), nullable=False)
    line_no = Column(Integer, nullable=False)
    account_version_id = Column(BigInteger, ForeignKey("fin_current.account_version.id"), nullable=False)
    dimension_set_id = Column(BigInteger, ForeignKey("fin_current.dimension_set.id"))
    summary = Column(String(512), nullable=False)
    currency_code = Column(String(16), nullable=False, server_default="CNY")
    exchange_rate = Column(Numeric(20, 10), nullable=False, server_default="1")
    debit_amount = Column(AMOUNT, nullable=False, server_default="0")
    credit_amount = Column(AMOUNT, nullable=False, server_default="0")


class FinanceV2LedgerBalance(_TimestampMixin, Base):
    __tablename__ = "ledger_balance"
    __table_args__ = (
        UniqueConstraint(
            "book_id", "period_id", "account_version_id", "dimension_set_id", "currency_code",
            name="uq_fin_current_ledger_balance_key",
        ),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"), nullable=False)
    period_id = Column(BigInteger, ForeignKey("fin_current.fiscal_period.id"), nullable=False)
    account_version_id = Column(BigInteger, ForeignKey("fin_current.account_version.id"), nullable=False)
    dimension_set_id = Column(BigInteger, ForeignKey("fin_current.dimension_set.id"), nullable=False)
    currency_code = Column(String(16), nullable=False, server_default="CNY")
    opening_debit = Column(AMOUNT, nullable=False, server_default="0")
    opening_credit = Column(AMOUNT, nullable=False, server_default="0")
    period_debit = Column(AMOUNT, nullable=False, server_default="0")
    period_credit = Column(AMOUNT, nullable=False, server_default="0")
    closing_debit = Column(AMOUNT, nullable=False, server_default="0")
    closing_credit = Column(AMOUNT, nullable=False, server_default="0")


class FinanceV2CommandIdempotency(_TimestampMixin, Base):
    __tablename__ = "command_idempotency"
    __table_args__ = (
        UniqueConstraint("book_id", "command_name", "idempotency_key", name="uq_fin_current_command_scope_key"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"), nullable=False)
    command_name = Column(String(64), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    request_hash = Column(String(64), nullable=False)
    result_payload = Column(JSONB, nullable=False, server_default="{}")
    completed_at = Column(DateTime(timezone=True))


class FinanceV2OperationEvent(Base):
    __tablename__ = "operation_event"
    __table_args__ = ({"schema": "fin_current"},)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"), nullable=False)
    voucher_id = Column(BigInteger, ForeignKey("fin_current.voucher.id"))
    command_id = Column(String(128), nullable=False)
    actor_id = Column(String(128), nullable=False)
    action = Column(String(64), nullable=False)
    reason = Column(Text)
    before_data = Column(JSONB)
    after_data = Column(JSONB)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
