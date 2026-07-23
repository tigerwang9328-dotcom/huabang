"""
数据罗盘（原有5张表，不动）
从原 app/models/finance.py 迁移过来，保持完全一致
"""
from sqlalchemy import (
    Column, Integer, String, Numeric, Date, Boolean,
    Text, ForeignKey, UniqueConstraint, text,
)
from app.core.database import Base
from app.models.finance._base import TimestampMixin


class FinanceReceipt(Base, TimestampMixin):
    """平台回款 / 结算到账记录"""
    __tablename__ = "biz_finance_receipts"
    id           = Column(Integer, primary_key=True)
    receipt_date = Column(Date, nullable=False, index=True)
    platform     = Column(String(64))
    store_name   = Column(String(128))
    store_id     = Column(Integer, ForeignKey("biz_stores.id", ondelete="SET NULL"), nullable=True)
    amount       = Column(Numeric(12, 2), default=0, server_default=text("0"), nullable=False)
    remark       = Column(String(256))
    created_by   = Column(Integer, ForeignKey("sys_users.id", ondelete="SET NULL"), nullable=True)


class FinanceFee(Base, TimestampMixin):
    """经营费用明细"""
    __tablename__ = "biz_finance_fees"
    id          = Column(Integer, primary_key=True)
    fee_date    = Column(Date, nullable=False, index=True)
    fee_type    = Column(String(32), nullable=False, default="other", server_default=text("'other'::character varying"), index=True)
    description = Column(String(256))
    store_id    = Column(Integer, ForeignKey("biz_stores.id", ondelete="SET NULL"), nullable=True)
    store_name  = Column(String(128))
    amount      = Column(Numeric(12, 2), default=0, server_default=text("0"), nullable=False)
    remark      = Column(String(256))
    created_by  = Column(Integer, ForeignKey("sys_users.id", ondelete="SET NULL"), nullable=True)


class FinDailySummary(Base, TimestampMixin):
    """全公司财务日汇总"""
    __tablename__ = "fin_daily_summary"
    __table_args__ = (UniqueConstraint("biz_date", name="uq_fin_daily_summary_date"),)
    id                = Column(Integer, primary_key=True)
    biz_date          = Column(Date, nullable=False, index=True)
    total_sales       = Column(Numeric(14, 2), default=0)
    total_refund      = Column(Numeric(14, 2), default=0)
    total_cogs        = Column(Numeric(14, 2), default=0)
    total_refund_cogs = Column(Numeric(14, 2), default=0)
    total_receipt     = Column(Numeric(14, 2), default=0)
    total_ad_cost     = Column(Numeric(14, 2), default=0)
    total_logistics   = Column(Numeric(14, 2), default=0)
    total_pack_cost   = Column(Numeric(14, 2), default=0)
    total_commission  = Column(Numeric(14, 2), default=0)
    total_labor_cost  = Column(Numeric(14, 2), default=0)
    gross_profit      = Column(Numeric(14, 2), default=0)
    net_profit        = Column(Numeric(14, 2), default=0)
    profit_rate       = Column(Numeric(8, 4), default=0)
    cashflow_net      = Column(Numeric(14, 2), default=0)
    store_count       = Column(Integer, default=0)


class FinRiskAlert(Base, TimestampMixin):
    """财务风险预警"""
    __tablename__ = "fin_risk_alerts"
    id            = Column(Integer, primary_key=True)
    biz_date      = Column(Date, nullable=False, index=True)
    alert_type    = Column(String(32), nullable=False, index=True)
    alert_level   = Column(String(16), default="warning")
    store_id      = Column(Integer, ForeignKey("biz_stores.id", ondelete="SET NULL"), nullable=True)
    store_name    = Column(String(128))
    metric_name   = Column(String(64))
    threshold     = Column(Numeric(12, 4))
    actual_value  = Column(Numeric(12, 4))
    message       = Column(Text)
    is_read       = Column(Boolean, default=False, index=True)
    read_by       = Column(Integer, ForeignKey("sys_users.id", ondelete="SET NULL"), nullable=True)


class FinCostConfig(Base, TimestampMixin):
    """月度固定费用配置"""
    __tablename__ = "fin_cost_config"
    __table_args__ = (UniqueConstraint("month", "cost_type", name="uq_fin_cost_config_month_type"),)
    id        = Column(Integer, primary_key=True)
    month     = Column(String(7), nullable=False, index=True)
    cost_type = Column(String(32), nullable=False)
    amount    = Column(Numeric(14, 2), default=0)
    remark    = Column(String(256))
