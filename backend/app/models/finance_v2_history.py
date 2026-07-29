"""Immutable, published-only historical accounting facts for Finance V2.0."""

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class FinanceV2HistoryBatch(Base):
    __tablename__ = "import_batch"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created','loading','loaded','validating','validated','published','failed','conflicted','cancelled','superseded')",
            name="ck_fin_history_batch_status",
        ),
        {"schema": "fin_history"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_code = Column(String(64), nullable=False, unique=True)
    source_system = Column(String(32), nullable=False, server_default="kingdee")
    source_database = Column(String(128), nullable=False)
    status = Column(String(16), nullable=False, server_default="created")
    expected_counts = Column(JSONB, nullable=False, server_default="{}")
    actual_counts = Column(JSONB, nullable=False, server_default="{}")
    validation_report = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    published_at = Column(DateTime(timezone=True))


class FinanceV2HistoryStagingVoucher(Base):
    __tablename__ = "staging_voucher"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_system", "source_database", "source_pk", name="uq_fin_history_staging_source"),
        {"schema": "fin_history"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_id = Column(BigInteger, ForeignKey("fin_history.import_batch.id"), nullable=False)
    source_system = Column(String(32), nullable=False)
    source_database = Column(String(128), nullable=False)
    source_pk = Column(String(256), nullable=False)
    source_hash = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=False)
    status = Column(String(16), nullable=False, server_default="loaded")


class FinanceV2HistoryVoucher(Base):
    __tablename__ = "voucher"
    __table_args__ = (
        UniqueConstraint("source_system", "source_database", "source_pk", name="uq_fin_history_voucher_source"),
        {"schema": "fin_history"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_id = Column(BigInteger, ForeignKey("fin_history.import_batch.id"), nullable=False)
    source_system = Column(String(32), nullable=False)
    source_database = Column(String(128), nullable=False)
    source_pk = Column(String(256), nullable=False)
    source_hash = Column(String(64), nullable=False)
    voucher_no = Column(String(64))
    voucher_group = Column(String(32))
    voucher_date = Column(Date, nullable=False)
    fiscal_year = Column(Integer, nullable=False)
    fiscal_period = Column(Integer, nullable=False)
    source_status = Column(String(32))
    total_debit = Column(Numeric(20, 2), nullable=False, server_default="0")
    total_credit = Column(Numeric(20, 2), nullable=False, server_default="0")
    is_historical = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinanceV2HistoryVoucherLine(Base):
    __tablename__ = "voucher_line"
    __table_args__ = (
        UniqueConstraint("voucher_id", "line_no", name="uq_fin_history_voucher_line_no"),
        {"schema": "fin_history"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    voucher_id = Column(BigInteger, ForeignKey("fin_history.voucher.id"), nullable=False)
    line_no = Column(Integer, nullable=False)
    source_pk = Column(String(256), nullable=False)
    account_code = Column(String(64))
    summary = Column(String(512))
    currency_code = Column(String(16), nullable=False, server_default="CNY")
    exchange_rate = Column(Numeric(20, 10), nullable=False, server_default="1")
    debit_amount = Column(Numeric(20, 2), nullable=False, server_default="0")
    credit_amount = Column(Numeric(20, 2), nullable=False, server_default="0")
    raw_dimensions = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinanceV2HistorySourceLink(Base):
    __tablename__ = "source_link"
    __table_args__ = (
        UniqueConstraint("source_system", "source_database", "source_pk", name="uq_fin_history_source_link"),
        {"schema": "fin_history"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_id = Column(BigInteger, ForeignKey("fin_history.import_batch.id"), nullable=False)
    history_voucher_id = Column(BigInteger, ForeignKey("fin_history.voucher.id"), nullable=False)
    source_system = Column(String(32), nullable=False)
    source_database = Column(String(128), nullable=False)
    source_pk = Column(String(256), nullable=False)
    source_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
