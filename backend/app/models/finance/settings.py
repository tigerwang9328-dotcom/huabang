"""
设置与日志 - 辅助核算/审计日志/报表快照/AI报告/账套权限
"""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean,
    ForeignKey, UniqueConstraint, DateTime, text,
)
from sqlalchemy.sql import func
from app.core.database import Base
from app.models.finance._base import TimestampMixin


class FinAuxCategory(Base, TimestampMixin):
    """辅助核算类别"""
    __tablename__ = "fin_aux_categories"
    __table_args__ = (UniqueConstraint("book_id", "category_code", name="uq_fin_aux_cat_book_code"),)
    id            = Column(Integer, primary_key=True)
    book_id       = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    category_code = Column(String(32), nullable=False)      # customer/supplier/department/project/store
    category_name = Column(String(64), nullable=False)
    is_active     = Column(Boolean, default=True, server_default=text("true"))


class FinAuxItem(Base, TimestampMixin):
    """辅助核算项"""
    __tablename__ = "fin_aux_items"
    __table_args__ = (UniqueConstraint("category_id", "item_code", name="uq_fin_aux_items_cat_code"),)
    id          = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("fin_aux_categories.id", ondelete="CASCADE"), nullable=False, index=True)
    item_code   = Column(String(32), nullable=False)
    item_name   = Column(String(128), nullable=False)
    is_active   = Column(Boolean, default=True, server_default=text("true"))


class FinAuditLog(Base):
    """审计日志"""
    __tablename__ = "fin_audit_logs"
    id         = Column(Integer, primary_key=True)
    book_id    = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=True, index=True)
    operator   = Column(String(64))
    action     = Column(String(32), nullable=False)          # create_voucher/review/post/close/unclose/export/switch_book/...
    target     = Column(String(64))                          # voucher:123 / period:2026-04 / ...
    detail     = Column(Text)
    ip_address = Column(String(64))
    created_at = Column(DateTime, default=func.now(), server_default=text("now()"))


class FinStatementSnapshot(Base):
    """三表快照（资产负债表/利润表/现金流量表结果缓存）"""
    __tablename__ = "fin_statement_snapshots"
    id             = Column(Integer, primary_key=True)
    book_id        = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    statement_type = Column(String(32), nullable=False)      # balance_sheet/profit/cashflow
    period_start   = Column(String(10), nullable=False)
    period_end     = Column(String(10), nullable=False)
    data_json      = Column(Text, nullable=False)
    created_at     = Column(DateTime, default=func.now(), server_default=text("now()"))


class FinAiReport(Base):
    """AI财务报告"""
    __tablename__ = "fin_ai_reports"
    id           = Column(Integer, primary_key=True)
    book_id      = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    report_type  = Column(String(16), nullable=False)        # daily/weekly/monthly/risk
    report_date  = Column(String(10), nullable=False)
    content      = Column(Text)
    status       = Column(String(16), default="draft", server_default=text("'draft'::character varying"))
    created_at   = Column(DateTime, default=func.now(), server_default=text("now()"))


class FinBookPermission(Base):
    """账套权限"""
    __tablename__ = "fin_book_permissions"
    __table_args__ = (UniqueConstraint("user_id", "book_id", "permission", name="uq_fin_book_perm"),)
    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("sys_users.id", ondelete="CASCADE"), nullable=False, index=True)
    book_id    = Column(Integer, ForeignKey("fin_books.id", ondelete="CASCADE"), nullable=False, index=True)
    permission = Column(String(32), nullable=False)          # admin/read/write/review/post/close
