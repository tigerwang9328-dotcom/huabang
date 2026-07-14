"""dim schema: 维度层"""
from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, BigInteger, Numeric, Text, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class DimStore(Base):
    # 华邦AI中台标准门店维表（多数据源统一：source_system=baison/kingdee/manual）
    __tablename__ = "dim_store"
    __table_args__ = (
        UniqueConstraint("store_code", "source_system", name="uq_dim_store_code_source"),
        {"schema": "dim"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    store_code = Column(String(32), nullable=False)
    store_name = Column(String(128), nullable=False)
    region = Column(String(64), comment="兼容旧列，等同 region_name")
    region_code = Column(String(32))
    region_name = Column(String(64))
    province = Column(String(64))
    city = Column(String(64))
    county = Column(String(64))
    channel = Column(String(32), comment="offline/online/other，兼容旧列")
    channel_code = Column(String(32))
    channel_name = Column(String(64))
    store_type = Column(String(32))
    business_type = Column(String(32), comment="线上/线下")
    category_code = Column(String(32))
    category_name = Column(String(64))
    area = Column(Numeric(10, 2))
    open_date = Column(Date)
    status = Column(String(16), default="active", comment="营业/停用/active")
    manager_name = Column(String(64))
    manager_phone = Column(String(20))
    address = Column(String(256))
    sort_order = Column(Integer, default=0)
    source_system = Column(String(32), nullable=False, server_default="manual", comment="数据来源 baison/kingdee/manual")
    source_store_id = Column(String(64), comment="来源系统门店ID")
    source_last_changed = Column(String(32), comment="来源最后变更时间(原值)")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    synced_at = Column(DateTime(timezone=True), comment="最近同步时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DimProduct(Base):
    # 标准商品维表（多数据源：source_system=baison/kingdee/manual）
    __tablename__ = "dim_product"
    __table_args__ = (
        UniqueConstraint("product_code", "source_system", name="uq_dim_product_code_source"),
        {"schema": "dim"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_code = Column(String(64), nullable=False)
    product_name = Column(String(256))
    category_l1 = Column(String(64), comment="兼容旧列")
    category_l2 = Column(String(64), comment="兼容旧列")
    category_l3 = Column(String(64), comment="兼容旧列")
    category_code = Column(String(64))
    category_name = Column(String(128))
    top_category_code = Column(String(32))
    top_category_name = Column(String(64))
    series_code = Column(String(32))
    series_name = Column(String(64))
    brand = Column(String(64), comment="兼容旧列=brand_name")
    brand_code = Column(String(32))
    brand_name = Column(String(64))
    season = Column(String(32))
    season_code = Column(String(32))
    year = Column(Integer)
    supplier_code = Column(String(32))
    supplier_name = Column(String(128))
    tag_price = Column(Numeric(12, 2))
    market_price = Column(Numeric(12, 2))
    cost_price = Column(Numeric(12, 2), comment="敏感字段，前端不展示")
    has_cost = Column(Boolean, default=False, comment="是否有成本价（影响利润可信度）")
    weight = Column(Numeric(12, 4))
    launch_date = Column(Date)
    status = Column(String(16), default="active", comment="active/disabled")
    source_system = Column(String(32), nullable=False, server_default="manual", comment="baison/kingdee/manual")
    source_product_id = Column(String(64))
    source_last_modified = Column(String(32))
    source_last_changed = Column(String(32))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    synced_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DimSku(Base):
    # 标准 SKU 维表（多数据源：source_system=baison/kingdee/manual）
    __tablename__ = "dim_sku"
    __table_args__ = (
        UniqueConstraint("sku_code", "source_system", name="uq_dim_sku_code_source"),
        {"schema": "dim"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sku_code = Column(String(80), nullable=False)
    product_code = Column(String(64), nullable=False)
    product_name = Column(String(256))
    short_name = Column(String(256))
    barcode = Column(String(64))
    gb_barcode = Column(String(64))
    six_nine_code = Column(String(64))
    color = Column(String(64), comment="兼容旧列=color_name")
    color_code = Column(String(32))
    color_name = Column(String(64))
    size = Column(String(32), comment="兼容旧列=size_name")
    size_code = Column(String(32))
    size_name = Column(String(32))
    brand_code = Column(String(32))
    brand_name = Column(String(64))
    category_code = Column(String(64))
    category_name = Column(String(128))
    season_code = Column(String(32))
    season_name = Column(String(32))
    series_code = Column(String(32))
    series_name = Column(String(64))
    tag_price = Column(Numeric(12, 2))
    market_price = Column(Numeric(12, 2))
    cost_price = Column(Numeric(12, 2), comment="ckj/cbj 之一，敏感，前端不展示，含义待确认")
    has_cost = Column(Boolean, default=False)
    weight = Column(Numeric(12, 4))
    remark = Column(String(256))
    status = Column(String(16), default="active", comment="接口未返回状态，默认 active，待百胜确认")
    source_system = Column(String(32), nullable=False, server_default="manual")
    source_created_at = Column(String(32))
    source_modified_at = Column(String(32))
    source_last_changed = Column(String(64), comment="可能 System.Byte[]，不可作增量游标")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    synced_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DimMember(Base):
    __tablename__ = "dim_member"
    __table_args__ = {"schema": "dim"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    member_no = Column(String(64), nullable=False, unique=True)
    member_name = Column(String(64))
    phone = Column(String(20), comment="明文手机号，展示时按权限脱敏")
    gender = Column(String(8))
    birthday = Column(Date)
    register_date = Column(Date)
    register_store = Column(String(32))
    member_level = Column(String(32))
    total_amount = Column(Numeric(14, 2))
    total_count = Column(Integer)
    current_balance = Column(Numeric(14, 2), comment="百胜CZ_DQJE当前储值余额")
    balance_updated_at = Column(DateTime(timezone=True))
    last_consume_date = Column(Date)
    last_consume_store = Column(String(32))
    rfm_score = Column(Numeric(4, 2), comment="RFM综合评分")
    rfm_segment = Column(String(32), comment="会员分层标签")
    status = Column(String(16), default="active")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DimEmployee(Base):
    __tablename__ = "dim_employee"
    __table_args__ = {"schema": "dim"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    employee_id = Column(String(32), nullable=False, unique=True)
    employee_name = Column(String(64))
    store_code = Column(String(32))
    position = Column(String(32))
    phone = Column(String(20))
    status = Column(String(16), default="active")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DimDate(Base):
    """日期维度表（一次性初始化10年数据）"""
    __tablename__ = "dim_date"
    __table_args__ = {"schema": "dim"}

    date_id = Column(Integer, primary_key=True, comment="格式YYYYMMDD")
    date_str = Column(String(10), nullable=False, unique=True, comment="YYYY-MM-DD")
    year = Column(Integer)
    quarter = Column(Integer)
    month = Column(Integer)
    week = Column(Integer)
    day = Column(Integer)
    weekday = Column(Integer, comment="1=周一 7=周日")
    is_weekend = Column(Boolean)
    is_holiday = Column(Boolean, default=False)
    fiscal_year = Column(Integer, comment="财务年度（可配置起始月）")
    fiscal_month = Column(Integer)


class DimBaisonShop(Base):
    # 百胜 E3ERP 店铺档案（base.shop.get_list API 拉取，区别于 Excel 导入的 ods.OdsBaisonStore）
    __tablename__ = "dim_baison_shop"
    __table_args__ = {"schema": "dim"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    shop_id = Column(String(64), comment="sd_id 门店ID")
    shop_code = Column(String(64), nullable=False, unique=True, comment="sd_code 门店代码，唯一键")
    shop_name = Column(String(256), comment="sd_name 门店名称")
    shop_type = Column(String(32), comment="sdxz 门店性质，如直营店")
    online_type = Column(String(32), comment="online_name 线上/线下")
    channel_code = Column(String(32), comment="qddm 渠道代码")
    channel_name = Column(String(64), comment="qdmc 渠道名称")
    category_code = Column(String(32), comment="lbdm 类别代码")
    category_name = Column(String(64), comment="lbmc 类别名称")
    area_code = Column(String(32), comment="qydm 区域代码")
    area_name = Column(String(64), comment="qymc 区域名称")
    province = Column(String(64))
    city = Column(String(64))
    county = Column(String(64))
    address = Column(String(256), comment="dz 地址")
    price_shop_code = Column(String(32), comment="zjf 执价店/价格门店")
    discount_rate = Column(Numeric(10, 4), comment="zk 折扣")
    employee_code = Column(String(32), comment="ygdm 员工代码")
    last_changed = Column(String(32), comment="lastchanged 最后更新时间(百胜原值)")
    is_enabled = Column(String(8), comment="is_qy 是否启用 1/0")
    raw_data = Column(JSONB, comment="百胜返回的原始整行，便于字段追溯")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    synced_at = Column(DateTime(timezone=True), comment="本次同步时间")


class DimWarehouse(Base):
    # 标准仓库维表（多数据源：source_system=baison/kingdee/manual）
    __tablename__ = "dim_warehouse"
    __table_args__ = (
        UniqueConstraint("warehouse_code", "source_system", name="uq_dim_warehouse_code_source"),
        {"schema": "dim"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    warehouse_code = Column(String(64), nullable=False, comment="ckdm")
    warehouse_name = Column(String(128), comment="ckmc")
    channel_code = Column(String(32), comment="qddm")
    region_name = Column(String(64), comment="qy_id_name")
    warehouse_nature = Column(String(32), comment="ckxz 普通/商店")
    warehouse_category_code = Column(String(32), comment="cklb")
    warehouse_category_name = Column(String(64), comment="cklb_name")
    default_location_code = Column(String(32), comment="defaultkwdm")
    default_location_name = Column(String(64), comment="defaultkwmc")
    status = Column(String(16), default="active", comment="ty:0=active/1=disabled，待业务确认")
    is_enabled = Column(Boolean, comment="ty:0=true/1=false")
    source_system = Column(String(32), nullable=False, server_default="manual")
    synced_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
