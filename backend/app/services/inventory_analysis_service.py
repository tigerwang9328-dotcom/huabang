"""库存分析统一数据服务 - Web 和 Mobile 共用"""
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


async def get_inventory_analysis_summary(db: AsyncSession) -> dict:
    """库存预警顶部指标"""
    wh_total_r = await db.execute(text("SELECT COUNT(*) FROM dim.dim_warehouse"))
    wh_total = wh_total_r.scalar() or 0

    wh_enabled_r = await db.execute(text("SELECT COUNT(*) FROM dim.dim_warehouse WHERE is_enabled = true"))
    wh_enabled = wh_enabled_r.scalar() or 0
    wh_disabled = wh_total - wh_enabled

    inv_records_r = await db.execute(text("SELECT COUNT(*) FROM dwd.dwd_inventory_balance"))
    inv_records = inv_records_r.scalar() or 0

    inv_qty_r = await db.execute(text("SELECT COALESCE(SUM(qty), 0) FROM dwd.dwd_inventory_balance"))
    total_inv_qty = int(inv_qty_r.scalar() or 0)

    # 缺货(库存=0)和低库存
    zero_r = await db.execute(
        text("SELECT COUNT(*) FROM dwd.dwd_inventory_balance WHERE qty = 0 OR available_qty = 0")
    )
    out_of_stock = zero_r.scalar() or 0

    synced_r = await db.execute(text("SELECT MAX(synced_at) FROM dwd.dwd_inventory_balance"))
    last_sync = synced_r.scalar()

    return {
        "updated_at": str(last_sync) if last_sync else None,
        "summary": {
            "warehouse_count": _value(wh_total),
            "enabled_warehouses": _value(wh_enabled),
            "disabled_warehouses": _value(wh_disabled),
            "inventory_records": _value(inv_records),
            "total_inventory_qty": _value(total_inv_qty),
            "inventory_amount": _pending("库存金额字段待确认"),
            "out_of_stock_sku_count": _value(out_of_stock),
            "high_stock_sku_count": _pending("库存预警规则待配置"),
        },
        "pending_fields": [
            {"field": "inventory_amount", "reason": "库存金额字段待确认"},
            {"field": "high_stock_sku_count", "reason": "库存预警规则待配置"},
        ],
    }


async def get_inventory_overview(db: AsyncSession) -> dict:
    """库存总览 - 按仓库汇总"""
    rows = await db.execute(text("""
        SELECT w.warehouse_code, w.warehouse_name,
               COALESCE(SUM(i.qty), 0) as total_qty,
               COUNT(i.id) as sku_count
        FROM dim.dim_warehouse w
        LEFT JOIN dwd.dwd_inventory_balance i ON w.warehouse_code = i.warehouse_code
        GROUP BY w.warehouse_code, w.warehouse_name
        ORDER BY total_qty DESC
    """))
    by_warehouse = [dict(r._mapping) for r in rows]
    for item in by_warehouse:
        item["total_qty"] = int(item["total_qty"]) if item["total_qty"] else 0
        item["sku_count"] = int(item["sku_count"]) if item["sku_count"] else 0
    return {"by_warehouse": by_warehouse}


async def get_warehouse_list(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    warehouse_nature: Optional[str] = None,
    warehouse_category_name: Optional[str] = None,
    region_name: Optional[str] = None,
    status: Optional[str] = None,
) -> dict:
    """仓库档案列表"""
    conds = []
    params = {}
    if keyword:
        kw = f"%{keyword.strip()}%"
        conds.append("(w.warehouse_code ILIKE :kw OR w.warehouse_name ILIKE :kw OR w.region_name ILIKE :kw)")
        params["kw"] = kw
    if warehouse_nature:
        conds.append("w.warehouse_nature = :wn")
        params["wn"] = warehouse_nature
    if warehouse_category_name:
        conds.append("w.warehouse_category_name = :wcn")
        params["wcn"] = warehouse_category_name
    if region_name:
        conds.append("w.region_name = :rn")
        params["rn"] = region_name
    if status:
        conds.append("w.status = :st")
        params["st"] = status
    where = " AND ".join(conds) if conds else "TRUE"
    total_r = await db.execute(text(f"SELECT COUNT(*) FROM dim.dim_warehouse w WHERE {where}").params(**params))
    total = total_r.scalar() or 0
    rows_r = await db.execute(
        text(f"""SELECT w.id, w.warehouse_code, w.warehouse_name, w.warehouse_nature,
                        w.warehouse_category_name, w.channel_code, w.region_name,
                        w.default_location_code, w.default_location_name,
                        w.status, w.is_enabled, w.source_system, w.synced_at
                 FROM dim.dim_warehouse w WHERE {where}
                 ORDER BY w.warehouse_code LIMIT :lim OFFSET :off""")
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


async def get_inventory_balance_list(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    warehouse_code: Optional[str] = None,
    product_code: Optional[str] = None,
    color_name: Optional[str] = None,
    size_name: Optional[str] = None,
    only_positive: Optional[bool] = None,
) -> dict:
    """库存余额列表"""
    conds = []
    params = {}
    if keyword:
        kw = f"%{keyword.strip()}%"
        conds.append("(i.product_code ILIKE :kw OR i.sku_code ILIKE :kw OR i.barcode ILIKE :kw OR i.goods_name ILIKE :kw)")
        params["kw"] = kw
    if warehouse_code:
        conds.append("i.warehouse_code = :wc")
        params["wc"] = warehouse_code.strip()
    if product_code:
        conds.append("i.product_code = :pc")
        params["pc"] = product_code.strip()
    if color_name:
        conds.append("i.color_name = :cn")
        params["cn"] = color_name
    if size_name:
        conds.append("i.size_name = :sn")
        params["sn"] = size_name
    if only_positive:
        conds.append("i.qty > 0")
    where = " AND ".join(conds) if conds else "TRUE"
    total_r = await db.execute(text(f"SELECT COUNT(*) FROM dwd.dwd_inventory_balance i WHERE {where}").params(**params))
    total = total_r.scalar() or 0
    rows_r = await db.execute(
        text(f"""SELECT i.id, i.warehouse_code, i.warehouse_name, i.product_code, i.sku_code,
                        i.barcode, i.goods_name, i.color_name, i.size_name,
                        i.location_name, i.qty, i.lock_qty, i.road_qty, i.available_qty,
                        i.source_system, i.synced_at
                 FROM dwd.dwd_inventory_balance i WHERE {where}
                 ORDER BY i.warehouse_code, i.product_code
                 LIMIT :lim OFFSET :off""")
        .params(**params, lim=page_size, off=(page - 1) * page_size)
    )
    items = []
    for r in rows_r:
        d = dict(r._mapping)
        for k in ("qty", "lock_qty", "road_qty", "available_qty"):
            if d.get(k) is not None:
                d[k] = float(d[k])
        for dt_col in ("synced_at",):
            if d.get(dt_col):
                d[dt_col] = str(d[dt_col])
        items.append(d)
    return {"items": items, "total": total, "page": page, "page_size": page_size}
