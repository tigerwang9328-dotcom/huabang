from sqlalchemy import Column, Integer, Numeric, Date, Text, ForeignKey, UniqueConstraint, text
from app.core.database import Base
from app.models.finance._base import TimestampMixin


class FinStoreDailyAdCost(Base, TimestampMixin):
    """每日广告费和赔付维护表（按日期+店铺，人工录入）"""
    __tablename__ = "finance_store_daily_ad_costs"
    __table_args__ = (
        UniqueConstraint("biz_date", "store_id", name="uq_fsdac_date_store"),
    )

    id         = Column(Integer, primary_key=True)
    biz_date   = Column(Date, nullable=False, index=True)
    store_id   = Column(Integer, ForeignKey("biz_stores.id", ondelete="CASCADE"), nullable=False, index=True)
    ad_cost    = Column(Numeric(12, 2), nullable=False, default=0, server_default=text("0"))
    compensation_amount = Column(Numeric(12, 2), nullable=False, default=0, server_default=text("0"))
    remark     = Column(Text)
    updated_by = Column(Integer)
