"""Operational controls and independent posting-attempt evidence for Finance V2.0."""

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class FinanceV2FeatureGate(Base):
    __tablename__ = "feature_gate"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_key", "gate_name", name="uq_fin_current_feature_gate_scope"),
        CheckConstraint("scope_type IN ('global','environment','book','source','role')", name="ck_fin_current_gate_scope"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scope_type = Column(String(16), nullable=False)
    scope_key = Column(String(128), nullable=False)
    gate_name = Column(String(64), nullable=False)
    enabled = Column(Boolean, nullable=False, server_default="false")
    changed_by = Column(String(128), nullable=False)
    reason = Column(Text, nullable=False)
    approved_by = Column(String(128))
    effective_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinanceV2PostingAttempt(Base):
    __tablename__ = "posting_attempt"
    __table_args__ = (
        CheckConstraint("status IN ('running','success','failed')", name="ck_fin_current_posting_attempt_status"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    voucher_id = Column(BigInteger, ForeignKey("fin_current.voucher.id"), nullable=False)
    command_id = Column(String(128), nullable=False, unique=True)
    status = Column(String(16), nullable=False, server_default="running")
    error_code = Column(String(64))
    error_context = Column(JSONB)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True))


class FinanceV2VoucherNumberCounter(Base):
    """One locked counter per book, period and voucher group."""

    __tablename__ = "voucher_number_counter"
    __table_args__ = (
        UniqueConstraint("book_id", "period_id", "voucher_group", name="uq_fin_current_voucher_number_counter_scope"),
        CheckConstraint("next_number >= 1", name="ck_fin_current_voucher_number_counter_next_number"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"), nullable=False)
    period_id = Column(BigInteger, ForeignKey("fin_current.fiscal_period.id"), nullable=False)
    voucher_group = Column(String(16), nullable=False, server_default="记")
    next_number = Column(Integer, nullable=False, server_default="1")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class FinanceV2VoucherNumberReservation(Base):
    """Append-only evidence for reserved, used and voided voucher numbers."""

    __tablename__ = "voucher_number_reservation"
    __table_args__ = (
        UniqueConstraint(
            "book_id", "period_id", "voucher_group", "voucher_no", name="uq_fin_current_voucher_number_reservation_scope"
        ),
        UniqueConstraint("command_id", name="uq_fin_current_voucher_number_reservation_command"),
        CheckConstraint("status IN ('reserved','used','voided')", name="ck_fin_current_voucher_number_reservation_status"),
        CheckConstraint(
            "status <> 'voided' OR void_reason IS NOT NULL",
            name="ck_fin_current_voucher_number_reservation_void_reason",
        ),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"), nullable=False)
    period_id = Column(BigInteger, ForeignKey("fin_current.fiscal_period.id"), nullable=False)
    voucher_group = Column(String(16), nullable=False, server_default="记")
    voucher_no = Column(String(64), nullable=False)
    command_id = Column(String(128), nullable=False)
    status = Column(String(16), nullable=False, server_default="reserved")
    void_reason = Column(Text)
    voucher_id = Column(BigInteger, ForeignKey("fin_current.voucher.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finalized_at = Column(DateTime(timezone=True))
