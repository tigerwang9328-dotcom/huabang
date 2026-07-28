"""Persistent opening-balance boundary records for Finance V2.0 cutover."""

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class FinanceV2OpeningBalanceBatch(Base):
    __tablename__ = "opening_balance_batch"
    __table_args__ = (
        UniqueConstraint("book_id", "batch_kind", "go_live_date", name="uq_fin_current_opening_batch_scope"),
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
    approved_by = Column(String(128))
    approved_at = Column(DateTime(timezone=True))
    locked_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


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
