"""ods schema: 百盛ERP原始数据层"""
from sqlalchemy import (
    Column, String, Integer, Boolean, Text, DateTime, BigInteger,
    Numeric, Date, UniqueConstraint, Index
)
from sqlalchemy.sql import func
from app.core.database import Base


class OdsBaisonStore(Base):
    """门店原始数据"""
    __tablename__ = "ods_baison_store"
    __table_args__ = (
        UniqueConstraint("store_code", "batch_no", name="uq_store_batch"),
        {"schema": "ods"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64), nullable=False, comment="导入批次号")
    store_code = Column(String(32), nullable=False, comment="门店编码")
    store_name = Column(String(128), comment="门店名称")
    region = Column(String(64), comment="区域")
    city = Column(String(64), comment="城市")
    channel = Column(String(32), comment="渠道: offline/online/other")
    store_type = Column(String(32), comment="门店类型")
    area = Column(Numeric(10, 2), comment="门店面积m²")
    open_date = Column(Date, comment="开业日期")
    status = Column(String(16), default="active")
    manager_name = Column(String(64), comment="店长姓名")
    manager_phone = Column(String(20), comment="店长手机")
    address = Column(String(256), comment="地址")
    raw_json = Column(Text, comment="原始JSON备份")
    source = Column(String(16), default="excel", comment="excel/api")
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OdsBaisonProduct(Base):
    """商品原始数据"""
    __tablename__ = "ods_baison_product"
    __table_args__ = (
        UniqueConstraint("product_code", "batch_no", name="uq_product_batch"),
        {"schema": "ods"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64), nullable=False)
    product_code = Column(String(64), nullable=False, comment="款号")
    product_name = Column(String(256), comment="商品名称")
    category_l1 = Column(String(64), comment="大类")
    category_l2 = Column(String(64), comment="中类")
    category_l3 = Column(String(64), comment="小类")
    brand = Column(String(64), comment="品牌")
    season = Column(String(32), comment="季节")
    year = Column(Integer, comment="年份")
    tag_price = Column(Numeric(12, 2), comment="吊牌价")
    cost_price = Column(Numeric(12, 2), comment="成本价")
    status = Column(String(16), default="active")
    raw_json = Column(Text)
    source = Column(String(16), default="excel")
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OdsBaisonSku(Base):
    """SKU原始数据"""
    __tablename__ = "ods_baison_sku"
    __table_args__ = (
        UniqueConstraint("sku_code", "batch_no", name="uq_sku_batch"),
        {"schema": "ods"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64), nullable=False)
    sku_code = Column(String(64), nullable=False, comment="SKU编码（条码）")
    product_code = Column(String(64), nullable=False, comment="关联款号")
    color = Column(String(64), comment="颜色")
    size = Column(String(32), comment="尺码")
    barcode = Column(String(64), comment="条形码")
    tag_price = Column(Numeric(12, 2), comment="吊牌价")
    cost_price = Column(Numeric(12, 2), comment="成本价")
    status = Column(String(16), default="active")
    raw_json = Column(Text)
    source = Column(String(16), default="excel")
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OdsBaisonSalesOrder(Base):
    """销售单原始数据"""
    __tablename__ = "ods_baison_sales_order"
    __table_args__ = (
        UniqueConstraint("order_no", "batch_no", name="uq_sales_order_batch"),
        Index("idx_sales_order_date", "order_date"),
        Index("idx_sales_order_store", "store_code"),
        {"schema": "ods"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64), nullable=False)
    order_no = Column(String(64), nullable=False, comment="销售单号")
    order_date = Column(Date, nullable=False, comment="销售日期")
    store_code = Column(String(32), nullable=False, comment="门店编码")
    channel = Column(String(32), comment="渠道: offline/online")
    member_no = Column(String(64), comment="会员编号")
    cashier_id = Column(String(32), comment="收银员ID")
    guide_id = Column(String(32), comment="导购ID")
    tag_amount = Column(Numeric(14, 2), comment="吊牌金额")
    discount_amount = Column(Numeric(14, 2), comment="优惠金额")
    actual_amount = Column(Numeric(14, 2), comment="实收金额")
    item_count = Column(Integer, comment="销售件数")
    pay_type = Column(String(32), comment="支付方式")
    status = Column(String(16), default="normal", comment="normal/returned/voided")
    raw_json = Column(Text)
    source = Column(String(16), default="excel")
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OdsBaisonSalesDetail(Base):
    """销售明细原始数据"""
    __tablename__ = "ods_baison_sales_detail"
    __table_args__ = (
        UniqueConstraint("detail_no", "batch_no", name="uq_sales_detail_batch"),
        Index("idx_sales_detail_order", "order_no"),
        Index("idx_sales_detail_sku", "sku_code"),
        Index("idx_sales_detail_date", "order_date"),
        {"schema": "ods"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64), nullable=False)
    detail_no = Column(String(64), nullable=False, comment="明细编号")
    order_no = Column(String(64), nullable=False, comment="关联销售单号")
    order_date = Column(Date, nullable=False, comment="销售日期")
    store_code = Column(String(32), nullable=False)
    channel = Column(String(32))
    product_code = Column(String(64), comment="款号")
    sku_code = Column(String(64), comment="SKU编码")
    color = Column(String(64))
    size = Column(String(32))
    quantity = Column(Integer, comment="数量")
    tag_price = Column(Numeric(12, 2), comment="吊牌单价")
    actual_price = Column(Numeric(12, 2), comment="实收单价")
    tag_amount = Column(Numeric(14, 2), comment="吊牌金额")
    actual_amount = Column(Numeric(14, 2), comment="实收金额")
    cost_price = Column(Numeric(12, 2), comment="成本价（可能缺失）")
    discount_rate = Column(Numeric(6, 4), comment="折扣率")
    guide_id = Column(String(32), comment="导购ID")
    raw_json = Column(Text)
    source = Column(String(16), default="excel")
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OdsBaisonReturnOrder(Base):
    """退货单原始数据"""
    __tablename__ = "ods_baison_return_order"
    __table_args__ = (
        UniqueConstraint("return_no", "batch_no", name="uq_return_order_batch"),
        Index("idx_return_order_date", "return_date"),
        Index("idx_return_order_store", "store_code"),
        {"schema": "ods"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64), nullable=False)
    return_no = Column(String(64), nullable=False, comment="退货单号")
    return_date = Column(Date, nullable=False, comment="退货日期")
    original_order_no = Column(String(64), comment="原销售单号")
    store_code = Column(String(32), nullable=False)
    channel = Column(String(32))
    member_no = Column(String(64))
    actual_amount = Column(Numeric(14, 2), comment="退款金额")
    item_count = Column(Integer, comment="退货件数")
    return_reason = Column(String(256), comment="退货原因")
    status = Column(String(16), default="normal")
    raw_json = Column(Text)
    source = Column(String(16), default="excel")
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OdsBaisonReturnDetail(Base):
    """退货明细原始数据"""
    __tablename__ = "ods_baison_return_detail"
    __table_args__ = (
        UniqueConstraint("detail_no", "batch_no", name="uq_return_detail_batch"),
        Index("idx_return_detail_date", "return_date"),
        {"schema": "ods"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64), nullable=False)
    detail_no = Column(String(64), nullable=False)
    return_no = Column(String(64), nullable=False)
    return_date = Column(Date, nullable=False)
    store_code = Column(String(32), nullable=False)
    channel = Column(String(32))
    product_code = Column(String(64))
    sku_code = Column(String(64))
    color = Column(String(64))
    size = Column(String(32))
    quantity = Column(Integer)
    actual_price = Column(Numeric(12, 2))
    actual_amount = Column(Numeric(14, 2))
    cost_price = Column(Numeric(12, 2))
    raw_json = Column(Text)
    source = Column(String(16), default="excel")
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OdsBaisonInventory(Base):
    """库存余额原始数据"""
    __tablename__ = "ods_baison_inventory"
    __table_args__ = (
        UniqueConstraint("store_code", "sku_code", "snapshot_date", "batch_no",
                         name="uq_inv_snapshot"),
        Index("idx_inventory_date", "snapshot_date"),
        Index("idx_inventory_store", "store_code"),
        {"schema": "ods"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64), nullable=False)
    snapshot_date = Column(Date, nullable=False, comment="库存快照日期")
    store_code = Column(String(32), nullable=False)
    product_code = Column(String(64))
    sku_code = Column(String(64), nullable=False)
    color = Column(String(64))
    size = Column(String(32))
    quantity = Column(Integer, comment="库存数量")
    cost_price = Column(Numeric(12, 2), comment="成本价")
    cost_amount = Column(Numeric(14, 2), comment="库存成本金额")
    age_days = Column(Integer, comment="库龄天数")
    raw_json = Column(Text)
    source = Column(String(16), default="excel")
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OdsBaisonMember(Base):
    """会员原始数据"""
    __tablename__ = "ods_baison_member"
    __table_args__ = (
        UniqueConstraint("member_no", "batch_no", name="uq_member_batch"),
        Index("idx_member_phone", "phone"),
        {"schema": "ods"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64), nullable=False)
    member_no = Column(String(64), nullable=False, comment="会员编号")
    member_name = Column(String(64), comment="会员姓名")
    phone = Column(String(20), comment="手机号（明文，权限控制展示）")
    gender = Column(String(8), comment="性别")
    birthday = Column(Date, comment="生日")
    register_date = Column(Date, comment="注册日期")
    register_store = Column(String(32), comment="注册门店")
    member_level = Column(String(32), comment="会员等级")
    total_amount = Column(Numeric(14, 2), comment="累计消费金额")
    total_count = Column(Integer, comment="累计消费次数")
    last_consume_date = Column(Date, comment="最后消费日期")
    last_consume_store = Column(String(32), comment="最后消费门店")
    raw_json = Column(Text)
    source = Column(String(16), default="excel")
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OdsBaisonEmployee(Base):
    """导购员工原始数据"""
    __tablename__ = "ods_baison_employee"
    __table_args__ = (
        UniqueConstraint("employee_id", "batch_no", name="uq_employee_batch"),
        {"schema": "ods"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64), nullable=False)
    employee_id = Column(String(32), nullable=False, comment="员工编号")
    employee_name = Column(String(64), comment="姓名")
    store_code = Column(String(32), comment="所在门店")
    position = Column(String(32), comment="职位：guide/manager/etc")
    phone = Column(String(20))
    status = Column(String(16), default="active")
    raw_json = Column(Text)
    source = Column(String(16), default="excel")
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
