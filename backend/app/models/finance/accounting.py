"""
会计核算底座 - 账套/科目/凭证/分录/总账余额
========================================
精确对标虎狼 models.py 中：
  account_books → FinBook
  chart_of_accounts → FinAccount
  vouchers → FinVoucher
  voucher_lines → FinVoucherLine
  ledger_daily_balances → FinLedgerBalance
适配：SQLite→PostgreSQL, TEXT→String, REAL→Numeric, INTEGER→Integer
"""
from sqlalchemy import (
    Column, Integer, String, Numeric, Date, Text, Boolean,
    ForeignKey, UniqueConstraint, DateTime, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.core.database import Base
from app.models.finance._base import TimestampMixin


class FinBook(Base, TimestampMixin):
    """
    账套主表（对标虎狼 account_books）
    每个独立核算主体一个账套，所有业务表通过 book_id 隔离
    """
    __tablename__ = "fin_books"

    id                   = Column(Integer, primary_key=True)
    book_code            = Column(String(32), unique=True, nullable=False)        # 账套编码（如 DEFAULT / BRANCH_SZ）
    book_name            = Column(String(128), nullable=False)                     # 账套名称
    company_name         = Column(String(128), nullable=False, default="牧马人服饰", server_default=text("'牧马人服饰'::character varying"))
    tax_entity_name      = Column(String(128), default="", server_default=text("''::character varying"))                         # 税务主体名称
    accounting_standard  = Column(String(32), default="小企业会计准则", server_default=text("'小企业会计准则'::character varying"))             # 会计准则
    base_currency        = Column(String(8), default="CNY", server_default=text("'CNY'::character varying"))                        # 本位币
    start_date           = Column(String(10))                                      # 启用日期 YYYY-MM-DD
    current_period       = Column(String(7), default="", server_default=text("''::character varying"))                           # 当前会计期间 YYYY-MM
    status               = Column(String(16), default="active", server_default=text("'active'::character varying"))                    # active/closed/locked
    safety_cash_line     = Column(Numeric(14, 2), default=300000, server_default=text("300000"))                  # 安全现金线
    enable_ai_summary    = Column(Boolean, default=True, server_default=text("true"))                           # 是否启用AI摘要
    wecom_group_key      = Column(String(128), default="", server_default=text("''::character varying"))                         # 企微群Webhook key
    template_source_id   = Column(Integer, default=0, server_default=text("0"))                              # 科目模板来源账套ID(0=默认)
    created_by           = Column(String(64), default="", server_default=text("''::character varying"))


class FinAccount(Base, TimestampMixin):
    """
    会计科目（对标虎狼 chart_of_accounts）
    小企业会计准则，一级科目自动初始化
    """
    __tablename__ = "fin_accounts"
    __table_args__ = (UniqueConstraint("book_id", "account_code", name="uq_fin_accounts_book_code"),)

    id            = Column(Integer, primary_key=True)
    book_id       = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    account_code  = Column(String(16), nullable=False)         # 科目编码（1001/1002/...）
    account_name  = Column(String(64), nullable=False)         # 科目名称
    parent_id     = Column(Integer, ForeignKey("fin_accounts.id"), nullable=True)  # 上级科目
    account_type  = Column(String(16), nullable=False)         # asset/liability/equity/income/expense
    direction     = Column(String(8), nullable=False, default="debit", server_default=text("'debit'::character varying"))  # debit/credit 余额方向
    level         = Column(Integer, default=1, server_default=text("1"))                 # 科目级别
    is_active     = Column(Boolean, default=True, server_default=text("true"))
    is_cash_flow  = Column(Boolean, default=False, server_default=text("false"))             # 是否现金流科目
    has_quantity   = Column(Boolean, default=False, server_default=text("false"))            # 是否数量核算
    has_currency   = Column(Boolean, default=False, server_default=text("false"))            # 是否外币核算


class FinVoucher(Base, TimestampMixin):
    """
    凭证主表（对标虎狼 vouchers）
    状态流转：draft → reviewed → posted → reversed
    """
    __tablename__ = "fin_vouchers"
    __table_args__ = (UniqueConstraint("book_id", "voucher_no", name="uq_fin_vouchers_book_no"),)

    id             = Column(Integer, primary_key=True)
    book_id        = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    voucher_no     = Column(String(32), nullable=False)        # 凭证编号（如 记-202604-001）
    voucher_type   = Column(String(8), default="记", server_default=text("'记'::character varying"))           # 凭证字：记/收/付/转
    voucher_date   = Column(Date, nullable=False, index=True)  # 凭证日期
    source_type    = Column(String(32), default="manual", server_default=text("'manual'::character varying"))      # manual/jst_sales/jst_refund/payroll/depreciation
    source_ref     = Column(String(128))                       # 来源单据号
    summary        = Column(Text)                              # 凭证摘要
    status         = Column(String(16), default="draft", server_default=text("'draft'::character varying"))       # draft/reviewed/posted/reversed
    attachment_url = Column(String(512))                       # 附件URL
    reviewed_by    = Column(String(64))                        # 审核人
    reviewed_at    = Column(DateTime)
    posted_by      = Column(String(64))                        # 过账人
    posted_at      = Column(DateTime)
    created_by     = Column(String(64), server_default=text("''::character varying"))                        # 制单人
    total_debit    = Column(Numeric(14, 2), default=0, server_default=text("0"))         # 借方合计（冗余，加速查询）
    total_credit   = Column(Numeric(14, 2), default=0, server_default=text("0"))         # 贷方合计
    period         = Column(String(7))                                         # 所属期间 YYYY-MM


class FinVoucherLine(Base):
    """
    凭证分录明细（对标虎狼 voucher_lines）
    每张凭证至少2条分录，借贷必须平衡
    """
    __tablename__ = "fin_voucher_lines"

    id            = Column(Integer, primary_key=True)
    voucher_id    = Column(Integer, ForeignKey("fin_vouchers.id", ondelete="CASCADE"), nullable=False, index=True)
    line_no       = Column(Integer, default=1, server_default=text("1"))                 # 行号
    account_id    = Column(Integer, ForeignKey("fin_accounts.id"), nullable=False)  # 科目ID
    account_code  = Column(String(16))                         # 科目编码（冗余）
    debit_amount  = Column(Numeric(14, 2), default=0, server_default=text("0"))          # 借方金额
    credit_amount = Column(Numeric(14, 2), default=0, server_default=text("0"))          # 贷方金额
    summary       = Column(String(256))                        # 分录摘要
    biz_date      = Column(Date)                               # 业务日期
    # 辅助核算
    customer_id   = Column(Integer)
    supplier_id   = Column(Integer)
    employee_id   = Column(Integer)
    department_id = Column(Integer)
    project_code  = Column(String(64))
    store_id      = Column(Integer)
    order_no      = Column(String(64))
    created_at    = Column(DateTime, default=func.now(), server_default=text("now()"))


class FinLedgerBalance(Base):
    """
    科目余额表 / 总账余额（对标虎狼 ledger_daily_balances）
    粒度：book_id + account_id + period
    """
    __tablename__ = "fin_ledger_balances"
    __table_args__ = (
        UniqueConstraint("book_id", "account_id", "period", name="uq_fin_ledger_book_acct_period"),
    )

    id             = Column(Integer, primary_key=True)
    book_id        = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id     = Column(Integer, ForeignKey("fin_accounts.id"), nullable=False, index=True)
    period         = Column(String(7), nullable=False)         # YYYY-MM（会计期间）
    opening_debit  = Column(Numeric(14, 2), default=0, server_default=text("0"))         # 期初借方
    opening_credit = Column(Numeric(14, 2), default=0, server_default=text("0"))         # 期初贷方
    period_debit   = Column(Numeric(14, 2), default=0, server_default=text("0"))         # 本期借方发生额
    period_credit  = Column(Numeric(14, 2), default=0, server_default=text("0"))         # 本期贷方发生额
    closing_debit  = Column(Numeric(14, 2), default=0, server_default=text("0"))         # 期末借方
    closing_credit = Column(Numeric(14, 2), default=0, server_default=text("0"))         # 期末贷方


class FinPeriod(Base):
    """会计期间（独立管理，结账/反结账/锁账）"""
    __tablename__ = "fin_periods"
    __table_args__ = (UniqueConstraint("book_id", "period", name="uq_fin_periods_book_period"),)

    id         = Column(Integer, primary_key=True)
    book_id    = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    period     = Column(String(7), nullable=False)
    status     = Column(String(16), default="open", server_default=text("'open'::character varying"))
    closed_by  = Column(String(64))
    closed_at  = Column(DateTime)
    locked_by  = Column(String(64))
    locked_at  = Column(DateTime)
    remark     = Column(Text)
    created_at = Column(DateTime, default=func.now(), server_default=text("now()"))

class FinVoucherTemplate(Base, TimestampMixin):
    """凭证模板（常用会计分录的快速复用）"""
    __tablename__ = "fin_voucher_templates"

    id           = Column(Integer, primary_key=True)
    book_id      = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    name         = Column(String(64), nullable=False)
    voucher_type = Column(String(8), default="记", server_default=text("'记'::character varying"))
    summary      = Column(Text)
    lines        = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_by   = Column(String(64))
