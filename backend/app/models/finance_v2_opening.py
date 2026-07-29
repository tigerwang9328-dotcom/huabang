"""Persistent opening-balance boundary records for Finance V2.0 cutover."""

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class FinanceV2OpeningBalanceBatch(Base):
    __tablename__ = "opening_balance_batch"
    __table_args__ = (
        Index("uq_fin_current_active_opening_batch_scope", "book_id", "batch_kind", "go_live_date", unique=True, postgresql_where=text("status <> 'discarded'")),
        CheckConstraint("batch_kind IN ('provisional','final')", name="ck_fin_current_opening_batch_kind"),
        CheckConstraint("status IN ('draft','validated','locked','discarded')", name="ck_fin_current_opening_batch_status"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"), nullable=False)
    batch_kind = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, server_default="draft")
    history_coverage_end_date = Column(Date, nullable=False)
    go_live_date = Column(Date, nullable=False)
    coverage_continuous = Column(Boolean, nullable=False, server_default="false")
    coverage_gap_id = Column(BigInteger, ForeignKey("fin_current.coverage_gap.id"))
    approved_by = Column(String(128))
    approved_at = Column(DateTime(timezone=True))
    locked_at = Column(DateTime(timezone=True))
    version = Column(Integer, nullable=False, server_default="1")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class FinanceV2OpeningBalanceLine(Base):
    __tablename__ = "opening_balance_line"
    __table_args__ = (
        UniqueConstraint("batch_id", "account_version_id", "dimension_set_id", "currency_code", name="uq_fin_current_opening_line_key"),
        CheckConstraint("debit_amount >= 0 AND credit_amount >= 0", name="ck_fin_current_opening_line_nonnegative"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_id = Column(BigInteger, ForeignKey("fin_current.opening_balance_batch.id"), nullable=False)
    account_version_id = Column(BigInteger, ForeignKey("fin_current.account_version.id"), nullable=False)
    dimension_set_id = Column(BigInteger, ForeignKey("fin_current.dimension_set.id"), nullable=False)
    currency_code = Column(String(16), nullable=False, server_default="CNY")
    debit_amount = Column(Numeric(20, 2), nullable=False, server_default="0")
    credit_amount = Column(Numeric(20, 2), nullable=False, server_default="0")
    source_system = Column(String(32), nullable=False)
    source_reference = Column(String(256))


class FinanceV2CoverageGap(Base):
    __tablename__ = "coverage_gap"
    __table_args__ = (
        CheckConstraint("gap_end_date >= gap_start_date", name="ck_fin_current_coverage_gap_dates"),
        CheckConstraint("status IN ('draft','approved','discarded')", name="ck_fin_current_coverage_gap_status"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"), nullable=False)
    gap_start_date = Column(Date, nullable=False)
    gap_end_date = Column(Date, nullable=False)
    reason = Column(Text, nullable=False)
    affected_reports = Column(JSONB, nullable=False, server_default="[]")
    status = Column(String(16), nullable=False, server_default="draft")
    approved_by = Column(String(128))
    approved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinanceV2OpeningBalanceApproval(Base):
    __tablename__ = "opening_balance_approval"
    __table_args__ = (
        UniqueConstraint("batch_id", "approval_step", name="uq_fin_current_opening_approval_step"),
        UniqueConstraint("command_id", name="uq_fin_current_opening_approval_command"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_id = Column(BigInteger, ForeignKey("fin_current.opening_balance_batch.id"), nullable=False)
    approval_step = Column(Integer, nullable=False, server_default="1")
    actor_id = Column(String(128), nullable=False)
    command_id = Column(String(128), nullable=False)
    reason = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinanceV2OpeningBalanceReconciliationItem(Base):
    __tablename__ = "opening_balance_reconciliation_item"
    __table_args__ = (
        UniqueConstraint("batch_id", "account_version_id", "dimension_set_id", "currency_code", name="uq_fin_current_opening_reconciliation_key"),
        CheckConstraint("status IN ('matched','exception','pending')", name="ck_fin_current_opening_reconciliation_status"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_id = Column(BigInteger, ForeignKey("fin_current.opening_balance_batch.id"), nullable=False)
    account_version_id = Column(BigInteger, ForeignKey("fin_current.account_version.id"), nullable=False)
    dimension_set_id = Column(BigInteger, ForeignKey("fin_current.dimension_set.id"), nullable=False)
    currency_code = Column(String(16), nullable=False, server_default="CNY")
    source_debit_amount = Column(Numeric(20, 2), nullable=False, server_default="0")
    source_credit_amount = Column(Numeric(20, 2), nullable=False, server_default="0")
    opening_debit_amount = Column(Numeric(20, 2), nullable=False, server_default="0")
    opening_credit_amount = Column(Numeric(20, 2), nullable=False, server_default="0")
    status = Column(String(16), nullable=False, server_default="pending")
    exception_reason = Column(Text)
