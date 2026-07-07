"""经营概览统一数据服务 - Web 和 Mobile 共用"""
import logging
import math
from datetime import date, timedelta, datetime
from typing import Optional
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.store_whitelist import (
    ALLOWED_INVENTORY_CODES,
    ALLOWED_STORE_CODES,
    ALLOWED_WAREHOUSE_CODES,
    allowed_inventory_sql_in,
    allowed_store_sql_in,
)

logger = logging.getLogger(__name__)

PENDING = {"value": None, "display": "待接入", "status": "pending_data"}
LOW_STOCK_AVAILABLE_QTY = 0
HIGH_STOCK_QTY = 100


def _pending(reason: str = "") -> dict:
    return {"value": None, "display": "待接入", "status": "pending_data", "reason": reason}


def _value(val, decimals: int = 0) -> dict:
    """已接入的真实值"""
    if val is None:
        return _pending()
    if isinstance(val, (int, float)):
        return {"value": round(float(val), decimals), "display": str(round(float(val), decimals)), "status": "ready"}
    return {"value": val, "display": str(val), "status": "ready"}


def _estimated(val, decimals: int = 0, reason: str = "") -> dict:
    if isinstance(val, (int, float)):
        val = round(float(val), decimals)
    return {"value": val, "display": str(val), "status": "estimated", "reason": reason}


async def get_base_counts(db: AsyncSession) -> dict:
    """获取基础数据资产计数（门店/商品/SKU/仓库/库存记录）"""
    counts = {}
    tables = {
        "product_count": "dim.dim_product",
        "sku_count": "dim.dim_sku",
    }
    for key, tbl in tables.items():
        r = await db.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
        counts[key] = r.scalar() or 0

    store_in = allowed_store_sql_in()
    inventory_in = allowed_inventory_sql_in()
    counts["store_count"] = len(ALLOWED_STORE_CODES)
    counts["warehouse_count"] = len(ALLOWED_WAREHOUSE_CODES)
    counts["inventory_scope_count"] = len(ALLOWED_INVENTORY_CODES)

    inv_count_result = await db.execute(text(f"""
        SELECT COUNT(*)
        FROM dwd.dwd_inventory_balance
        WHERE UPPER(COALESCE(warehouse_code, '')::text) IN {inventory_in}
    """))
    counts["inventory_record_count"] = inv_count_result.scalar() or 0

    active_store_result = await db.execute(text(f"""
        SELECT COUNT(DISTINCT store_code)
        FROM dwd.dwd_pos_ticket
        WHERE COALESCE(store_code, '') IN {store_in}
          AND sales_amount IS NOT NULL
    """))
    counts["active_store_count"] = active_store_result.scalar() or 0
    return counts


