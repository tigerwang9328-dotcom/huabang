"""
税务管理 - 税种配置 / 税务台账
"""
from sqlalchemy import (
    Column, Integer, String, Numeric, Date, Text, Boolean,
    ForeignKey, UniqueConstraint, DateTime, text,
)
from sqlalchemy.sql import func
from app.core.database import Base
from app.models.finance._base import TimestampMixin


class FinTaxType(Base, TimestampMixin):
    """税种配置"""
    __tablename__ = "fin_tax_types"
    __table_args__ = (UniqueConstraint("book_id", "tax_code", name="uq_fin_tax_types_book_code"),)

    id           = Column(Integer, primary_key=True)
    book_id      = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    tax_code     = Column(String(16), nullable=False)       # VAT/CIT/IIT/STAMP/CITY
    tax_name     = Column(String(64), nullable=False)       # 增值税/企业所得税/个人所得税
    tax_rate     = Column(Numeric(8, 4), default=0, server_default=text("0"))
    tax_category = Column(String(16), default="vat", server_default=text("'vat'::character varying"))
    period_type  = Column(String(8), default="month", server_default=text("'month'::character varying"))  # month/quarter/year
    is_active    = Column(Boolean, default=True, server_default=text("true"))


class FinTaxRecord(Base, TimestampMixin):
    """税务台账（按期间）"""
    __tablename__ = "fin_tax_records"
    __table_args__ = (
        UniqueConstraint("book_id", "tax_type_id", "period", name="uq_fin_tax_records_book_type_period"),
    )

    id           = Column(Integer, primary_key=True)
    book_id      = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    tax_type_id  = Column(Integer, ForeignKey("fin_tax_types.id"), nullable=True)
    period       = Column(String(7), nullable=False, index=True)    # YYYY-MM
    tax_base     = Column(Numeric(14, 2), default=0, server_default=text("0"))    # 计税依据
    tax_amount   = Column(Numeric(14, 2), default=0, server_default=text("0"))    # 应纳税额
    paid_amount  = Column(Numeric(14, 2), default=0, server_default=text("0"))    # 已缴税额
    status       = Column(String(16), default="pending", server_default=text("'pending'::character varying"))
    due_date     = Column(Date)
    paid_date    = Column(Date)
    remark       = Column(Text)
    voucher_id   = Column(Integer, ForeignKey("fin_vouchers.id"), nullable=True)
