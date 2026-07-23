"""
业务台账 - 客户/供应商/应收/应付/出纳/工资/资产/发票/债务
========================================
精确对标虎狼 models.py 中对应表，适配 PG + async ORM
"""
from sqlalchemy import (
    Column, Integer, String, Numeric, Date, Text, Boolean,
    ForeignKey, UniqueConstraint, DateTime, text,
)
from sqlalchemy.sql import func
from app.core.database import Base
from app.models.finance._base import TimestampMixin


class FinCustomer(Base, TimestampMixin):
    """客户台账"""
    __tablename__ = "fin_customers"
    __table_args__ = (UniqueConstraint("book_id", "code", name="uq_fin_customers_book_code"),)
    id          = Column(Integer, primary_key=True)
    book_id     = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    code        = Column(String(32), nullable=False)
    name        = Column(String(128), nullable=False)
    platform    = Column(String(32))              # 抖音/快手/视频号/线下
    contact     = Column(String(128))
    credit_days = Column(Integer, default=30, server_default=text("30"))
    is_active   = Column(Boolean, default=True, server_default=text("true"))


class FinSupplier(Base, TimestampMixin):
    """供应商台账"""
    __tablename__ = "fin_suppliers"
    __table_args__ = (UniqueConstraint("book_id", "code", name="uq_fin_suppliers_book_code"),)
    id          = Column(Integer, primary_key=True)
    book_id     = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    code        = Column(String(32), nullable=False)
    name        = Column(String(128), nullable=False)
    contact     = Column(String(128))
    credit_days = Column(Integer, default=30, server_default=text("30"))
    is_active   = Column(Boolean, default=True, server_default=text("true"))


class FinReceivable(Base, TimestampMixin):
    """应收账款"""
    __tablename__ = "fin_receivables"
    id           = Column(Integer, primary_key=True)
    book_id      = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id  = Column(Integer, ForeignKey("fin_customers.id"), nullable=True)
    invoice_no   = Column(String(64))
    invoice_date = Column(Date, nullable=False)
    due_date     = Column(Date)
    amount       = Column(Numeric(14, 2), default=0, server_default=text("0"))
    paid_amount  = Column(Numeric(14, 2), default=0, server_default=text("0"))
    status       = Column(String(16), default="open", server_default=text("'open'::character varying"))      # open/partial/paid/overdue/bad_debt
    source_type  = Column(String(32), default="manual", server_default=text("'manual'::character varying"))
    source_ref   = Column(String(128))
    remark       = Column(Text)


class FinPayable(Base, TimestampMixin):
    """应付账款"""
    __tablename__ = "fin_payables"
    id           = Column(Integer, primary_key=True)
    book_id      = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id  = Column(Integer, ForeignKey("fin_suppliers.id"), nullable=True)
    invoice_no   = Column(String(64))
    invoice_date = Column(Date, nullable=False)
    due_date     = Column(Date)
    amount       = Column(Numeric(14, 2), default=0, server_default=text("0"))
    paid_amount  = Column(Numeric(14, 2), default=0, server_default=text("0"))
    status       = Column(String(16), default="open", server_default=text("'open'::character varying"))      # open/partial/paid/overdue
    source_type  = Column(String(32), default="manual", server_default=text("'manual'::character varying"))
    source_ref   = Column(String(128))
    remark       = Column(Text)


class FinCashAccount(Base, TimestampMixin):
    """出纳账户（银行/支付宝/微信/现金）"""
    __tablename__ = "fin_cash_accounts"
    __table_args__ = (UniqueConstraint("book_id", "account_name", name="uq_fin_cash_accounts_book_name"),)
    id           = Column(Integer, primary_key=True)
    book_id      = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    account_name = Column(String(128), nullable=False)
    account_type = Column(String(16), default="bank", server_default=text("'bank'::character varying"))      # bank/alipay/wechat/cash
    bank_name    = Column(String(128))
    account_no   = Column(String(64))
    balance      = Column(Numeric(14, 2), default=0, server_default=text("0"))
    is_active    = Column(Boolean, default=True, server_default=text("true"))


class FinCashFlow(Base):
    """出纳流水"""
    __tablename__ = "fin_cash_flows"
    id              = Column(Integer, primary_key=True)
    book_id         = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    cash_account_id = Column(Integer, ForeignKey("fin_cash_accounts.id"), nullable=False)
    flow_date       = Column(Date, nullable=False, index=True)
    flow_type       = Column(String(8), nullable=False)    # in/out
    amount          = Column(Numeric(14, 2), default=0, server_default=text("0"))
    category        = Column(String(32))                    # 销售回款/供应商付款/工资/房租/税费/贷款/其他
    counterpart     = Column(String(128))                   # 交易对手
    remark          = Column(Text)
    voucher_id      = Column(Integer, ForeignKey("fin_vouchers.id"), nullable=True)
    created_at      = Column(DateTime, default=func.now(), server_default=text("now()"))