async def _table_columns(db: AsyncSession, schema: str, table: str) -> set[str]:
    result = await db.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :table
    """), {"schema": schema, "table": table})
    return {r[0] for r in result.fetchall()}


def _inventory_key_expr(columns: set[str]) -> str:
    """构建库存风险聚合主键，避免 sku_code 全空时风险统计永远为 0。"""
    parts = []
    for col in ("sku_code", "product_code", "goods_id", "barcode"):
        if col in columns:
            parts.append(f"NULLIF(BTRIM({col}::text), '')")
    if "id" in columns:
        parts.append("id::text")
    return "COALESCE(" + ", ".join(parts) + ")" if parts else "NULL"


async def get_overview(db: AsyncSession, stat_date: Optional[str] = None) -> dict:
    """经营概览完整数据"""
    counts = await get_base_counts(db)
    store_in = allowed_store_sql_in()
    inventory_in = allowed_inventory_sql_in()

    # 未指定日期时，使用已落库的最新有效 POS 业务日，
    # 避免每日同步尚未完成时首页误显示为全部“待接入”。
    effective_date = stat_date
    if not effective_date:
        latest_result = await db.execute(text("""
            SELECT COALESCE(
                (SELECT MAX(biz_date) FROM dwd.dwd_pos_ticket WHERE to_regclass('dwd.dwd_pos_ticket') IS NOT NULL AND sales_amount IS NOT NULL),
                (SELECT MAX(biz_date) FROM dwd.dwd_pos_sale_goods WHERE sales_amount IS NOT NULL)
            )
        """))
        latest_date = latest_result.scalar()
        effective_date = str(latest_date or (date.today() - timedelta(days=1)))

    # 数据更新时间
    synced_result = await db.execute(
        select(func.max(text("synced_at"))).select_from(text("dim.dim_product"))
    )
    last_sync = synced_result.scalar()

    data = {
        "stat_date": effective_date,
        "updated_at": str(last_sync) if last_sync else None,

        # 数据资产（真实数据）
        "data_assets": {
            "store_count": _value(counts.get("store_count", 0)),
            "product_count": _value(counts.get("product_count", 0)),
            "sku_count": _value(counts.get("sku_count", 0)),
            "warehouse_count": _value(counts.get("warehouse_count", 0)),
            "inventory_scope_count": _value(counts.get("inventory_scope_count", 0)),
            "inventory_record_count": _value(counts.get("inventory_record_count", 0)),
        },

        # 经营指标（销售/毛利等 — 暂无真实数据）
        "business_metrics": {
            "yesterday_sales": _pending("销售明细尚未接入"),
            "yesterday_sales_e3": _pending("E3销售额尚未接入"),
            "yesterday_sales_pinke": _pending("品氪销售额尚未接入"),
            "yesterday_actual_pay_amount": _pending("实收金额尚未接入"),
            "yesterday_orders": _pending("销售明细尚未接入"),
            "yesterday_items": _pending("销售明细尚未接入"),
            "gross_profit": _pending("成本价待接入"),
            "gross_margin": _pending("成本价待接入"),
            "discount_rate": _pending("销售明细尚未接入"),
            "avg_order_value": _pending("销售明细尚未接入"),
            "items_per_order": _pending("销售明细尚未接入"),
        },

        # 库存风险（部分真实 + 部分待接入）
        "inventory_risk": {
            "total_inventory_qty": _pending("库存金额需等成本数据接入"),
            "inventory_amount": _pending("库存金额字段待确认"),
            "low_stock_sku_count": _pending("库存预警规则待配置"),
            "high_stock_sku_count": _pending("库存预警规则待配置"),
            "no_barcode_sku_count": _pending("条码质量统计待接入"),
            "age_90_plus_amount": _pending("库龄数据未接入"),
        },

        # 任务执行
        "task_execution": {
            "pending_task_count": _value(0),
            "overdue_task_count": _value(0),
            "completed_task_count": _value(0),
        },
    }

    # 库存余额表已落库的可直接计算指标。
    try:
        inv_columns = await _table_columns(db, "dwd", "dwd_inventory_balance")
        inv_key = _inventory_key_expr(inv_columns)
        qty_col = "qty" if "qty" in inv_columns else "0"
        available_col = "available_qty" if "available_qty" in inv_columns else qty_col
        barcode_expr = (
            "barcode IS NULL OR BTRIM(barcode::text) = ''"
            if "barcode" in inv_columns
            else "FALSE"
        )
        inv_result = await db.execute(text("""
            WITH inv AS (
                SELECT {inv_key} AS inv_key,
                       COALESCE(SUM({qty_col}), 0) AS total_qty,
                       COALESCE(SUM({available_col}), 0) AS available_qty,
                       BOOL_OR({barcode_expr}) AS missing_barcode
                FROM dwd.dwd_inventory_balance
                WHERE UPPER(COALESCE(warehouse_code, '')::text) IN {inventory_in}
                GROUP BY {inv_key}
            )
            SELECT COALESCE(SUM(total_qty), 0) AS total_qty,
                   COUNT(*) FILTER (WHERE missing_barcode) AS no_barcode_sku_count,
                   COUNT(*) FILTER (WHERE available_qty <= :low_stock_qty) AS low_stock_sku_count,
                   COUNT(*) FILTER (WHERE total_qty >= :high_stock_qty) AS high_stock_sku_count
            FROM inv
            WHERE inv_key IS NOT NULL
        """.format(
            inv_key=inv_key,
            qty_col=qty_col,
            available_col=available_col,
            barcode_expr=barcode_expr,
            inventory_in=inventory_in,
        )), {
            "low_stock_qty": LOW_STOCK_AVAILABLE_QTY,
            "high_stock_qty": HIGH_STOCK_QTY,
        })
        inv_row = inv_result.mappings().first()
        if inv_row:
            data["inventory_risk"]["total_inventory_qty"] = _value(float(inv_row["total_qty"] or 0))
            data["inventory_risk"]["no_barcode_sku_count"] = _value(int(inv_row["no_barcode_sku_count"] or 0))
            data["inventory_risk"]["low_stock_sku_count"] = _value(int(inv_row["low_stock_sku_count"] or 0))
            data["inventory_risk"]["high_stock_sku_count"] = _value(int(inv_row["high_stock_sku_count"] or 0))

        if "product_code" in inv_columns:
            amount_result = await db.execute(text(f"""
                SELECT COALESCE(SUM(i.qty * COALESCE(sku.cost_price, p.cost_price)), 0) AS inventory_amount,
                       COALESCE(SUM(i.qty) FILTER (
                           WHERE COALESCE(sku.cost_price, p.cost_price) IS NOT NULL
                             AND COALESCE(sku.cost_price, p.cost_price) > 0
                       ), 0) AS costed_qty,
                       COALESCE(SUM(i.qty), 0) AS total_qty
                FROM dwd.dwd_inventory_balance i
                LEFT JOIN dim.dim_sku sku
                  ON sku.product_code = i.product_code
                 AND sku.color_code = i.color_code
                 AND sku.size_code = i.size_code
                 AND COALESCE(sku.source_system, 'baison') = 'baison'
                LEFT JOIN dim.dim_product p
                  ON p.product_code = i.product_code
                 AND COALESCE(p.source_system, 'baison') = 'baison'
                WHERE UPPER(COALESCE(i.warehouse_code, '')::text) IN {inventory_in}
            """))
            amount_row = amount_result.mappings().first()
            if amount_row and float(amount_row["inventory_amount"] or 0) > 0:
                data["inventory_risk"]["inventory_amount"] = _value(
                    round(float(amount_row["inventory_amount"]), 2), 2
                )
    except Exception:
        logger.exception("获取库存实时指标失败，使用待接入占位")

    # 销售核心指标：优先使用 DWS 公司日汇总(老板看板同口径)。
    used_dws_metrics = False
    gross_metrics_ready = False
    try:
        query_date = date.fromisoformat(data["stat_date"])
        dws_result = await db.execute(text("""
            SELECT total_sales_amount, total_order_count, total_item_count,
                   gross_profit, gross_margin, avg_order_value,
                   items_per_order, avg_discount_rate
            FROM dws.dws_company_daily
            WHERE stat_date = :sd
        """), {"sd": query_date})
        dws_row = dws_result.mappings().first()
        if dws_row and float(dws_row["total_sales_amount"] or 0) > 0:
            bm = data["business_metrics"]
            pinke_sales = float(dws_row["total_sales_amount"] or 0)
            total_orders = int(dws_row["total_order_count"] or 0)
            total_items = int(dws_row["total_item_count"] or 0)
            bm["yesterday_sales_pinke"] = _value(round(pinke_sales, 2), 2)
            bm["yesterday_sales"] = bm["yesterday_sales_pinke"]
            bm["yesterday_orders"] = _value(total_orders)
            bm["yesterday_items"] = _value(total_items)
            if dws_row.get("gross_profit") is not None:
                bm["gross_profit"] = _value(round(float(dws_row["gross_profit"]), 2), 2)
            if dws_row.get("gross_margin") is not None:
                bm["gross_margin"] = _value(round(float(dws_row["gross_margin"]) * 100, 1), 1)
            gross_metrics_ready = (
                dws_row.get("gross_profit") is not None
                and dws_row.get("gross_margin") is not None
            )
            if dws_row.get("avg_discount_rate") is not None:
                bm["discount_rate"] = _value(round(float(dws_row["avg_discount_rate"]) * 100, 1), 1)
            if dws_row.get("avg_order_value") is not None:
                bm["avg_order_value"] = _value(round(float(dws_row["avg_order_value"]), 2), 2)
            if dws_row.get("items_per_order") is not None:
                bm["items_per_order"] = _value(round(float(dws_row["items_per_order"]), 2), 2)
            used_dws_metrics = True
    except Exception:
        logger.exception("获取 DWS 公司日汇总失败，回退 DWD 明细口径")

    try:
        query_date = date.fromisoformat(data["stat_date"])
        e3_result = await db.execute(text(f"""
            SELECT COALESCE(SUM(sales_amount), 0) AS e3_sales,
                   COALESCE(SUM(actual_pay_amount), 0) AS actual_pay_amount
            FROM dwd.dwd_pos_ticket
            WHERE biz_date = :sd
              AND COALESCE(is_void, false) = false
              AND COALESCE(is_pending, false) = false
              AND COALESCE(store_code, '') IN {store_in}
        """), {"sd": query_date})
        e3_row = e3_result.mappings().first()
        e3_sales = float(e3_row["e3_sales"] or 0) if e3_row else 0
        actual_pay_amount = float(e3_row["actual_pay_amount"] or 0) if e3_row else 0
        if e3_sales > 0:
            bm = data["business_metrics"]
            bm["yesterday_sales_e3"] = _value(round(e3_sales, 2), 2)
            bm["yesterday_sales"] = bm["yesterday_sales_e3"]
        if actual_pay_amount > 0:
            data["business_metrics"]["yesterday_actual_pay_amount"] = _value(round(actual_pay_amount, 2), 2)
    except Exception:
        logger.exception("获取 E3 销售额失败")

    # DWS 未产出时使用真实小票流水；DWS 已有销售时，仍回补毛利。
    # 首页销售件数/连带率对齐品氪，使用小票头件数；毛利仍按商品明细成本计算。
    reconcile_detail_metrics = True
    if reconcile_detail_metrics:
        try:
            query_date = date.fromisoformat(data["stat_date"])
            ticket_table_result = await db.execute(text("SELECT to_regclass('dwd.dwd_pos_ticket') IS NOT NULL"))
            has_ticket_table = bool(ticket_table_result.scalar())
            row = None
            source = "ticket"

            if has_ticket_table:
                ticket_result = await db.execute(text(f"""
                WITH category_cost AS (
                    SELECT COALESCE(NULLIF(category_name, ''), NULLIF(top_category_name, ''), 'UNKNOWN') AS cat,
                           AVG(cost_price) FILTER (WHERE cost_price IS NOT NULL AND cost_price > 0) AS avg_cost
                    FROM dim.dim_product
                    WHERE COALESCE(source_system, 'baison') = 'baison'
                    GROUP BY 1
                ), ticket AS (
                    SELECT *
                    FROM dwd.dwd_pos_ticket
                    WHERE biz_date = :sd
                      AND COALESCE(store_code, '') IN {store_in}
                      AND COALESCE(is_void, false) = false
                      AND COALESCE(is_pending, false) = false
                ), ticket_agg AS (
                    SELECT COALESCE(SUM(sales_amount),0) AS total_sales,
                           COALESCE(SUM(actual_pay_amount),0) AS actual_pay_amount,
                           COALESCE(SUM(sales_qty),0) AS total_qty,
                           COALESCE(SUM(standard_amount),0) AS total_std,
                           COUNT(*) AS total_orders,
                           CASE WHEN SUM(standard_amount) > 0
                                THEN ROUND(SUM(sales_amount)::numeric / SUM(standard_amount)::numeric, 4)
                                ELSE NULL END AS discount_rate
                    FROM ticket
                ), detail AS (
                    SELECT NULLIF(d.item->>'spdm', '') AS product_code,
                           COALESCE(NULLIF(d.item->>'sl', '')::numeric, 0) AS sales_qty
                    FROM ticket t
                    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(t.raw_data->'orderDetailGets', '[]'::jsonb)) AS d(item)
                ), detail_cost AS (
                    SELECT COALESCE(SUM(detail.sales_qty), 0) AS detail_qty,
                           COALESCE(SUM(detail.sales_qty) FILTER (
                               WHERE p.cost_price IS NOT NULL AND p.cost_price > 0
                           ), 0) AS costed_qty,
                           COALESCE(SUM(detail.sales_qty) FILTER (
                               WHERE (p.cost_price IS NOT NULL AND p.cost_price > 0)
                                  OR (cc.avg_cost IS NOT NULL AND cc.avg_cost > 0)
                           ), 0) AS covered_qty,
                           COALESCE(SUM(detail.sales_qty * COALESCE(NULLIF(p.cost_price, 0), cc.avg_cost)) FILTER (
                               WHERE (p.cost_price IS NOT NULL AND p.cost_price > 0)
                                  OR (cc.avg_cost IS NOT NULL AND cc.avg_cost > 0)
                           ), 0) AS sales_cost
                    FROM detail
                    LEFT JOIN dim.dim_product p
                      ON p.product_code = detail.product_code
                     AND COALESCE(p.source_system, 'baison') = 'baison'
                    LEFT JOIN category_cost cc
                      ON cc.cat = COALESCE(NULLIF(p.category_name, ''), NULLIF(p.top_category_name, ''), 'UNKNOWN')
                )
                SELECT ticket_agg.*, detail_cost.detail_qty, detail_cost.costed_qty,
                       detail_cost.covered_qty, detail_cost.sales_cost
                FROM ticket_agg CROSS JOIN detail_cost
            """), {"sd": query_date})
                row = ticket_result.mappings().first()

            if not row or not row.get("total_sales") or float(row["total_sales"] or 0) <= 0:
                source = "sale_goods_fallback"
                fallback_result = await db.execute(text(f"""
                WITH category_cost AS (
                    SELECT COALESCE(NULLIF(category_name, ''), NULLIF(top_category_name, ''), 'UNKNOWN') AS cat,
                           AVG(cost_price) FILTER (WHERE cost_price IS NOT NULL AND cost_price > 0) AS avg_cost
                    FROM dim.dim_product
                    WHERE COALESCE(source_system, 'baison') = 'baison'
                    GROUP BY 1
                ), sale AS (
                    SELECT s.sales_amount, s.sales_qty, s.standard_amount,
                           p.cost_price, cc.avg_cost AS estimated_cost_price
                    FROM dwd.dwd_pos_sale_goods s
                    LEFT JOIN dim.dim_product p
                      ON p.product_code = s.product_code
                     AND COALESCE(p.source_system, 'baison') = 'baison'
                    LEFT JOIN category_cost cc
                      ON cc.cat = COALESCE(NULLIF(p.category_name, ''), NULLIF(p.top_category_name, ''), 'UNKNOWN')
                    WHERE s.biz_date = :sd
                      AND COALESCE(s.store_code, '') IN {store_in}
                )
                SELECT COALESCE(SUM(sales_amount),0) as total_sales,
                       COALESCE(SUM(sales_qty),0) as total_qty,
                       COALESCE(SUM(standard_amount),0) as total_std,
                       NULL::int as total_orders,
                       COALESCE(SUM(sales_qty) FILTER (WHERE cost_price IS NOT NULL AND cost_price > 0), 0) AS costed_qty,
                       COALESCE(SUM(sales_qty) FILTER (
                           WHERE (cost_price IS NOT NULL AND cost_price > 0)
                              OR (estimated_cost_price IS NOT NULL AND estimated_cost_price > 0)
                       ), 0) AS covered_qty,
                       COALESCE(SUM(sales_qty * COALESCE(NULLIF(cost_price, 0), estimated_cost_price)) FILTER (
                           WHERE (cost_price IS NOT NULL AND cost_price > 0)
                              OR (estimated_cost_price IS NOT NULL AND estimated_cost_price > 0)
                       ), 0) AS sales_cost,
                       CASE WHEN SUM(standard_amount) > 0
                            THEN ROUND(SUM(sales_amount)::numeric / SUM(standard_amount)::numeric, 4)
                            ELSE NULL END as discount_rate
                FROM sale
            """), {"sd": query_date})
                row = fallback_result.mappings().first()

            if row and row.get("total_sales") and float(row["total_sales"] or 0) > 0:
                bm = data["business_metrics"]
                total_sales = float(row["total_sales"] or 0)
                actual_pay_amount = float(row.get("actual_pay_amount") or 0)
                total_qty = float(row["total_qty"] or 0)
                item_qty = total_qty
                total_orders = row.get("total_orders")
                if not used_dws_metrics:
                    bm["yesterday_sales"] = _value(round(total_sales, 2), 2)
                    bm["yesterday_sales_e3"] = bm["yesterday_sales"]
                    if actual_pay_amount > 0:
                        bm["yesterday_actual_pay_amount"] = _value(round(actual_pay_amount, 2), 2)
                    if total_orders is not None and int(total_orders or 0) > 0:
                        order_count = int(total_orders)
                        bm["yesterday_orders"] = _value(order_count)
                        bm["avg_order_value"] = _value(round(total_sales / order_count, 2), 2)
                    elif source == "sale_goods_fallback":
                        bm["yesterday_orders"] = _pending("销售排行接口不包含订单数，需同步小票流水")
                        bm["avg_order_value"] = _pending("销售排行接口不包含订单数，需同步小票流水")
                        bm["items_per_order"] = _pending("销售排行接口不包含订单数，需同步小票流水")
                    if row.get("discount_rate"):
                        bm["discount_rate"] = _value(round(float(row["discount_rate"]) * 100, 1), 1)
                if item_qty >= 0:
                    bm["yesterday_items"] = _value(int(item_qty) if item_qty.is_integer() else round(item_qty, 2), 2)
                    if total_orders is not None and int(total_orders or 0) > 0:
                        items_per_order = math.floor((item_qty / int(total_orders)) * 100) / 100
                        bm["items_per_order"] = _value(items_per_order, 2)

                cost_base_qty = float(row.get("detail_qty") or row.get("total_qty") or 0)
                costed_qty = float(row.get("costed_qty") or 0)
                covered_qty = float(row.get("covered_qty") or 0)
                if cost_base_qty > 0 and covered_qty / cost_base_qty >= 0.95:
                    gross_profit = total_sales - float(row.get("sales_cost") or 0)
                    status_reason = "成本覆盖完整" if costed_qty / cost_base_qty >= 0.95 else "部分商品成本按同品类平均成本估算"
                    setter = _value if costed_qty / cost_base_qty >= 0.95 else _estimated
                    bm["gross_profit"] = setter(round(gross_profit, 2), 2, status_reason) if setter is _estimated else setter(round(gross_profit, 2), 2)
                    gross_margin = round(gross_profit / total_sales * 100, 1) if total_sales else 0
                    bm["gross_margin"] = setter(gross_margin, 1, status_reason) if setter is _estimated else setter(gross_margin, 1)
        except Exception:
            logger.exception("获取 DWD 销售/小票数据失败，使用待接入占位")

    # 尝试获取任务汇总
    try:
        r2 = await db.execute(
            select(
                func.count().filter(text("status IN ('pending', 'processing')")).label("pending"),
                func.count().filter(text("status = 'overdue'")).label("overdue"),
                func.count().filter(text("status IN ('closed', 'review_passed')")).label("completed"),
            ).select_from(text("app.app_action_task")).where(text("is_deleted = false"))
        )
        trow = r2.one()
        if trow.pending is not None:
            data["task_execution"]["pending_task_count"] = _value(trow.pending)
        if trow.overdue is not None:
            data["task_execution"]["overdue_task_count"] = _value(trow.overdue)
        if trow.completed is not None:
            data["task_execution"]["completed_task_count"] = _value(trow.completed)
    except Exception:
        logger.exception("获取任务汇总失败")

    # 构建 pending_fields 列表
    pending_fields = []
    for group_name, group in [
        ("business_metrics", data["business_metrics"]),
        ("inventory_risk", data["inventory_risk"]),
    ]:
        for field_name, field_val in group.items():
            if isinstance(field_val, dict) and field_val.get("status") == "pending_data":
                pending_fields.append({
                    "field": field_name,
                    "group": group_name,
                    "reason": field_val.get("reason", ""),
                })

    data["pending_fields"] = pending_fields
    return data
