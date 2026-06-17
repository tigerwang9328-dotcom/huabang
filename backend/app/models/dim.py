"""dim schema: 维度层"""
from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, BigInteger, Numeric, Text
from sqlalchemy.sql import func
from app.core.database import Base


class DimStore(Base):
    __tablename__ = "dim_store"
    __table_args__ = {"schema": "dim"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    store_code = Column(String(32), nullable=False, unique=True)
    store_name = Column(String(128), nullable=False)
    region = Column(String(64))
    city = Column(String(64))
    channel = Column(String(32), comment="offline/online/other")
    store_type = Column(String(32))
    area = Column(Numeric(10, 2))
    open_date = Column(Date)
    status = Column(String(16), default="active")
    manager_name = Column(String(64))
    manager_phone = Column(String(20))
    address = Column(String(256))
    sort_order = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DimProduct(Base):
    __tablename__ = "dim_product"
    __table_args__ = {"schema": "dim"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_code = Column(String(64), nullable=False, unique=True)
    product_name = Column(String(256))
    category_l1 = Column(String(64))
    category_l2 = Column(String(64))
    category_l3 = Column(String(64))
    brand = Column(String(64))
    season = Column(String(32))
    year = Column(Integer)
    tag_price = Column(Numeric(12, 2))
    cost_price = Column(Numeric(12, 2))
    has_cost = Column(Boolean, default=False, comment="是否有成本价（影响利润可信度）")
    status = Column(String(16), default="active")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DimSku(Base):
    __tablename__ = "dim_sku"
    __table_args__ = {"schema": "dim"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sku_code = Column(String(64), nullable=False, unique=True)
    product_code = Column(String(64), nullable=False)
    color = Column(String(64))
    size = Column(String(32))
    barcode = Column(String(64))
    tag_price = Column(Numeric(12, 2))
    cost_price = Column(Numeric(12, 2))
    has_cost = Column(Boolean, default=False)
    status = Column(String(16), default="active")
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
