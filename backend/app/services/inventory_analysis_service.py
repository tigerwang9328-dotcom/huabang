"""库存分析统一数据服务 - Web 和 Mobile 共用"""
import logging
from typing import Optional
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.store_whitelist import allowed_inventory_sql_in, allowed_store_sql_in

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
    inventory_in = allowed_inventory_sql_in()
    store_in = allowed_store_sql_in()
    wh_total_r = await db.execute(text(f"""
        SELECT COUNT(*)
        FROM dim.dim_warehouse
        WHERE UPPER(COALESCE(warehouse_code, '')::text) IN {inventory_in}
    """))
    wh_total = wh_total_r.scalar() or 0

    wh_enabled_r = await db.execute(text(f"""
        SELECT COUNT(*)
        FROM dim.dim_warehouse
        WHERE is_enabled = true
          AND UPPER(COALESCE(warehouse_code, '')::text) IN {inventory_in}
    """))
    wh_enabled = wh_enabled_r.scalar() or 0
    wh_disabled = wh_total - wh_enabled

    inv_records_r = await db.execute(text(f"""
        SELECT COUNT(*)
        FROM dwd.v_apparel_inventory_balance
        WHERE UPPER(COALESCE(warehouse_code, '')::text) IN {inventory_in}
    """))
    inv_records = inv_records_r.scalar() or 0

    inv_qty_r = await db.execute(text(f"""
        SELECT COALESCE(SUM(qty), 0)
        FROM dwd.v_apparel_inventory_balance
        WHERE UPPER(COALESCE(warehouse_code, '')::text) IN {inventory_in}
    """))
    total_inv_qty = int(inv_qty_r.scalar() or 0)

    amount_r = await db.execute(text(f"""
        WITH inv_spec AS MATERIALIZED (
            SELECT product_code,
                   COALESCE(BTRIM(color_code::text), '') AS color_code,
                   COALESCE(BTRIM(size_code::text), '') AS size_code,
                   SUM(qty) AS qty
            FROM dwd.v_apparel_inventory_balance
            WHERE UPPER(COALESCE(warehouse_code, '')::text) IN {inventory_in}
            GROUP BY product_code, COALESCE(BTRIM(color_code::text), ''), COALESCE(BTRIM(size_code::text), '')
        ), priced AS (
            SELECT i.product_code,
                   i.color_code,
                   i.size_code,
                   i.qty,
                   sp.standard_purchase_price AS unit_price
            FROM inv_spec i
            LEFT JOIN dim.v_baison_sku_standard_purchase_price sp
              ON sp.product_code = i.product_code
             AND sp.color_code = i.color_code
             AND sp.size_code = i.size_code
        ), sales_window AS (
            SELECT MAX(biz_date) AS end_date, MAX(biz_date) - INTERVAL '6 days' AS start_date
            FROM dwd.dwd_pos_sale_goods
            WHERE store_code IN {store_in}
        ), recent_sales AS (
            SELECT g.product_code, COALESCE(SUM(g.sales_qty), 0) AS sales_qty
            FROM dwd.dwd_pos_sale_goods g
            CROSS JOIN sales_window sw
            WHERE g.store_code IN {store_in}
              AND sw.end_date IS NOT NULL
              AND g.biz_date >= sw.start_date
              AND g.biz_date <= sw.end_date
            GROUP BY g.product_code
        ), age_snapshot AS (
            SELECT COUNT(*) AS snapshot_rows,
                   COALESCE(SUM(
                       GREATEST(a.quantity, 0) * sp.standard_purchase_price
                   ) FILTER (
                       WHERE a.age_days > 90
                         AND sp.standard_purchase_price IS NOT NULL
                   ), 0) AS age_90_plus_amount
            FROM dwd.v_apparel_inventory_snapshot a
            LEFT JOIN dim.v_baison_sku_standard_purchase_price sp
              ON sp.sku_code = a.sku_code
            WHERE UPPER(COALESCE(a.store_code, '')::text) IN {inventory_in}
        )
        SELECT COALESCE(SUM(GREATEST(priced.qty, 0) * priced.unit_price)
                   FILTER (WHERE priced.unit_price IS NOT NULL), 0) AS inventory_amount,
               CASE WHEN MAX(age_snapshot.snapshot_rows) > 0
                    THEN MAX(age_snapshot.age_90_plus_amount)
                    ELSE COALESCE(SUM(CASE WHEN priced.qty > 0 AND COALESCE(recent_sales.sales_qty, 0) <= 0
                                           THEN priced.qty * priced.unit_price ELSE 0 END), 0)
                END AS age_90_plus_amount,
               (SELECT COUNT(*) FROM inv_spec WHERE qty<>0) AS inventory_sku_count,
               COUNT(*) FILTER (WHERE priced.qty>0 AND priced.unit_price IS NOT NULL) AS standard_purchase_price_ready_sku_count,
               COUNT(*) FILTER (WHERE priced.qty>0 AND priced.unit_price IS NULL) AS missing_standard_purchase_price_sku_count,
               COALESCE(SUM(GREATEST(priced.qty, 0)) FILTER (WHERE priced.unit_price IS NULL), 0) AS missing_standard_purchase_price_qty,
               CASE WHEN COALESCE(SUM(GREATEST(priced.qty, 0)), 0) > 0
                    THEN COALESCE(SUM(GREATEST(priced.qty, 0)) FILTER (WHERE priced.unit_price IS NOT NULL), 0)::numeric
                         / SUM(GREATEST(priced.qty, 0))
                    ELSE 0 END AS standard_purchase_price_coverage_rate
        FROM priced
        LEFT JOIN recent_sales ON recent_sales.product_code = priced.product_code
        CROSS JOIN age_snapshot
    """))
    amount_row = amount_r.mappings().first()
    inventory_amount = float(amount_row["inventory_amount"] or 0) if amount_row else 0
    age_90_plus_amount = float(amount_row["age_90_plus_amount"] or 0) if amount_row else 0
    inventory_sku_count = int(amount_row["inventory_sku_count"] or 0) if amount_row else 0
    standard_purchase_price_ready_sku_count = int(
        amount_row["standard_purchase_price_ready_sku_count"] or 0
    ) if amount_row else 0
    missing_standard_purchase_price_sku_count = int(
        amount_row["missing_standard_purchase_price_sku_count"] or 0
    ) if amount_row else 0
    missing_standard_purchase_price_qty = float(
        amount_row["missing_standard_purchase_price_qty"] or 0
    ) if amount_row else 0
    standard_purchase_price_coverage_rate = float(
        amount_row["standard_purchase_price_coverage_rate"] or 0
    ) if amount_row else 0

    warning_counts_r = await db.execute(text("""
        SELECT COUNT(DISTINCT (store_code, COALESCE(sku_code, product_code)))
                   FILTER (WHERE warning_type='stockout') AS out_of_stock,
               COUNT(DISTINCT (store_code, COALESCE(sku_code, product_code)))
                   FILTER (WHERE warning_type IN ('low_motion_high_stock','seasonal','age_180','clearance_return'))
                   AS high_stock
        FROM dm.dm_inventory_warning
        WHERE warning_date=(SELECT MAX(warning_date) FROM dm.dm_inventory_warning)
    """))
    warning_counts = warning_counts_r.mappings().first() or {}
    out_of_stock = int(warning_counts.get("out_of_stock") or 0)
    high_stock = int(warning_counts.get("high_stock") or 0)

    synced_r = await db.execute(text(f"""
        SELECT MAX(synced_at)
        FROM dwd.v_apparel_inventory_balance
        WHERE UPPER(COALESCE(warehouse_code, '')::text) IN {inventory_in}
    """))
    last_sync = synced_r.scalar()

    return {
        "updated_at": str(last_sync) if last_sync else None,
        "summary": {
            "warehouse_count": _value(wh_total),
            "enabled_warehouses": _value(wh_enabled),
            "disabled_warehouses": _value(wh_disabled),
            "inventory_records": _value(inv_records),
            "total_inventory_qty": _value(total_inv_qty),
            "inventory_amount": _value(round(inventory_amount, 2), 2),
            "standard_purchase_price_coverage_rate": _value(
                round(standard_purchase_price_coverage_rate * 100, 1), 1
            ),
            "standard_purchase_price_ready_sku_count": _value(standard_purchase_price_ready_sku_count),
            "missing_standard_purchase_price_sku_count": _value(missing_standard_purchase_price_sku_count),
            "missing_standard_purchase_price_qty": _value(missing_standard_purchase_price_qty),
            "inventory_sku_count": _value(inventory_sku_count),
            "age_90_plus_amount": _value(round(age_90_plus_amount, 2), 2),
            "out_of_stock_sku_count": _value(out_of_stock),
            "high_stock_sku_count": _value(high_stock),
        },
        "pending_fields": [],
    }


