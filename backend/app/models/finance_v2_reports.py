"""Versioned report metadata for Finance V2.0.

These records describe a report; they never replace the current voucher and
ledger facts that remain the accounting source of truth.
"""

from sqlalchemy import BigInteger, CheckConstraint, Column, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class FinanceV2ReportTemplate(Base):
    __tablename__ = "report_template"
    __table_args__ = (
        UniqueConstraint("book_id", "report_code", "version_code", name="uq_fin_current_report_template_version"),
        CheckConstraint("report_code IN ('balance_sheet','profit_statement')", name="ck_fin_current_report_template_code"),
        CheckConstraint("status IN ('draft','published','retired')", name="ck_fin_current_report_template_status"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_fin_current_report_template_effective_range"),
        CheckConstraint("jsonb_typeof(line_definition->'line_codes') = 'array' AND jsonb_array_length(line_definition->'line_codes') > 0", name="ck_fin_current_report_template_lines"),
        CheckConstraint("status <> 'published' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)", name="ck_fin_current_report_template_publication_approval"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"), nullable=False)
    report_code = Column(String(32), nullable=False)
    version_code = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, server_default="draft")
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    line_definition = Column(JSONB, nullable=False)
    approved_by = Column(String(128))
    approved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinanceV2ReportMapping(Base):
    __tablename__ = "report_mapping"
    __table_args__ = (
        UniqueConstraint("template_id", "line_code", "account_version_id", name="uq_fin_current_report_mapping_line_account"),
        CheckConstraint("multiplier <> 0", name="ck_fin_current_report_mapping_multiplier"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    template_id = Column(BigInteger, ForeignKey("fin_current.report_template.id"), nullable=False)
    line_code = Column(String(64), nullable=False)
    account_version_id = Column(BigInteger, ForeignKey("fin_current.account_version.id"), nullable=False)
    multiplier = Column(Numeric(20, 10), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinanceV2ReportSnapshot(Base):
    __tablename__ = "report_snapshot"
    __table_args__ = (
        UniqueConstraint("book_id", "period_id", "template_id", name="uq_fin_current_report_snapshot_scope"),
        CheckConstraint("status IN ('ready','blocked','pending_mapping','pending_data','pending_gap')", name="ck_fin_current_report_snapshot_status"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"), nullable=False)
    period_id = Column(BigInteger, ForeignKey("fin_current.fiscal_period.id"), nullable=False)
    template_id = Column(BigInteger, ForeignKey("fin_current.report_template.id"), nullable=False)
    status = Column(String(32), nullable=False)
    output_hash = Column(String(64), nullable=False)
    output_data = Column(JSONB, nullable=False, server_default="{}")
    generated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
