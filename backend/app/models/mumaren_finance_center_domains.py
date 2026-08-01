"""牧马人财务中心的应收应付、经营和税务独立领域模型。

本文件不依赖华邦旧财务模型或表。所有持久化对象均置于
``finance_center_mumaren`` schema，并由独立迁移创建。
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


MUMAREN_FINANCE_DOMAIN_SCHEMA = "finance_center_mumaren"
_BOOK = f"{MUMAREN_FINANCE_DOMAIN_SCHEMA}.finance_center_mumaren_books.id"


class FinanceCenterMumarenCounterparty(Base):
    __tablename__ = "finance_center_mumaren_counterparties"
    __table_args__ = (
        UniqueConstraint("book_id", "counterparty_type", "counterparty_code", name="uq_mumaren_finance_counterparty"),
        CheckConstraint("counterparty_type IN ('customer', 'supplier')", name="ck_mumaren_finance_counterparty_type"),
        {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    counterparty_type: Mapped[str] = mapped_column(String(16), nullable=False)
    counterparty_code: Mapped[str] = mapped_column(String(64), nullable=False)
    counterparty_name: Mapped[str] = mapped_column(String(128), nullable=False)
    contact: Mapped[str | None] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(64))
    tax_no: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class _MumarenOrderBase:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    order_no: Mapped[str] = mapped_column(String(64), nullable=False)
    order_date: Mapped[object] = mapped_column(Date, nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    counterparty_id: Mapped[int | None] = mapped_column(BigInteger)
    counterparty_name: Mapped[str] = mapped_column(String(128), nullable=False)
    total_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    settled_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    settlement_status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    workflow_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    remark: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)
    posted_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceCenterMumarenReceivableOrder(_MumarenOrderBase, Base):
    __tablename__ = "finance_center_mumaren_receivable_orders"
    __table_args__ = (
        UniqueConstraint("book_id", "order_no", name="uq_mumaren_finance_receivable_order"),
        CheckConstraint("workflow_status IN ('draft', 'reviewed', 'posted')", name="ck_mumaren_finance_receivable_workflow"),
        CheckConstraint("settlement_status IN ('open', 'partial', 'settled')", name="ck_mumaren_finance_receivable_settlement"),
        CheckConstraint("settled_amount >= 0 AND total_amount >= 0 AND settled_amount <= total_amount", name="ck_mumaren_finance_receivable_amount"),
        {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA},
    )


class FinanceCenterMumarenPayableOrder(_MumarenOrderBase, Base):
    __tablename__ = "finance_center_mumaren_payable_orders"
    __table_args__ = (
        UniqueConstraint("book_id", "order_no", name="uq_mumaren_finance_payable_order"),
        CheckConstraint("workflow_status IN ('draft', 'reviewed', 'posted')", name="ck_mumaren_finance_payable_workflow"),
        CheckConstraint("settlement_status IN ('open', 'partial', 'settled')", name="ck_mumaren_finance_payable_settlement"),
        CheckConstraint("settled_amount >= 0 AND total_amount >= 0 AND settled_amount <= total_amount", name="ck_mumaren_finance_payable_amount"),
        {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA},
    )


class _MumarenOrderLineBase:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    spec: Mapped[str | None] = mapped_column(String(255))
    quantity: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=1)
    unit_price: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    tax_rate: Mapped[object] = mapped_column(Numeric(8, 4), nullable=False, default=0)
    tax_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    remark: Mapped[str | None] = mapped_column(String(500))


class FinanceCenterMumarenReceivableOrderLine(_MumarenOrderLineBase, Base):
    __tablename__ = "finance_center_mumaren_receivable_order_lines"
    __table_args__ = (UniqueConstraint("order_id", "line_no", name="uq_mumaren_finance_receivable_line"), {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA})
    order_id: Mapped[int] = mapped_column(ForeignKey(f"{MUMAREN_FINANCE_DOMAIN_SCHEMA}.finance_center_mumaren_receivable_orders.id", ondelete="CASCADE"), nullable=False)


class FinanceCenterMumarenPayableOrderLine(_MumarenOrderLineBase, Base):
    __tablename__ = "finance_center_mumaren_payable_order_lines"
    __table_args__ = (UniqueConstraint("order_id", "line_no", name="uq_mumaren_finance_payable_line"), {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA})
    order_id: Mapped[int] = mapped_column(ForeignKey(f"{MUMAREN_FINANCE_DOMAIN_SCHEMA}.finance_center_mumaren_payable_orders.id", ondelete="CASCADE"), nullable=False)


class FinanceCenterMumarenArApSettlement(Base):
    __tablename__ = "finance_center_mumaren_ar_ap_settlements"
    __table_args__ = (CheckConstraint("settlement_type IN ('receivable', 'payable')", name="ck_mumaren_finance_settlement_type"), {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    settlement_type: Mapped[str] = mapped_column(String(16), nullable=False)
    order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    settlement_date: Mapped[object] = mapped_column(Date, nullable=False)
    amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False)
    workflow_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    voucher_id: Mapped[int | None] = mapped_column(BigInteger)
    remark: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceCenterMumarenCashAccount(Base):
    __tablename__ = "finance_center_mumaren_cash_accounts"
    __table_args__ = (UniqueConstraint("book_id", "account_code", name="uq_mumaren_finance_cash_account"), {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    account_code: Mapped[str] = mapped_column(String(64), nullable=False)
    account_name: Mapped[str] = mapped_column(String(128), nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), nullable=False, default="bank")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="CNY")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FinanceCenterMumarenCashFlow(Base):
    __tablename__ = "finance_center_mumaren_cash_flows"
    __table_args__ = (CheckConstraint("direction IN ('in', 'out')", name="ck_mumaren_finance_cash_flow_direction"), {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    cash_account_id: Mapped[int] = mapped_column(ForeignKey(f"{MUMAREN_FINANCE_DOMAIN_SCHEMA}.finance_center_mumaren_cash_accounts.id"), nullable=False)
    flow_date: Mapped[object] = mapped_column(Date, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64))
    counterparty_name: Mapped[str | None] = mapped_column(String(128))
    workflow_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    voucher_id: Mapped[int | None] = mapped_column(BigInteger)
    remark: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceCenterMumarenFixedAsset(Base):
    __tablename__ = "finance_center_mumaren_fixed_assets"
    __table_args__ = (UniqueConstraint("book_id", "asset_code", name="uq_mumaren_finance_asset"), {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    asset_code: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_category: Mapped[str | None] = mapped_column(String(64))
    purchase_date: Mapped[object] = mapped_column(Date, nullable=False)
    original_value: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False)
    residual_value: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    useful_life_months: Mapped[int] = mapped_column(Integer, nullable=False)
    accumulated_depreciation: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceCenterMumarenInvoice(Base):
    __tablename__ = "finance_center_mumaren_invoices"
    __table_args__ = (UniqueConstraint("book_id", "invoice_no", name="uq_mumaren_finance_invoice"), {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    invoice_no: Mapped[str] = mapped_column(String(64), nullable=False)
    invoice_type: Mapped[str] = mapped_column(String(32), nullable=False)
    invoice_date: Mapped[object] = mapped_column(Date, nullable=False)
    counterparty_name: Mapped[str | None] = mapped_column(String(128))
    amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False)
    tax_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    workflow_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")


class FinanceCenterMumarenPayroll(Base):
    __tablename__ = "finance_center_mumaren_payrolls"
    __table_args__ = (UniqueConstraint("book_id", "period", "employee_no", name="uq_mumaren_finance_payroll"), {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    employee_no: Mapped[str] = mapped_column(String(64), nullable=False)
    employee_name: Mapped[str] = mapped_column(String(128), nullable=False)
    gross_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False)
    deduction_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    net_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False)
    workflow_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    voucher_id: Mapped[int | None] = mapped_column(BigInteger)


class FinanceCenterMumarenTaxType(Base):
    __tablename__ = "finance_center_mumaren_tax_types"
    __table_args__ = (UniqueConstraint("book_id", "tax_code", name="uq_mumaren_finance_tax_type"), {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    tax_code: Mapped[str] = mapped_column(String(64), nullable=False)
    tax_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tax_category: Mapped[str | None] = mapped_column(String(64))
    default_rate: Mapped[object] = mapped_column(Numeric(8, 4), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FinanceCenterMumarenTaxRecord(Base):
    __tablename__ = "finance_center_mumaren_tax_records"
    __table_args__ = (
        UniqueConstraint("book_id", "tax_type_id", "period", name="uq_mumaren_finance_tax_record"),
        CheckConstraint("paid_amount >= 0 AND tax_amount >= 0 AND paid_amount <= tax_amount", name="ck_mumaren_finance_tax_amount"),
        {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    tax_type_id: Mapped[int] = mapped_column(ForeignKey(f"{MUMAREN_FINANCE_DOMAIN_SCHEMA}.finance_center_mumaren_tax_types.id"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    tax_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False)
    paid_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    due_date: Mapped[object | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    workflow_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    voucher_id: Mapped[int | None] = mapped_column(BigInteger)
    source_payload: Mapped[dict | None] = mapped_column(JSON)
    remark: Mapped[str | None] = mapped_column(Text)


class FinanceCenterMumarenVoucherTemplate(Base):
    __tablename__ = "finance_center_mumaren_voucher_templates"
    __table_args__ = (
        UniqueConstraint("book_id", "template_name", name="uq_mumaren_finance_voucher_template"),
        {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    template_name: Mapped[str] = mapped_column(String(128), nullable=False)
    voucher_type: Mapped[str] = mapped_column(String(16), nullable=False, default="记")
    summary: Mapped[str | None] = mapped_column(String(500))
    lines_json: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceCenterMumarenAutoVoucherRule(Base):
    __tablename__ = "finance_center_mumaren_auto_voucher_rules"
    __table_args__ = (
        UniqueConstraint("book_id", "rule_name", name="uq_mumaren_finance_auto_voucher_rule"),
        {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger_event: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[int | None] = mapped_column(BigInteger)
    direction: Mapped[str] = mapped_column(String(8), nullable=False, default="debit")
    amount_formula: Mapped[str | None] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceCenterMumarenExpenseEntry(Base):
    __tablename__ = "finance_center_mumaren_expense_entries"
    __table_args__ = (
        CheckConstraint("workflow_status IN ('draft', 'reviewed', 'posted')", name="ck_mumaren_finance_expense_workflow"),
        CheckConstraint("amount >= 0", name="ck_mumaren_finance_expense_amount"),
        {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    account_code: Mapped[str] = mapped_column(String(64), nullable=False)
    account_name: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    remark: Mapped[str | None] = mapped_column(Text)
    workflow_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceCenterMumarenSalesMonthlyReport(Base):
    __tablename__ = "finance_center_mumaren_sales_monthly_reports"
    __table_args__ = (
        UniqueConstraint("book_id", "period", "store_code", name="uq_mumaren_finance_sales_monthly"),
        {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    store_code: Mapped[str] = mapped_column(String(32), nullable=False)
    store_name: Mapped[str | None] = mapped_column(String(128))
    sales_amount: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    remark: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceCenterMumarenBankReconciliation(Base):
    __tablename__ = "finance_center_mumaren_bank_reconciliations"
    __table_args__ = (
        UniqueConstraint("book_id", "cash_account_id", "period", name="uq_mumaren_finance_bank_reconciliation"),
        {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    cash_account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    bank_balance: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    book_balance: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    adjusted_balance: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    items_json: Mapped[dict | None] = mapped_column(JSON)
    workflow_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceCenterMumarenAuxiliaryAccounting(Base):
    __tablename__ = "finance_center_mumaren_auxiliary_accountings"
    __table_args__ = (
        UniqueConstraint("book_id", "aux_type", "code", name="uq_mumaren_finance_auxiliary_accounting"),
        CheckConstraint("aux_type IN ('customer', 'supplier', 'employee', 'project', 'department')", name="ck_mumaren_finance_aux_type"),
        {"schema": MUMAREN_FINANCE_DOMAIN_SCHEMA},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(_BOOK), nullable=False)
    aux_type: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