class FinPayrollRecord(Base, TimestampMixin):
    """工资记录"""
    __tablename__ = "fin_payroll_records"
    __table_args__ = (UniqueConstraint("book_id", "pay_month", "employee_name", name="uq_fin_payroll_book_month_emp"),)
    id            = Column(Integer, primary_key=True)
    book_id       = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    pay_month     = Column(String(7), nullable=False, index=True)  # YYYY-MM
    employee_name = Column(String(64), nullable=False)
    department    = Column(String(64))
    base_salary   = Column(Numeric(12, 2), default=0, server_default=text("0"))
    bonus         = Column(Numeric(12, 2), default=0, server_default=text("0"))
    deductions    = Column(Numeric(12, 2), default=0, server_default=text("0"))
    social_insurance = Column(Numeric(12, 2), default=0, server_default=text("0"))   # 社保
    housing_fund  = Column(Numeric(12, 2), default=0, server_default=text("0"))      # 公积金
    tax           = Column(Numeric(12, 2), default=0, server_default=text("0"))       # 个税
    net_pay       = Column(Numeric(12, 2), default=0, server_default=text("0"))       # 实发工资
    gross_pay     = Column(Numeric(12, 2), default=0, server_default=text("0"))       # 应发工资（修复虎狼bug）
    cost_type     = Column(String(16), default="管理费用", server_default=text("'管理费用'::character varying"))   # 管理费用/销售费用
    status        = Column(String(16), default="pending", server_default=text("'pending'::character varying"))   # pending/paid
    voucher_id    = Column(Integer, ForeignKey("fin_vouchers.id"), nullable=True)


class FinDebtRecord(Base, TimestampMixin):
    """债务记录"""
    __tablename__ = "fin_debt_records"
    id            = Column(Integer, primary_key=True)
    book_id       = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    debt_name     = Column(String(128), nullable=False)
    debt_type     = Column(String(32), nullable=False)      # bank_loan/supplier/payroll/rent/tax/other
    creditor      = Column(String(128))
    principal     = Column(Numeric(14, 2), default=0, server_default=text("0"))
    interest_rate = Column(Numeric(8, 4), default=0, server_default=text("0"))
    due_date      = Column(Date)
    next_payment  = Column(Numeric(14, 2), default=0, server_default=text("0"))
    next_pay_date = Column(Date)
    risk_level    = Column(String(16), default="正常", server_default=text("'正常'::character varying"))       # 高风险/中风险/正常
    priority      = Column(Integer, default=5, server_default=text("5"))
    status        = Column(String(16), default="active", server_default=text("'active'::character varying"))    # active/paid/overdue
    remark        = Column(Text)


class FinFixedAsset(Base, TimestampMixin):
    """固定资产"""
    __tablename__ = "fin_fixed_assets"
    __table_args__ = (UniqueConstraint("book_id", "asset_code", name="uq_fin_fixed_assets_book_code"),)
    id              = Column(Integer, primary_key=True)
    book_id         = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_code      = Column(String(32), nullable=False)
    asset_name      = Column(String(128), nullable=False)
    category        = Column(String(32))                     # 办公设备/生产设备/运输工具/电子设备/其他
    purchase_date   = Column(Date)
    original_value  = Column(Numeric(14, 2), default=0, server_default=text("0"))
    net_value       = Column(Numeric(14, 2), default=0, server_default=text("0"))
    depre_method    = Column(String(16), default="straight_line", server_default=text("'straight_line'::character varying"))  # straight_line/double_declining
    depre_years     = Column(Integer, default=5, server_default=text("5"))
    monthly_depre   = Column(Numeric(14, 2), default=0, server_default=text("0"))
    accumulated_depre = Column(Numeric(14, 2), default=0, server_default=text("0"))    # 累计折旧
    status          = Column(String(16), default="in_use", server_default=text("'in_use'::character varying"))   # in_use/scrapped/sold


