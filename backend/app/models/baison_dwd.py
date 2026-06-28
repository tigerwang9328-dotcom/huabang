"""百胜 DWD 标准明细模型 - 门店商品销售"""
from sqlalchemy import Column, String, Integer, BigInteger, Numeric, DateTime, Date, Text
from sqlalchemy.sql import func
from app.core.database import Base


class DwdPosSaleGoods(Base):
    __tablename__ = 'dwd_pos_sale_goods'
    __table_args__ = {'schema': 'dwd'}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_system = Column(String(32), default='baison')
    biz_date = Column(Date)
    store_code = Column(String(32), nullable=False)
    product_code = Column(String(64))
    sku_code = Column(String(64))
    product_name = Column(String(256))
    goods_id = Column(String(64))
    category_code = Column(String(32))
    category_name = Column(String(64))
    brand_code = Column(String(32))
    brand_name = Column(String(64))
    outer_product_code = Column(String(64))
    sales_qty = Column(Numeric(12, 4), default=0)
    sales_amount = Column(Numeric(16, 4), default=0)
    standard_amount = Column(Numeric(16, 4), default=0)
    discount_rate = Column(Numeric(8, 4))
    tag_price = Column(Numeric(12, 4))
    stock_qty_snapshot = Column(Numeric(12, 4))
    batch_no = Column(String(32))
    raw_ref_id = Column(BigInteger)
    synced_at = Column(DateTime, default=func.now())
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
