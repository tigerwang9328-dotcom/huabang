"""Immutable source receipts and versioned dry-run rules for Finance V2.0."""

from sqlalchemy import BigInteger, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class FinanceV2SourceDocument(Base):
    __tablename__ = "source_document"
    __table_args__ = (
        UniqueConstraint("source_system", "source_pk", name="uq_fin_current_source_document_identity"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_system = Column(String(64), nullable=False)
    source_pk = Column(String(256), nullable=False)
    business_type = Column(String(64), nullable=False)
    legal_entity_code = Column(String(64))
    organization_code = Column(String(64))
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinanceV2SourceDocumentVersion(Base):
    __tablename__ = "source_document_version"
    __table_args__ = (
        UniqueConstraint("source_document_id", "version_no", name="uq_fin_current_source_document_version_no"),
        UniqueConstraint("source_document_id", "source_hash", name="uq_fin_current_source_document_version_hash"),
        CheckConstraint("version_no >= 1", name="ck_fin_current_source_document_version_no"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_document_id = Column(BigInteger, ForeignKey("fin_current.source_document.id"), nullable=False)
    version_no = Column(Integer, nullable=False)
    source_hash = Column(String(64), nullable=False)
    source_occurred_at = Column(DateTime(timezone=True))
    payload = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinanceV2SourceInbox(Base):
    __tablename__ = "source_inbox"
    __table_args__ = (
        UniqueConstraint("source_document_version_id", name="uq_fin_current_source_inbox_version"),
        UniqueConstraint("idempotency_key", name="uq_fin_current_source_inbox_idempotency"),
        CheckConstraint("status IN ('received','preview_ready','pending_mapping','exception','ignored')", name="ck_fin_current_source_inbox_status"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_document_version_id = Column(BigInteger, ForeignKey("fin_current.source_document_version.id"), nullable=False)
    status = Column(String(32), nullable=False, server_default="received")
    idempotency_key = Column(String(128), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_previewed_at = Column(DateTime(timezone=True))


class FinanceV2PostingRule(Base):
    __tablename__ = "posting_rule"
    __table_args__ = (
        UniqueConstraint("source_system", "rule_code", name="uq_fin_current_posting_rule_identity"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_system = Column(String(64), nullable=False)
    rule_code = Column(String(64), nullable=False)
    business_type = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinanceV2PostingRuleVersion(Base):
    __tablename__ = "posting_rule_version"
    __table_args__ = (
        UniqueConstraint("posting_rule_id", "version_code", name="uq_fin_current_posting_rule_version_code"),
        CheckConstraint("status IN ('draft','published','retired')", name="ck_fin_current_posting_rule_version_status"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_fin_current_posting_rule_version_dates"),
        CheckConstraint("status <> 'published' OR (published_by IS NOT NULL AND published_at IS NOT NULL)", name="ck_fin_current_posting_rule_version_publication"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    posting_rule_id = Column(BigInteger, ForeignKey("fin_current.posting_rule.id"), nullable=False)
    version_code = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, server_default="draft")
    legal_entity_code = Column(String(64))
    organization_code = Column(String(64))
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"))
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    priority = Column(Integer, nullable=False, server_default="0")
    debit_account_version_id = Column(BigInteger, ForeignKey("fin_current.account_version.id"), nullable=False)
    credit_account_version_id = Column(BigInteger, ForeignKey("fin_current.account_version.id"), nullable=False)
    dimension_mapping = Column(JSONB, nullable=False, server_default="{}")
    tax_mapping = Column(JSONB, nullable=False, server_default="{}")
    published_by = Column(String(128))
    published_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinanceV2MappingException(Base):
    __tablename__ = "mapping_exception"
    __table_args__ = (
        UniqueConstraint("source_inbox_id", "exception_code", name="uq_fin_current_mapping_exception_inbox_code"),
        CheckConstraint("status IN ('open','resolved','ignored')", name="ck_fin_current_mapping_exception_status"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_inbox_id = Column(BigInteger, ForeignKey("fin_current.source_inbox.id"), nullable=False)
    exception_code = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, server_default="open")
    detail = Column(JSONB, nullable=False, server_default="{}")
    resolved_by = Column(String(128))
    resolved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinanceV2PreviewRun(Base):
    __tablename__ = "preview_run"
    __table_args__ = (
        Index("uq_fin_current_preview_run_input", "source_inbox_id", text("COALESCE(posting_rule_version_id, 0)"), "input_hash", unique=True),
        CheckConstraint("status IN ('preview_ready','pending_mapping','exception')", name="ck_fin_current_preview_run_status"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_inbox_id = Column(BigInteger, ForeignKey("fin_current.source_inbox.id"), nullable=False)
    posting_rule_version_id = Column(BigInteger, ForeignKey("fin_current.posting_rule_version.id"))
    status = Column(String(32), nullable=False)
    input_hash = Column(String(64), nullable=False)
    result_payload = Column(JSONB, nullable=False, server_default="{}")
    exception_code = Column(String(64))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
