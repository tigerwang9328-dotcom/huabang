"""dwd schema: 明细清洗层"""
from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, BigInteger, Numeric, Text
from sqlalchemy.sql import func
from app.core.database import Base


class DwdSalesDetail(Base):
    """清洗后的销售明细（净销售，已剔除退货）"""
    __tablename__ = "dwd_sales_detail"
    __table_args__ = {"schema": "dwd"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_date = Column(Date, nullable=False)
    order_no = Column(String(64), nullable=False)
    detail_no = Column(String(64), nullable=False, unique=True)
    store_code = Column(String(32), nullable=False)
    channel = Column(String(32), nullable=False)
    product_code = Column(String(64))
    sku_code = Column(String(64))
    color = Column(String(64))
    size = Column(String(32))
    member_no = Column(String(64))
    guide_id = Column(String(32))
    quantity = Column(Integer)
    tag_price = Column(Numeric(12, 2))
    actual_price = Column(Numeric(12, 2))
    tag_amount = Column(Numeric(14, 2))
    actual_amount = Column(Numeric(14, 2))
    cost_price = Column(Numeric(12, 2))
    cost_amount = Column(Numeric(14, 2), comment="成本金额=数量×成本价")
    gross_profit = Column(Numeric(14, 2), comment="毛利=实收-成本")
    gross_margin = Column(Numeric(6, 4), comment="毛利率=毛利/实收")
    discount_rate = Column(Numeric(6, 4), comment="折扣率=实收/吊牌")
    is_cost_missing = Column(Boolean, default=False, comment="成本缺失标记")
    is_discount_abnormal = Column(Boolean, default=False, comment="折扣异常标记")
    is_member_sale = Column(Boolean, default=False)
    etl_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DwdReturnDetail(Base):
    """清洗后的退货明细"""
    __tablename__ = "dwd_return_detail"
    __table_args__ = {"schema": "dwd"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    return_date = Column(Date, nullable=False)
    return_no = Column(String(64), nullable=False)
    detail_no = Column(String(64), nullable=False, unique=True)
    original_order_no = Column(String(64))
    store_code = Column(String(32), nullable=False)
    channel = Column(String(32))
    product_code = Column(String(64))
    sku_code = Column(String(64))
    quantity = Column(Integer)
    actual_amount = Column(Numeric(14, 2))
    cost_price = Column(Numeric(12, 2))
    cost_amount = Column(Numeric(14, 2))
    return_reason = Column(String(256))
    is_abnormal = Column(Boolean, default=False, comment="退货异常标记")
    etl_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DwdInventorySnapshot(Base):
    """清洗后的库存快照"""
    __tablename__ = "dwd_inventory_snapshot"
    __table_args__ = {"schema": "dwd"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_date = Column(Date, nullable=False)
    store_code = Column(String(32), nullable=False)
    product_code = Column(String(64))
    sku_code = Column(String(64), nullable=False)
    color = Column(String(64))
    size = Column(String(32))
    quantity = Column(Integer)
    cost_price = Column(Numeric(12, 2))
    cost_amount = Column(Numeric(14, 2))
    age_days = Column(Integer)
    age_bucket = Column(String(16), comment="0-30/31-60/61-90/91-180/180+")
    is_negative = Column(Boolean, default=False, comment="负库存标记")
    is_cost_missing = Column(Boolean, default=False)
    etl_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DwdFinanceExpense(Base):
    """财务费用明细（金蝶同步或手工补录）"""
    __tablename__ = "dwd_finance_expense"
    __table_args__ = {"schema": "dwd"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    expense_date = Column(Date, nullable=False)
    allocation_start = Column(Date, comment="费用分摊开始日（含）")
    allocation_end = Column(Date, comment="费用分摊结束日（含）")
    store_code = Column(String(32), comment="为空表示公司级费用")
    expense_type = Column(String(32), nullable=False,
                          comment="rent/wages/social_security/platform_fee/utilities/logistics/marketing/other")
    expense_amount = Column(Numeric(14, 2), nullable=False)
    description = Column(String(256))
    data_type = Column(String(16), default="estimate",
                       comment="estimate=预估 actual=财务核准")
    source = Column(String(16), default="manual", comment="manual=手工 api=金蝶")
    month_year = Column(String(7), comment="格式YYYY-MM，月度费用归属")
    created_by = Column(BigInteger, comment="录入人user_id")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DwdFinanceCash(Base):
    """现金/银行余额（手工补录）"""
    __tablename__ = "dwd_finance_cash"
    __table_args__ = {"schema": "dwd"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    record_date = Column(Date, nullable=False)
    account_type = Column(String(16), comment="cash/bank")
    account_name = Column(String(64))
    balance = Column(Numeric(16, 2), nullable=False)
    data_type = Column(String(16), default="actual")
    source = Column(String(16), default="manual")
    created_by = Column(BigInteger)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
