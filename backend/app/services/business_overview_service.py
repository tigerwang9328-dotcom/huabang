"""经营概览统一数据服务 - Web 和 Mobile 共用"""
import logging
from datetime import date, timedelta, datetime
from typing import Optional
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PENDING = {"value": None, "display": "待接入", "status": "pending_data"}


def _pending(reason: str = "") -> dict:
    return {"value": None, "display": "待接入", "status": "pending_data", "reason": reason}


def _value(val, decimals: int = 0) -> dict:
    """已接入的真实值"""
    if val is None:
        return _pending()
    if isinstance(val, (int, float)):
        return {"value": round(float(val), decimals), "display": str(round(float(val), decimals)), "status": "ready"}
    return {"value": val, "display": str(val), "status": "ready"}


async def get_base_counts(db: AsyncSession) -> dict:
    """获取基础数据资产计数（门店/商品/SKU/仓库/库存记录）"""
    counts = {}
    tables = {
        "store_count": "dim.dim_store",
        "product_count": "dim.dim_product",
        "sku_count": "dim.dim_sku",
        "warehouse_count": "dim.dim_warehouse",
        "inventory_record_count": "dwd.dwd_inventory_balance",
    }
    for key, tbl in tables.items():
        r = await db.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
        counts[key] = r.scalar() or 0
    return counts


async def get_overview(db: AsyncSession, stat_date: Optional[str] = None) -> dict:
    """经营概览完整数据"""
    counts = await get_base_counts(db)

    # 未指定日期时，使用已落库的最新有效 POS 业务日，
    # 避免每日同步尚未完成时首页误显示为全部“待接入”。
    effective_date = stat_date
    if not effective_date:
        latest_result = await db.execute(text("""
            SELECT MAX(biz_date)
            FROM dwd.dwd_pos_sale_goods
            WHERE sales_amount IS NOT NULL
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
            "inventory_record_count": _value(counts.get("inventory_record_count", 0)),
        },

        # 经营指标（销售/毛利等 — 暂无真实数据）
        "business_metrics": {
            "yesterday_sales": _pending("销售明细尚未接入"),
            "yesterday_orders": _pending("销售明细尚未接入"),
            "yesterday_items": _pending("销售明细尚未接入"),
            "gross_profit": _pending("成本和销售未完整接入"),
            "gross_margin": _pending("成本和销售未完整接入"),
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
        inv_result = await db.execute(text("""
            SELECT COALESCE(SUM(qty), 0) AS total_qty,
                   COUNT(DISTINCT sku_code) FILTER (
                       WHERE barcode IS NULL OR BTRIM(barcode) = ''
                   ) AS no_barcode_sku_count
            FROM dwd.dwd_inventory_balance
        """))
        inv_row = inv_result.mappings().first()
        if inv_row:
            data["inventory_risk"]["total_inventory_qty"] = _value(float(inv_row["total_qty"] or 0))
            data["inventory_risk"]["no_barcode_sku_count"] = _value(int(inv_row["no_barcode_sku_count"] or 0))
    except Exception:
        logger.exception("获取库存实时指标失败，使用待接入占位")

    # 从 DWD 门店商品销售表获取真实销售数据
    try:
        query_date = date.fromisoformat(data["stat_date"])
        r = await db.execute(
            text("""SELECT COALESCE(SUM(sales_amount),0) as total_sales,
                       COALESCE(SUM(sales_qty),0) as total_qty,
                       COALESCE(SUM(standard_amount),0) as total_std,
                       CASE WHEN SUM(standard_amount) > 0 
                            THEN ROUND(SUM(sales_amount)::numeric / SUM(standard_amount)::numeric, 4)
                            ELSE NULL END as discount_rate
                FROM dwd.dwd_pos_sale_goods
                WHERE biz_date = :sd""").params(sd=query_date)
        )
        row = r.mappings().first()
        if row and row.get("total_sales") and float(row["total_sales"]) > 0:
            bm = data["business_metrics"]
            bm["yesterday_sales"] = _value(round(float(row["total_sales"]), 2))
            bm["yesterday_items"] = _value(int(float(row["total_qty"])))
            if row.get("discount_rate"):
                bm["discount_rate"] = _value(round(float(row["discount_rate"]) * 100, 1))
            # 没有订单数，保持待接入
            # 没有毛利，保持待接入
    except Exception:
        logger.exception("获取 DWD 销售数据失败，使用待接入占位")

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
