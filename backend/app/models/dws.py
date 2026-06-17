"""dws schema: 汇总层"""
from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, BigInteger, Numeric
from sqlalchemy.sql import func
from app.core.database import Base


class DwsStoreDailySales(Base):
    """门店日销售汇总"""
    __tablename__ = "dws_store_daily"
    __table_args__ = {"schema": "dws"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False)
    store_code = Column(String(32), nullable=False)
    channel = Column(String(32), default="offline")

    # 销售核心指标
    order_count = Column(Integer, default=0, comment="订单数")
    item_count = Column(Integer, default=0, comment="销售件数")
    return_count = Column(Integer, default=0, comment="退货件数")
    net_item_count = Column(Integer, default=0, comment="净销售件数")
    tag_amount = Column(Numeric(14, 2), default=0, comment="吊牌金额")
    sales_amount = Column(Numeric(14, 2), default=0, comment="实收金额")
    return_amount = Column(Numeric(14, 2), default=0, comment="退货金额")
    net_sales_amount = Column(Numeric(14, 2), default=0, comment="净销售额")
    cost_amount = Column(Numeric(14, 2), default=0, comment="销售成本")
    gross_profit = Column(Numeric(14, 2), comment="毛利（成本不完整时为null）")
    gross_margin = Column(Numeric(6, 4), comment="毛利率")

    # 衍生指标
    avg_order_value = Column(Numeric(12, 2), comment="客单价")
    items_per_order = Column(Numeric(6, 2), comment="连带率")
    avg_discount_rate = Column(Numeric(6, 4), comment="平均折扣率")
    member_sales_amount = Column(Numeric(14, 2), default=0, comment="会员销售额")
    member_order_count = Column(Integer, default=0, comment="会员订单数")
    member_ratio = Column(Numeric(6, 4), comment="会员销售占比")

    # 标记
    is_cost_complete = Column(Boolean, default=False, comment="成本是否完整")
    etl_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DwsCompanyDaily(Base):
    """公司日汇总（全渠道）"""
    __tablename__ = "dws_company_daily"
    __table_args__ = {"schema": "dws"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False, unique=True)

    total_sales_amount = Column(Numeric(14, 2), default=0, comment="总销售额")
    offline_sales_amount = Column(Numeric(14, 2), default=0, comment="线下销售额")
    online_sales_amount = Column(Numeric(14, 2), default=0, comment="线上销售额")
    online_ratio = Column(Numeric(6, 4), comment="线上占比")
    total_order_count = Column(Integer, default=0)
    total_item_count = Column(Integer, default=0)
    total_return_amount = Column(Numeric(14, 2), default=0)
    net_sales_amount = Column(Numeric(14, 2), default=0)
    total_cost_amount = Column(Numeric(14, 2), default=0)
    gross_profit = Column(Numeric(14, 2))
    gross_margin = Column(Numeric(6, 4))
    avg_order_value = Column(Numeric(12, 2))
    items_per_order = Column(Numeric(6, 2))
    avg_discount_rate = Column(Numeric(6, 4))
    active_store_count = Column(Integer, default=0, comment="有销售门店数")
    is_cost_complete = Column(Boolean, default=False)
    etl_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DwsInventoryDaily(Base):
    """库存日汇总"""
    __tablename__ = "dws_inventory_daily"
    __table_args__ = {"schema": "dws"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False)
    store_code = Column(String(32), nullable=False)

    total_quantity = Column(Integer, default=0, comment="库存总件数")
    total_cost_amount = Column(Numeric(14, 2), default=0, comment="库存总成本")
    age_0_30_amount = Column(Numeric(14, 2), default=0, comment="0-30天库存成本")
    age_31_60_amount = Column(Numeric(14, 2), default=0)
    age_61_90_amount = Column(Numeric(14, 2), default=0)
    age_91_180_amount = Column(Numeric(14, 2), default=0, comment="90天以上库存成本")
    age_180_plus_amount = Column(Numeric(14, 2), default=0, comment="180天以上库存成本")
    negative_sku_count = Column(Integer, default=0, comment="负库存SKU数")
    sku_count = Column(Integer, default=0, comment="在库SKU数")
    is_cost_complete = Column(Boolean, default=False)
    etl_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DwsProductDaily(Base):
    """商品日销售汇总"""
    __tablename__ = "dws_product_daily"
    __table_args__ = {"schema": "dws"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False)
    product_code = Column(String(64), nullable=False)
    store_code = Column(String(32), default="ALL", comment="ALL=全公司汇总")

    sales_quantity = Column(Integer, default=0)
    return_quantity = Column(Integer, default=0)
    net_quantity = Column(Integer, default=0)
    sales_amount = Column(Numeric(14, 2), default=0)
    return_amount = Column(Numeric(14, 2), default=0)
    net_sales_amount = Column(Numeric(14, 2), default=0)
    cost_amount = Column(Numeric(14, 2), default=0)
    gross_profit = Column(Numeric(14, 2))
    gross_margin = Column(Numeric(6, 4))
    avg_discount_rate = Column(Numeric(6, 4))
    is_cost_complete = Column(Boolean, default=False)
    etl_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DwsFinanceDaily(Base):
    """财务日汇总"""
    __tablename__ = "dws_finance_daily"
    __table_args__ = {"schema": "dws"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False)
    store_code = Column(String(32), default="ALL")

    net_sales_amount = Column(Numeric(14, 2), default=0)
    cost_amount = Column(Numeric(14, 2), default=0)
    gross_profit = Column(Numeric(14, 2))
    gross_margin = Column(Numeric(6, 4))
    total_expense = Column(Numeric(14, 2), default=0, comment="已归集费用合计")
    rent_expense = Column(Numeric(14, 2), default=0)
    labor_expense = Column(Numeric(14, 2), default=0)
    utilities_expense = Column(Numeric(14, 2), default=0)
    logistics_expense = Column(Numeric(14, 2), default=0)
    admin_expense = Column(Numeric(14, 2), default=0)
    other_expense = Column(Numeric(14, 2), default=0)
    operating_profit_estimate = Column(Numeric(14, 2), comment="预估经营利润")
    data_type = Column(String(16), default="estimate",
                       comment="estimate=预估 actual=财务核准")
    is_profit_complete = Column(Boolean, default=False)
    etl_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
