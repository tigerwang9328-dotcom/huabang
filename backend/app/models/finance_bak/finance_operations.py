"""Operational finance models that produce auditable voucher drafts."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.finance_core import AMOUNT, _LineageMixin, _TimestampMixin


class _BookScopedMixin:
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin.book.id"), nullable=False)


class _DraftVoucherMixin(_BookScopedMixin):
    draft_voucher_id = Column(BigInteger)


class FinReceivable(_DraftVoucherMixin, _LineageMixin, _TimestampMixin, Base):
    __tablename__ = "receivable"
    __table_args__ = (
        UniqueConstraint("book_id", "id", name="uq_fin_receivable_book_id"),
        Index(
            "uq_fin_receivable_source",
            "book_id",
            "source_system",
            "source_database",
            "source_pk",
            unique=True,
            postgresql_where=text("source_pk IS NOT NULL"),
        ),
        ForeignKeyConstraint(["book_id", "draft_voucher_id"], ["fin.voucher.book_id", "fin.voucher.id"], name="fk_fin_receivable_book_voucher"),
        ForeignKeyConstraint(["book_id", "counterparty_aux_id"], ["fin.aux_item.book_id", "fin.aux_item.id"], name="fk_fin_receivable_book_counterparty"),
        CheckConstraint("original_amount >= 0 AND settled_amount >= 0 AND settled_amount <= original_amount AND outstanding_amount = original_amount - settled_amount", name="ck_fin_receivable_amounts"),
        Index("ix_fin_receivable_book_status_due", "book_id", "status", "due_date"),
        Index("ix_fin_receivable_book_voucher", "book_id", "draft_voucher_id"),
        Index("ix_fin_receivable_book_counterparty", "book_id", "counterparty_aux_id"),
        {"schema": "fin"},
    )

    document_no = Column(String(128), nullable=False)
    counterparty_aux_id = Column(BigInteger, nullable=False)
    business_date = Column(Date, nullable=False)
    due_date = Column(Date)
    currency_code = Column(String(16), nullable=False, server_default="CNY")
    original_amount = Column(AMOUNT, nullable=False)
    settled_amount = Column(AMOUNT, nullable=False, server_default="0")
    outstanding_amount = Column(AMOUNT, nullable=False)
    status = Column(String(16), nullable=False, server_default="open")
    version = Column(Integer, nullable=False, server_default="1")


class FinPayable(_DraftVoucherMixin, _LineageMixin, _TimestampMixin, Base):
    __tablename__ = "payable"
    __table_args__ = (
        UniqueConstraint("book_id", "id", name="uq_fin_payable_book_id"),
        Index("uq_fin_payable_source", "book_id", "source_system", "source_database", "source_pk", unique=True, postgresql_where=text("source_pk IS NOT NULL")),
        ForeignKeyConstraint(["book_id", "draft_voucher_id"], ["fin.voucher.book_id", "fin.voucher.id"], name="fk_fin_payable_book_voucher"),
        ForeignKeyConstraint(["book_id", "counterparty_aux_id"], ["fin.aux_item.book_id", "fin.aux_item.id"], name="fk_fin_payable_book_counterparty"),
        CheckConstraint("original_amount >= 0 AND settled_amount >= 0 AND settled_amount <= original_amount AND outstanding_amount = original_amount - settled_amount", name="ck_fin_payable_amounts"),
        Index("ix_fin_payable_book_status_due", "book_id", "status", "due_date"),
        Index("ix_fin_payable_book_voucher", "book_id", "draft_voucher_id"),
        Index("ix_fin_payable_book_counterparty", "book_id", "counterparty_aux_id"),
        {"schema": "fin"},
    )

    document_no = Column(String(128), nullable=False)
    counterparty_aux_id = Column(BigInteger, nullable=False)
    business_date = Column(Date, nullable=False)
    due_date = Column(Date)
    currency_code = Column(String(16), nullable=False, server_default="CNY")
    original_amount = Column(AMOUNT, nullable=False)
    settled_amount = Column(AMOUNT, nullable=False, server_default="0")
    outstanding_amount = Column(AMOUNT, nullable=False)
    status = Column(String(16), nullable=False, server_default="open")
    version = Column(Integer, nullable=False, server_default="1")


class FinSettlement(_DraftVoucherMixin, _TimestampMixin, Base):
    __tablename__ = "settlement"
    __table_args__ = (
        UniqueConstraint("book_id", "settlement_no", name="uq_fin_settlement_book_no"),
        UniqueConstraint("book_id", "id", name="uq_fin_settlement_book_id"),
        ForeignKeyConstraint(["book_id", "draft_voucher_id"], ["fin.voucher.book_id", "fin.voucher.id"], name="fk_fin_settlement_book_voucher"),
        ForeignKeyConstraint(["book_id", "reversal_of_id"], ["fin.settlement.book_id", "fin.settlement.id"], name="fk_fin_settlement_book_reversal"),
        ForeignKeyConstraint(["book_id", "receivable_id"], ["fin.receivable.book_id", "fin.receivable.id"], name="fk_fin_settlement_book_receivable"),
        ForeignKeyConstraint(["book_id", "payable_id"], ["fin.payable.book_id", "fin.payable.id"], name="fk_fin_settlement_book_payable"),
        CheckConstraint("amount > 0", name="ck_fin_settlement_amount"),
        CheckConstraint("(receivable_id IS NOT NULL)::integer + (payable_id IS NOT NULL)::integer = 1", name="ck_fin_settlement_one_target"),
        Index("ix_fin_settlement_book_voucher", "book_id", "draft_voucher_id"),
        Index("ix_fin_settlement_book_reversal", "book_id", "reversal_of_id"),
        Index("ix_fin_settlement_book_receivable", "book_id", "receivable_id"),
        Index("ix_fin_settlement_book_payable", "book_id", "payable_id"),
        {"schema": "fin"},
    )

    settlement_no = Column(String(128), nullable=False)
    settlement_type = Column(String(16), nullable=False)
    receivable_id = Column(BigInteger)
    payable_id = Column(BigInteger)
    settlement_date = Column(Date, nullable=False)
    amount = Column(AMOUNT, nullable=False)
    status = Column(String(16), nullable=False, server_default="active")
    reversal_of_id = Column(BigInteger)
    actor_id = Column(BigInteger, ForeignKey("sys.sys_user.id"))
    reason = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, server_default="1")


class FinCashAccount(_BookScopedMixin, _TimestampMixin, Base):
    __tablename__ = "cash_account"
    __table_args__ = (
        UniqueConstraint("book_id", "account_code", name="uq_fin_cash_account_book_code"),
        UniqueConstraint("book_id", "id", name="uq_fin_cash_account_book_id"),
        ForeignKeyConstraint(["book_id", "ledger_account_id"], ["fin.account.book_id", "fin.account.id"], name="fk_fin_cash_account_book_account"),
        Index("ix_fin_cash_account_book_account", "book_id", "ledger_account_id"),
        {"schema": "fin"},
    )

    account_code = Column(String(64), nullable=False)
    account_name = Column(String(128), nullable=False)
    account_type = Column(String(16), nullable=False)
    ledger_account_id = Column(BigInteger, nullable=False)
    bank_name = Column(String(128))
    bank_account_masked = Column(String(64))
    currency_code = Column(String(16), nullable=False, server_default="CNY")
    status = Column(String(16), nullable=False, server_default="active")
    version = Column(Integer, nullable=False, server_default="1")


class FinBankTransaction(_DraftVoucherMixin, _LineageMixin, _TimestampMixin, Base):
    __tablename__ = "bank_transaction"
    __table_args__ = (
        Index("uq_fin_bank_transaction_source", "book_id", "source_system", "source_database", "source_pk", unique=True, postgresql_where=text("source_pk IS NOT NULL")),
        UniqueConstraint("cash_account_id", "statement_hash", name="uq_fin_bank_transaction_hash"),
        ForeignKeyConstraint(["book_id", "draft_voucher_id"], ["fin.voucher.book_id", "fin.voucher.id"], name="fk_fin_bank_transaction_book_voucher"),
        ForeignKeyConstraint(["book_id", "cash_account_id"], ["fin.cash_account.book_id", "fin.cash_account.id"], name="fk_fin_bank_transaction_book_cash"),
        CheckConstraint("amount > 0 AND direction IN ('in','out')", name="ck_fin_bank_transaction_amount_direction"),
        Index("ix_fin_bank_transaction_book_voucher", "book_id", "draft_voucher_id"),
        Index("ix_fin_bank_transaction_book_cash", "book_id", "cash_account_id"),
        {"schema": "fin"},
    )

    cash_account_id = Column(BigInteger, nullable=False)
    transaction_date = Column(Date, nullable=False)
    amount = Column(AMOUNT, nullable=False)
    direction = Column(String(8), nullable=False)
    counterparty_name = Column(String(256))
    reference_no = Column(String(128))
    summary = Column(String(512))
    statement_hash = Column(String(64), nullable=False)
    status = Column(String(24), nullable=False, server_default="unreconciled")
    version = Column(Integer, nullable=False, server_default="1")


class FinReconciliation(_DraftVoucherMixin, _TimestampMixin, Base):
    __tablename__ = "reconciliation"
    __table_args__ = (
        UniqueConstraint("book_id", "reconciliation_no", name="uq_fin_reconciliation_book_no"),
        ForeignKeyConstraint(["book_id", "draft_voucher_id"], ["fin.voucher.book_id", "fin.voucher.id"], name="fk_fin_reconciliation_book_voucher"),
        ForeignKeyConstraint(["book_id", "cash_account_id"], ["fin.cash_account.book_id", "fin.cash_account.id"], name="fk_fin_reconciliation_book_cash"),
        CheckConstraint("difference = statement_balance - ledger_balance", name="ck_fin_reconciliation_difference"),
        Index("ix_fin_reconciliation_book_voucher", "book_id", "draft_voucher_id"),
        Index("ix_fin_reconciliation_book_cash", "book_id", "cash_account_id"),
        {"schema": "fin"},
    )

    reconciliation_no = Column(String(128), nullable=False)
    cash_account_id = Column(BigInteger, nullable=False)
    period = Column(String(7), nullable=False)
    statement_balance = Column(AMOUNT, nullable=False)
    ledger_balance = Column(AMOUNT, nullable=False)
    difference = Column(AMOUNT, nullable=False)
    matched_transaction_ids = Column(JSONB, nullable=False, server_default="[]")
    status = Column(String(16), nullable=False, server_default="draft")
    reviewed_by = Column(BigInteger, ForeignKey("sys.sys_user.id"))
    reviewed_at = Column(DateTime(timezone=True))
    version = Column(Integer, nullable=False, server_default="1")


class FinFixedAsset(_DraftVoucherMixin, _TimestampMixin, Base):
    __tablename__ = "fixed_asset"
    __table_args__ = (
        UniqueConstraint("book_id", "asset_code", name="uq_fin_fixed_asset_book_code"),
        UniqueConstraint("book_id", "id", name="uq_fin_fixed_asset_book_id"),
        ForeignKeyConstraint(["book_id", "draft_voucher_id"], ["fin.voucher.book_id", "fin.voucher.id"], name="fk_fin_fixed_asset_book_voucher"),
        ForeignKeyConstraint(["book_id", "department_aux_id"], ["fin.aux_item.book_id", "fin.aux_item.id"], name="fk_fin_fixed_asset_book_department"),
        ForeignKeyConstraint(["book_id", "expense_account_id"], ["fin.account.book_id", "fin.account.id"], name="fk_fin_fixed_asset_book_expense"),
        ForeignKeyConstraint(["book_id", "accumulated_account_id"], ["fin.account.book_id", "fin.account.id"], name="fk_fin_fixed_asset_book_accumulated"),
        CheckConstraint("original_cost > 0 AND useful_life_months > 0 AND residual_rate >= 0 AND residual_rate < 1 AND accumulated_depreciation >= 0 AND accumulated_depreciation <= original_cost", name="ck_fin_fixed_asset_amounts"),
        Index("ix_fin_fixed_asset_book_voucher", "book_id", "draft_voucher_id"),
        Index("ix_fin_fixed_asset_book_department", "book_id", "department_aux_id"),
        Index("ix_fin_fixed_asset_book_expense", "book_id", "expense_account_id"),
        Index("ix_fin_fixed_asset_book_accumulated", "book_id", "accumulated_account_id"),
        {"schema": "fin"},
    )

    asset_code = Column(String(64), nullable=False)
    asset_name = Column(String(256), nullable=False)
    category = Column(String(64), nullable=False)
    acquisition_date = Column(Date, nullable=False)
    in_service_date = Column(Date, nullable=False)
    original_cost = Column(AMOUNT, nullable=False)
    residual_rate = Column(Numeric(8, 6), nullable=False, server_default="0")
    useful_life_months = Column(Integer, nullable=False)
    accumulated_depreciation = Column(AMOUNT, nullable=False, server_default="0")
    status = Column(String(16), nullable=False, server_default="active")
    department_aux_id = Column(BigInteger)
    expense_account_id = Column(BigInteger, nullable=False)
    accumulated_account_id = Column(BigInteger, nullable=False)
    version = Column(Integer, nullable=False, server_default="1")


class FinDepreciation(_DraftVoucherMixin, _TimestampMixin, Base):
    __tablename__ = "depreciation"
    __table_args__ = (
        UniqueConstraint("fixed_asset_id", "period", name="uq_fin_depreciation_asset_period"),
        ForeignKeyConstraint(["book_id", "draft_voucher_id"], ["fin.voucher.book_id", "fin.voucher.id"], name="fk_fin_depreciation_book_voucher"),
        ForeignKeyConstraint(["book_id", "fixed_asset_id"], ["fin.fixed_asset.book_id", "fin.fixed_asset.id"], name="fk_fin_depreciation_book_asset"),
        CheckConstraint("amount >= 0 AND accumulated_amount >= amount", name="ck_fin_depreciation_amounts"),
        Index("ix_fin_depreciation_book_voucher", "book_id", "draft_voucher_id"),
        Index("ix_fin_depreciation_book_asset", "book_id", "fixed_asset_id"),
        {"schema": "fin"},
    )

    fixed_asset_id = Column(BigInteger, nullable=False)
    period = Column(String(7), nullable=False)
    depreciation_date = Column(Date, nullable=False)
    amount = Column(AMOUNT, nullable=False)
    accumulated_amount = Column(AMOUNT, nullable=False)
    status = Column(String(16), nullable=False, server_default="scheduled")
    version = Column(Integer, nullable=False, server_default="1")


class FinInvoice(_DraftVoucherMixin, _LineageMixin, _TimestampMixin, Base):
    __tablename__ = "invoice"
    __table_args__ = (
        UniqueConstraint("book_id", "invoice_code", "invoice_no", name="uq_fin_invoice_identity"),
        Index("uq_fin_invoice_source", "book_id", "source_system", "source_database", "source_pk", unique=True, postgresql_where=text("source_pk IS NOT NULL")),
        ForeignKeyConstraint(["book_id", "draft_voucher_id"], ["fin.voucher.book_id", "fin.voucher.id"], name="fk_fin_invoice_book_voucher"),
        ForeignKeyConstraint(["book_id", "counterparty_aux_id"], ["fin.aux_item.book_id", "fin.aux_item.id"], name="fk_fin_invoice_book_counterparty"),
        CheckConstraint("amount_excluding_tax >= 0 AND tax_amount >= 0 AND amount_excluding_tax + tax_amount = total_amount", name="ck_fin_invoice_total"),
        Index("ix_fin_invoice_book_voucher", "book_id", "draft_voucher_id"),
        Index("ix_fin_invoice_book_counterparty", "book_id", "counterparty_aux_id"),
        {"schema": "fin"},
    )

    invoice_code = Column(String(64), nullable=False, server_default="")
    invoice_no = Column(String(128), nullable=False)
    invoice_type = Column(String(32), nullable=False)
    direction = Column(String(8), nullable=False)
    invoice_date = Column(Date, nullable=False)
    counterparty_aux_id = Column(BigInteger)
    amount_excluding_tax = Column(AMOUNT, nullable=False)
    tax_amount = Column(AMOUNT, nullable=False)
    total_amount = Column(AMOUNT, nullable=False)
    currency_code = Column(String(16), nullable=False, server_default="CNY")
    status = Column(String(16), nullable=False, server_default="registered")
    version = Column(Integer, nullable=False, server_default="1")


class FinPayroll(_DraftVoucherMixin, _LineageMixin, _TimestampMixin, Base):
    __tablename__ = "payroll"
    __table_args__ = (
        UniqueConstraint("book_id", "period", "employee_aux_id", name="uq_fin_payroll_employee_period"),
        Index("uq_fin_payroll_source", "book_id", "source_system", "source_database", "source_pk", unique=True, postgresql_where=text("source_pk IS NOT NULL")),
        ForeignKeyConstraint(["book_id", "draft_voucher_id"], ["fin.voucher.book_id", "fin.voucher.id"], name="fk_fin_payroll_book_voucher"),
        ForeignKeyConstraint(["book_id", "employee_aux_id"], ["fin.aux_item.book_id", "fin.aux_item.id"], name="fk_fin_payroll_book_employee"),
        ForeignKeyConstraint(["book_id", "department_aux_id"], ["fin.aux_item.book_id", "fin.aux_item.id"], name="fk_fin_payroll_book_department"),
        CheckConstraint("gross_amount >= 0 AND social_security_amount >= 0 AND housing_fund_amount >= 0 AND tax_amount >= 0 AND other_deduction >= 0 AND net_amount = gross_amount - social_security_amount - housing_fund_amount - tax_amount - other_deduction", name="ck_fin_payroll_total"),
        Index("ix_fin_payroll_book_voucher", "book_id", "draft_voucher_id"),
        Index("ix_fin_payroll_book_employee", "book_id", "employee_aux_id"),
        Index("ix_fin_payroll_book_department", "book_id", "department_aux_id"),
        {"schema": "fin"},
    )

    period = Column(String(7), nullable=False)
    employee_aux_id = Column(BigInteger, nullable=False)
    department_aux_id = Column(BigInteger)
    gross_amount = Column(AMOUNT, nullable=False)
    social_security_amount = Column(AMOUNT, nullable=False, server_default="0")
    housing_fund_amount = Column(AMOUNT, nullable=False, server_default="0")
    tax_amount = Column(AMOUNT, nullable=False, server_default="0")
    other_deduction = Column(AMOUNT, nullable=False, server_default="0")
    net_amount = Column(AMOUNT, nullable=False)
    status = Column(String(16), nullable=False, server_default="draft")
    version = Column(Integer, nullable=False, server_default="1")


class FinTaxRecord(_DraftVoucherMixin, _LineageMixin, _TimestampMixin, Base):
    __tablename__ = "tax_record"
    __table_args__ = (
        UniqueConstraint("book_id", "tax_type", "period", name="uq_fin_tax_record_scope"),
        Index("uq_fin_tax_record_source", "book_id", "source_system", "source_database", "source_pk", unique=True, postgresql_where=text("source_pk IS NOT NULL")),
        ForeignKeyConstraint(["book_id", "draft_voucher_id"], ["fin.voucher.book_id", "fin.voucher.id"], name="fk_fin_tax_record_book_voucher"),
        CheckConstraint("taxable_amount >= 0 AND tax_amount >= 0 AND paid_amount >= 0 AND paid_amount <= tax_amount", name="ck_fin_tax_record_amounts"),
        Index("ix_fin_tax_record_book_voucher", "book_id", "draft_voucher_id"),
        {"schema": "fin"},
    )

    tax_type = Column(String(64), nullable=False)
    period = Column(String(7), nullable=False)
    taxable_amount = Column(AMOUNT, nullable=False, server_default="0")
    tax_amount = Column(AMOUNT, nullable=False)
    paid_amount = Column(AMOUNT, nullable=False, server_default="0")
    due_date = Column(Date)
    paid_date = Column(Date)
    status = Column(String(16), nullable=False, server_default="unpaid")
    version = Column(Integer, nullable=False, server_default="1")


class FinAutoEntryRule(_BookScopedMixin, _TimestampMixin, Base):
    __tablename__ = "auto_entry_rule"
    __table_args__ = (
        UniqueConstraint("book_id", "business_type", "effective_from", "priority", name="uq_fin_auto_entry_rule_scope"),
        {"schema": "fin"},
    )

    rule_name = Column(String(128), nullable=False)
    business_type = Column(String(64), nullable=False)
    source_system = Column(String(32), nullable=False)
    effective_from = Column(String(7), nullable=False)
    effective_to = Column(String(7))
    priority = Column(Integer, nullable=False, server_default="100")
    conditions = Column(JSONB, nullable=False, server_default="{}")
    entry_template = Column(JSONB, nullable=False)
    status = Column(String(16), nullable=False, server_default="active")
    version = Column(Integer, nullable=False, server_default="1")


class FinAutoEntryRun(_DraftVoucherMixin, _TimestampMixin, Base):
    __tablename__ = "auto_entry_run"
    __table_args__ = (
        UniqueConstraint("book_id", "run_key", name="uq_fin_auto_entry_run_key"),
        ForeignKeyConstraint(["book_id", "draft_voucher_id"], ["fin.voucher.book_id", "fin.voucher.id"], name="fk_fin_auto_entry_run_book_voucher"),
        Index("ix_fin_auto_entry_run_book_voucher", "book_id", "draft_voucher_id"),
        {"schema": "fin"},
    )

    run_key = Column(String(128), nullable=False)
    source_system = Column(String(32), nullable=False)
    business_type = Column(String(64), nullable=False)
    mode = Column(String(16), nullable=False, server_default="preview")
    status = Column(String(16), nullable=False, server_default="pending")
    source_count = Column(Integer, nullable=False, server_default="0")
    draft_count = Column(Integer, nullable=False, server_default="0")
    exception_count = Column(Integer, nullable=False, server_default="0")
    input_hash = Column(String(64), nullable=False)
    result = Column(JSONB, nullable=False, server_default="{}")
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    version = Column(Integer, nullable=False, server_default="1")
