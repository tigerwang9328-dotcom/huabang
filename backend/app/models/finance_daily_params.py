from sqlalchemy import Column, Integer, Numeric, String, Boolean, Text, ForeignKey, UniqueConstraint, text
from app.core.database import Base
from app.models.finance._base import TimestampMixin


class FinStoreDailyParams(Base, TimestampMixin):
    """店铺日报参数表（按月配置，用于日报公式计算）"""
    __tablename__ = "finance_store_daily_params"
    __table_args__ = (
        UniqueConstraint("month", "store_id", name="uq_fsdp_month_store"),
    )

    id            = Column(Integer, primary_key=True)
    month         = Column(String(7), nullable=False, index=True)      # YYYY-MM
    store_id      = Column(Integer, ForeignKey("biz_stores.id", ondelete="CASCADE"), index=True)
    store_name    = Column(String(200))
    platform      = Column(String(50))

    # 平台系数
    platform_commission_rate = Column(Numeric(6, 4), default=0, server_default=text("0"))   # 平台佣金率（暂保留，L 直接用 income_rate）
    platform_income_rate     = Column(Numeric(6, 4), default=1, server_default=text("1"))   # 平台收入系数 L = K × income_rate

    # 预计退货率（actual refund_rate=0 时 fallback）
    estimated_return_rate = Column(Numeric(6, 4), default=0, server_default=text("0"))
    refund_only_rate      = Column(Numeric(6, 4), default=0, server_default=text("0"))  # X 仅退款率

    # 单件/单单成本参数
    freight_insurance_unit_cost = Column(Numeric(10, 4), default=0, server_default=text("0"))  # Q 运费险/件
    express_unit_cost           = Column(Numeric(10, 4), default=0, server_default=text("0"))  # S 快递费/件
    package_unit_cost           = Column(Numeric(10, 4), default=0, server_default=text("0"))  # R 包装成本/单
    return_labor_unit_cost      = Column(Numeric(10, 4), default=0, server_default=text("0"))  # V 退货人工/件
    goods_loss_unit_cost        = Column(Numeric(10, 4), default=0, server_default=text("0"))  # W 货值损耗/件
    promotion_unit_cost         = Column(Numeric(10, 4), default=0, server_default=text("0"))  # U 推广单件成本

    # 预警配置
    return_rate_warning_threshold = Column(Numeric(6, 4), default=0.08, server_default=text("0.08"))
    warning_enabled               = Column(Boolean, default=True, server_default=text("true"))

    remark     = Column(Text)
    updated_by = Column(Integer)