async def get_inventory_overview(db: AsyncSession) -> dict:
    """库存总览 - 按仓库汇总"""
    inventory_in = allowed_inventory_sql_in()
    rows = await db.execute(text(f"""
        WITH inv_spec AS (
            SELECT UPPER(COALESCE(i.warehouse_code, '')::text) AS warehouse_code,
                   MAX(i.warehouse_name) AS warehouse_name,
                   i.product_code,
                   COALESCE(BTRIM(i.color_code::text), '') AS color_code,
                   COALESCE(BTRIM(i.size_code::text), '') AS size_code,
                   SUM(i.qty) AS qty,
                   COUNT(*) AS row_count
            FROM dwd.v_apparel_inventory_balance i
            WHERE UPPER(COALESCE(i.warehouse_code, '')::text) IN {inventory_in}
            GROUP BY UPPER(COALESCE(i.warehouse_code, '')::text), i.product_code,
                     COALESCE(BTRIM(i.color_code::text), ''), COALESCE(BTRIM(i.size_code::text), '')
        ), amount_by_wh AS (
            SELECT i.warehouse_code,
                   COALESCE(SUM(i.qty * sp.standard_purchase_price)
                       FILTER (WHERE sp.standard_purchase_price IS NOT NULL), 0) AS inventory_amount
            FROM inv_spec i
            LEFT JOIN dim.v_baison_sku_standard_purchase_price sp
              ON sp.product_code = i.product_code
             AND sp.color_code = i.color_code
             AND sp.size_code = i.size_code
            WHERE i.qty <> 0
            GROUP BY i.warehouse_code
        )
        SELECT UPPER(COALESCE(w.warehouse_code, '')::text) AS warehouse_code,
               COALESCE(MAX(w.warehouse_name), MAX(i.warehouse_name)) AS warehouse_name,
               COALESCE(SUM(i.qty), 0) AS total_qty,
               COUNT(i.product_code) AS sku_count,
               COALESCE(MAX(a.inventory_amount), 0) AS inventory_amount
        FROM dim.dim_warehouse w
        LEFT JOIN inv_spec i ON UPPER(COALESCE(w.warehouse_code, '')::text) = i.warehouse_code
        LEFT JOIN amount_by_wh a ON a.warehouse_code = UPPER(COALESCE(w.warehouse_code, '')::text)
        WHERE UPPER(COALESCE(w.warehouse_code, '')::text) IN {inventory_in}
        GROUP BY UPPER(COALESCE(w.warehouse_code, '')::text)
        ORDER BY total_qty DESC, warehouse_code
    """))
    by_warehouse = [dict(r._mapping) for r in rows]
    for item in by_warehouse:
        item["total_qty"] = int(item["total_qty"]) if item["total_qty"] else 0
        item["sku_count"] = int(item["sku_count"]) if item["sku_count"] else 0
        item["inventory_amount"] = round(float(item["inventory_amount"] or 0), 2)
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
    inventory_in = allowed_inventory_sql_in()
    conds = [f"UPPER(COALESCE(w.warehouse_code, '')::text) IN {inventory_in}"]
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
        text(f"""
            WITH inv_spec AS (
                SELECT UPPER(COALESCE(i.warehouse_code, '')::text) AS warehouse_code,
                       i.product_code,
                       COALESCE(BTRIM(i.color_code::text), '') AS color_code,
                       COALESCE(BTRIM(i.size_code::text), '') AS size_code,
                       SUM(i.qty) AS qty
                FROM dwd.v_apparel_inventory_balance i
                WHERE UPPER(COALESCE(i.warehouse_code, '')::text) IN {inventory_in}
                GROUP BY UPPER(COALESCE(i.warehouse_code, '')::text), i.product_code,
                         COALESCE(BTRIM(i.color_code::text), ''), COALESCE(BTRIM(i.size_code::text), '')
            ), inv_wh AS (
                SELECT warehouse_code,
                       COALESCE(SUM(qty), 0) AS inventory_qty,
                       COUNT(*) AS sku_count
                FROM inv_spec
                GROUP BY warehouse_code
            ), amount_wh AS (
                SELECT i.warehouse_code,
                       COALESCE(SUM(i.qty * sp.standard_purchase_price)
                           FILTER (WHERE sp.standard_purchase_price IS NOT NULL), 0) AS inventory_amount
                FROM inv_spec i
                LEFT JOIN dim.v_baison_sku_standard_purchase_price sp
                  ON sp.product_code = i.product_code
                 AND sp.color_code = i.color_code
                 AND sp.size_code = i.size_code
                WHERE i.qty <> 0
                GROUP BY i.warehouse_code
            )
            SELECT w.id, w.warehouse_code, w.warehouse_name, w.warehouse_nature,
                   w.warehouse_category_name, w.channel_code, w.region_name,
                   w.default_location_code, w.default_location_name,
                   w.status, w.is_enabled, w.source_system, w.synced_at,
                   COALESCE(i.inventory_qty, 0) AS inventory_qty,
                   COALESCE(i.sku_count, 0) AS sku_count,
                   COALESCE(a.inventory_amount, 0) AS inventory_amount
            FROM dim.dim_warehouse w
            LEFT JOIN inv_wh i ON i.warehouse_code = UPPER(COALESCE(w.warehouse_code, '')::text)
            LEFT JOIN amount_wh a ON a.warehouse_code = UPPER(COALESCE(w.warehouse_code, '')::text)
            WHERE {where}
            ORDER BY w.warehouse_code LIMIT :lim OFFSET :off""")
        .params(**params, lim=page_size, off=(page - 1) * page_size)
    )
    items = []
    for r in rows_r:
        d = dict(r._mapping)
        for dt_col in ("synced_at",):
            if d.get(dt_col):
                d[dt_col] = str(d[dt_col])
        d["inventory_qty"] = float(d.get("inventory_qty") or 0)
        d["sku_count"] = int(d.get("sku_count") or 0)
        d["inventory_amount"] = round(float(d.get("inventory_amount") or 0), 2)
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
    inventory_in = allowed_inventory_sql_in()
    conds = [f"UPPER(COALESCE(i.warehouse_code, '')::text) IN {inventory_in}"]
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
    total_r = await db.execute(text(f"SELECT COUNT(*) FROM dwd.v_apparel_inventory_balance i WHERE {where}").params(**params))
    total = total_r.scalar() or 0
    rows_r = await db.execute(
        text(f"""SELECT i.id, i.warehouse_code, i.warehouse_name, i.product_code, i.sku_code,
                        i.barcode, i.goods_name, i.color_name, i.size_name,
                        i.location_name, i.qty, i.lock_qty, i.road_qty, i.available_qty,
                        sp.standard_purchase_price,
                        CASE WHEN sp.standard_purchase_price IS NOT NULL
                             THEN i.qty * sp.standard_purchase_price
                             ELSE NULL
                        END AS inventory_amount,
                        i.source_system, i.synced_at
                 FROM dwd.v_apparel_inventory_balance i
                 LEFT JOIN dim.v_baison_sku_standard_purchase_price sp
                   ON sp.product_code = i.product_code
                  AND sp.color_code = COALESCE(BTRIM(i.color_code::text), '')
                  AND sp.size_code = COALESCE(BTRIM(i.size_code::text), '')
                 WHERE {where}
                 ORDER BY i.warehouse_code, i.product_code
                 LIMIT :lim OFFSET :off""")
        .params(**params, lim=page_size, off=(page - 1) * page_size)
    )
    items = []
    for r in rows_r:
        d = dict(r._mapping)
        for k in ("qty", "lock_qty", "road_qty", "available_qty", "standard_purchase_price", "inventory_amount"):
            if d.get(k) is not None:
                d[k] = float(d[k])
        for dt_col in ("synced_at",):
            if d.get(dt_col):
                d[dt_col] = str(d[dt_col])
        items.append(d)
    return {"items": items, "total": total, "page": page, "page_size": page_size}
