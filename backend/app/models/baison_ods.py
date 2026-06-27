"""百胜 API 原始落地层（ODS）模型。

与 Excel 导入链路的 ods.ods_baison_* 区分：本文件是 API 拉取的原始响应落地表（*_api）。
raw_data 保存百胜单条完整原始记录；绝不含 AppSecret / sign。
"""
from sqlalchemy import Column, String, Integer, DateTime, BigInteger, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.core.database import Base


class OdsBaisonProductApi(Base):
    __tablename__ = "ods_baison_product_api"
    __table_args__ = (
        UniqueConstraint("goods_sn", "source_system", name="uq_ods_baison_product_api_sn_source"),
        {"schema": "ods"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64))
    source_system = Column(String(32), nullable=False, server_default="baison")
    api_method = Column(String(64), comment="prm.goods.list_get")
    source_goods_sn = Column(String(64), comment="百胜 goodsSn")
    source_goods_id = Column(String(64), comment="百胜 goods_id")
    goods_sn = Column(String(64), nullable=False)
    goods_name = Column(String(256))
    raw_data = Column(JSONB, comment="百胜单条商品完整原始记录")
    source_hash = Column(String(64), comment="raw_data 的 md5，判断原始记录是否变化")
    created_source_at = Column(String(32), comment="百胜 created 原值")
    modified_source_at = Column(String(32), comment="百胜 modified 原值")
    lastchanged = Column(String(32))
    is_delete = Column(Integer)
    synced_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OdsBaisonSkuApi(Base):
    __tablename__ = "ods_baison_sku_api"
    __table_args__ = (
        UniqueConstraint("sku_code", "source_system", name="uq_ods_baison_sku_api_sku_source"),
        {"schema": "ods"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64))
    source_system = Column(String(32), nullable=False, server_default="baison")
    api_method = Column(String(64), comment="prm.goods.sku_list_get")
    source_goods_sn = Column(String(80), comment="百胜 goodsSn 原值(可能带空格)")
    source_sku = Column(String(120), comment="百胜 sku 原值(可能带空格)")
    goods_sn = Column(String(64), comment="trim 后款号")
    sku_code = Column(String(80), nullable=False, comment="trim 后 SKU 编码")
    barcode = Column(String(64))
    gb_barcode = Column(String(64))
    six_nine_code = Column(String(64))
    raw_data = Column(JSONB, comment="百胜单条 SKU 完整原始记录(保留原始空格)")
    source_hash = Column(String(64))
    created_source_at = Column(String(32))
    modified_source_at = Column(String(32))
    lastchanged = Column(String(64), comment="可能是 System.Byte[]，不可作可靠增量游标")
    synced_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OdsBaisonWarehouseApi(Base):
    __tablename__ = "ods_baison_warehouse_api"
    __table_args__ = (
        UniqueConstraint("warehouse_code", "source_system", name="uq_ods_baison_warehouse_api_code_source"),
        {"schema": "ods"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64))
    source_system = Column(String(32), nullable=False, server_default="baison")
    api_method = Column(String(64), comment="base.warehouse_list_get")
    source_warehouse_code = Column(String(64), comment="百胜 ckdm 原值")
    warehouse_code = Column(String(64), nullable=False, comment="trim 后")
    warehouse_name = Column(String(128))
    raw_data = Column(JSONB, comment="百胜单条仓库完整原始记录")
    source_hash = Column(String(64))
    synced_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OdsBaisonInventoryApi(Base):
    # 百胜实物库存 API 原始落地（barcode 展开后一条码一行）
    __tablename__ = "ods_baison_inventory_api"
    __table_args__ = (
        UniqueConstraint("line_hash", "source_system", name="uq_ods_baison_inventory_api_line_source"),
        {"schema": "ods"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64))
    source_system = Column(String(32), nullable=False, server_default="baison")
    api_method = Column(String(64), comment="stock.goods_sscx")
    line_hash = Column(String(32), nullable=False, comment="md5(store|goods|color|size|barcode)")
    store_code = Column(String(64))
    goods_code = Column(String(64))
    sku = Column(String(80))
    barcode = Column(String(64))
    color_code = Column(String(32))
    size_code = Column(String(32))
    raw_data = Column(JSONB, comment="百胜单条原始库存(含 barcode 数组+shelf)")
    source_hash = Column(String(64))
    synced_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DwdInventoryBalance(Base):
    # 标准库存余额事实表（来源 stock.goods_sscx）。仓库档案≠库存余额。
    __tablename__ = "dwd_inventory_balance"
    __table_args__ = (
        UniqueConstraint("line_hash", "source_system", name="uq_dwd_inventory_balance_line_source"),
        {"schema": "dwd"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64))
    source_system = Column(String(32), nullable=False, server_default="manual")
    line_hash = Column(String(32), nullable=False)
    warehouse_code = Column(String(64), comment="store_code")
    warehouse_name = Column(String(128), comment="ck_name")
    product_code = Column(String(64), comment="goods_code")
    sku_code = Column(String(80), comment="sku")
    barcode = Column(String(64))
    goods_name = Column(String(256))
    color_code = Column(String(32))
    color_name = Column(String(64))
    size_code = Column(String(32))
    size_name = Column(String(32))
    location_name = Column(String(64), comment="kw_name")
    qty = Column(Numeric(16, 4), comment="num 实物库存")
    lock_qty = Column(Numeric(16, 4), comment="lock_num 占用")
    road_qty = Column(Numeric(16, 4), comment="road_num 在途")
    available_qty = Column(Numeric(16, 4), comment="num - lock_num")
    synced_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
