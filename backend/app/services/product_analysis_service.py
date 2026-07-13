"""商品分析统一数据服务 - Web 和 Mobile 共用"""
import logging
from typing import Optional
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _pending(reason: str = "") -> dict:
    return {"value": None, "display": "待接入", "status": "pending_data", "reason": reason}


def _value(val, decimals: int = 0) -> dict:
    if val is None:
        return _pending()
    if isinstance(val, (int, float)):
        return {"value": round(float(val), decimals), "display": str(round(float(val), decimals)), "status": "ready"}
    return {"value": val, "display": str(val), "status": "ready"}


async def get_product_analysis_summary(db: AsyncSession) -> dict:
    """商品分析顶部指标"""
    # 基础计数
    product_total_r = await db.execute(text("SELECT COUNT(*) FROM dim.dim_product"))
    product_total = product_total_r.scalar() or 0

    sku_total_r = await db.execute(text("SELECT COUNT(*) FROM dim.dim_sku"))
    sku_total = sku_total_r.scalar() or 0

    # 条码统计
    barcode_r = await db.execute(text("SELECT COUNT(*) FROM dim.dim_sku WHERE barcode IS NOT NULL AND barcode != ''"))
    sku_with_barcode = barcode_r.scalar() or 0
    sku_no_barcode = sku_total - sku_with_barcode

    # 库存汇总
    inv_qty_r = await db.execute(text("SELECT COALESCE(SUM(qty), 0) FROM dwd.v_apparel_inventory_balance"))
    total_inv_qty = int(inv_qty_r.scalar() or 0)

    synced_r = await db.execute(text("SELECT MAX(synced_at) FROM dim.dim_product"))
    last_sync = synced_r.scalar()

    return {
        "updated_at": str(last_sync) if last_sync else None,
        "summary": {
            "product_count": _value(product_total),
            "sku_count": _value(sku_total),
            "sku_with_barcode": _value(sku_with_barcode),
            "sku_no_barcode": _value(sku_no_barcode),
            "total_inventory_qty": _value(total_inv_qty),
            "inventory_amount": _pending("库存金额待成本数据接入"),
            "last_7_days_sales": _pending("销售明细尚未接入"),
        },
        "pending_fields": [
            {"field": "inventory_amount", "reason": "库存金额待成本数据接入"},
            {"field": "last_7_days_sales", "reason": "销售明细尚未接入"},
        ],
    }


async def get_product_list(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    brand_name: Optional[str] = None,
    category_name: Optional[str] = None,
    season: Optional[str] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
) -> dict:
    """商品主档列表"""
    conds = []
    params = {}
    if keyword:
        kw = f"%{keyword.strip()}%"
        conds.append("(p.product_code ILIKE :kw OR p.product_name ILIKE :kw)")
        params["kw"] = kw
    if brand_name:
        conds.append("p.brand_name = :brand_name")
        params["brand_name"] = brand_name
    if category_name:
        conds.append("p.category_name = :category_name")
        params["category_name"] = category_name
    if season:
        conds.append("p.season = :season")
        params["season"] = season
    if year is not None:
        conds.append("p.year = :year")
        params["year"] = year
    if status:
        conds.append("p.status = :status")
        params["status"] = status

    where = " AND ".join(conds) if conds else "TRUE"
    total_r = await db.execute(text(f"SELECT COUNT(*) FROM dim.dim_product p WHERE {where}").params(**params))
    total = total_r.scalar() or 0
    rows_r = await db.execute(
        text(f"""SELECT p.id, p.product_code, p.product_name, p.category_code, p.category_name,
                        p.brand_name, p.top_category_name, p.year, p.season,
                        p.tag_price, p.market_price, p.supplier_name,
                        p.status, p.source_system, p.synced_at
                 FROM dim.dim_product p WHERE {where}
                 ORDER BY p.product_code LIMIT :lim OFFSET :off""")
        .params(**params, lim=page_size, off=(page - 1) * page_size)
    )
    items = []
    for r in rows_r:
        d = dict(r._mapping)
        for dt_col in ("synced_at",):
            if d.get(dt_col):
                d[dt_col] = str(d[dt_col])
        items.append(d)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def get_sku_list(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    product_code: Optional[str] = None,
    brand_name: Optional[str] = None,
    color_name: Optional[str] = None,
    size_name: Optional[str] = None,
    season_name: Optional[str] = None,
    status: Optional[str] = None,
) -> dict:
    """SKU列表"""
    conds = []
    params = {}
    if keyword:
        kw = f"%{keyword.strip()}%"
        conds.append("(s.sku_code ILIKE :kw OR s.barcode ILIKE :kw OR s.product_code ILIKE :kw OR s.product_name ILIKE :kw)")
        params["kw"] = kw
    if product_code:
        conds.append("s.product_code = :product_code")
        params["product_code"] = product_code.strip()
    if brand_name:
        conds.append("s.brand_name = :brand_name")
        params["brand_name"] = brand_name
    if color_name:
        conds.append("s.color_name = :color_name")
        params["color_name"] = color_name
    if size_name:
        conds.append("s.size_name = :size_name")
        params["size_name"] = size_name
    if season_name:
        conds.append("s.season_name = :season_name")
        params["season_name"] = season_name
    if status:
        conds.append("s.status = :status")
        params["status"] = status
    where = " AND ".join(conds) if conds else "TRUE"
    total_r = await db.execute(text(f"SELECT COUNT(*) FROM dim.dim_sku s WHERE {where}").params(**params))
    total = total_r.scalar() or 0
    rows_r = await db.execute(
        text(f"""SELECT s.id, s.sku_code, s.product_code, s.product_name, s.barcode,
                        s.color_code, s.color_name, s.size_code, s.size_name,
                        s.brand_name, s.season_name, s.tag_price, s.market_price,
                        s.status, s.source_system, s.synced_at
                 FROM dim.dim_sku s WHERE {where}
                 ORDER BY s.sku_code LIMIT :lim OFFSET :off""")
        .params(**params, lim=page_size, off=(page - 1) * page_size)
    )
    items = []
    for r in rows_r:
        d = dict(r._mapping)
        for dt_col in ("synced_at",):
            if d.get(dt_col):
                d[dt_col] = str(d[dt_col])
        items.append(d)
    return {"items": items, "total": total, "page": page, "page_size": page_size}