class FinInvoice(Base, TimestampMixin):
    """发票台账"""
    __tablename__ = "fin_invoices"
    id           = Column(Integer, primary_key=True)
    book_id      = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_type = Column(String(16), default="output", server_default=text("'output'::character varying"))     # output=销项/input=进项
    invoice_no   = Column(String(64))
    invoice_date = Column(Date)
    counterpart  = Column(String(128))                       # 购/销方名称
    amount       = Column(Numeric(14, 2), default=0, server_default=text("0"))         # 不含税金额
    tax_amount   = Column(Numeric(14, 2), default=0, server_default=text("0"))         # 税额
    total_amount = Column(Numeric(14, 2), default=0, server_default=text("0"))         # 价税合计
    tax_rate     = Column(Numeric(6, 4), default=0, server_default=text("0"))
    status       = Column(String(16), default="normal", server_default=text("'normal'::character varying"))      # normal/voided
    remark       = Column(Text)

class FinRecvOrder(Base, TimestampMixin):
    """应收单据头（明细型应收，含分行商品明细）"""
    __tablename__ = "fin_recv_orders"
    __table_args__ = (UniqueConstraint("book_id", "order_no", name="uq_fin_recv_orders_book_no"),)

    id              = Column(Integer, primary_key=True)
    book_id         = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    order_no        = Column(String(32), nullable=False)
    period          = Column(String(7))
    order_date      = Column(Date, nullable=False)
    customer_id     = Column(Integer, ForeignKey("fin_customers.id"), nullable=True)
    customer_name   = Column(String(128))
    contact         = Column(String(64))
    total_amount    = Column(Numeric(14, 2), default=0, server_default=text("0"))
    received_amount = Column(Numeric(14, 2), default=0, server_default=text("0"))
    status          = Column(String(16), default="open", server_default=text("'open'::character varying"))
    voucher_id      = Column(Integer, ForeignKey("fin_vouchers.id"), nullable=True)
    remark          = Column(Text)
    created_by      = Column(String(64))


class FinRecvOrderLine(Base):
    """应收单据明细行"""
    __tablename__ = "fin_recv_order_lines"

    id         = Column(Integer, primary_key=True)
    order_id   = Column(Integer, ForeignKey("fin_recv_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    line_no    = Column(Integer, default=1, server_default=text("1"))
    item_name  = Column(String(128), nullable=False)
    spec       = Column(String(128))
    quantity   = Column(Numeric(10, 2), default=1, server_default=text("1"))
    unit_price = Column(Numeric(14, 4), default=0, server_default=text("0"))
    amount     = Column(Numeric(14, 2), default=0, server_default=text("0"))
    tax_rate   = Column(Numeric(5, 2), default=0, server_default=text("0"))
    tax_amount = Column(Numeric(14, 2), default=0, server_default=text("0"))
    remark     = Column(Text)


class FinPayableOrder(Base, TimestampMixin):
    """应付单据头（明细型应付，含分行商品明细）"""
    __tablename__ = "fin_payable_orders"
    __table_args__ = (UniqueConstraint("book_id", "order_no", name="uq_fin_payable_orders_book_no"),)

    id           = Column(Integer, primary_key=True)
    book_id      = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    order_no     = Column(String(32), nullable=False)
    period       = Column(String(7))
    order_date   = Column(Date, nullable=False)
    supplier_id  = Column(Integer, ForeignKey("fin_suppliers.id"), nullable=True)
    supplier_name = Column(String(128))
    contact      = Column(String(64))
    total_amount = Column(Numeric(14, 2), default=0, server_default=text("0"))
    paid_amount  = Column(Numeric(14, 2), default=0, server_default=text("0"))
    status       = Column(String(16), default="open", server_default=text("'open'::character varying"))
    voucher_id   = Column(Integer, ForeignKey("fin_vouchers.id"), nullable=True)
    remark       = Column(Text)
    created_by   = Column(String(64))


class FinPayableOrderLine(Base):
    """应付单据明细行"""
    __tablename__ = "fin_payable_order_lines"

    id         = Column(Integer, primary_key=True)
    order_id   = Column(Integer, ForeignKey("fin_payable_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    line_no    = Column(Integer, default=1, server_default=text("1"))
    item_name  = Column(String(128), nullable=False)
    spec       = Column(String(128))
    quantity   = Column(Numeric(10, 2), default=1, server_default=text("1"))
    unit_price = Column(Numeric(14, 4), default=0, server_default=text("0"))
    amount     = Column(Numeric(14, 2), default=0, server_default=text("0"))
    tax_rate   = Column(Numeric(5, 2), default=0, server_default=text("0"))
    tax_amount = Column(Numeric(14, 2), default=0, server_default=text("0"))
    remark     = Column(Text)
