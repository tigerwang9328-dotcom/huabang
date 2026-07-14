"""门店运营中心 - 标准门店维(dim.dim_store)查询接口。

读取标准业务表 dim_store（不返回百胜原始字段、不暴露任何密钥）。
"""
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.store_whitelist import ALLOWED_INVENTORY_CODES, ALLOWED_STORE_CODES
from app.core.database import get_db
from app.core.data_scope import get_data_scope
from app.models.dim import DimStore
from app.models.sys import SysUser
from app.services.sales_metric_service import PAY_DETAIL_SQL

logger = logging.getLogger("store.api")

router = APIRouter(prefix="/store", tags=["门店运营中心"])

_COLS = (
    DimStore.id, DimStore.store_code, DimStore.store_name, DimStore.region_name,
    DimStore.store_type, DimStore.business_type, DimStore.province, DimStore.city,
    DimStore.county, DimStore.address, DimStore.status, DimStore.source_system, DimStore.synced_at,
)


def _parse_date(value: Optional[str], fallback: date) -> date:
    if not value:
        return fallback
    return date.fromisoformat(value[:10])


def _growth_rate(current, previous):
    if previous is None or float(previous) == 0:
        return None
    return round((float(current or 0) - float(previous)) / float(previous), 4)


def _pending_metric(source: str, reason: str) -> dict:
    return {"value": None, "status": "pending_data", "source": source, "reason": reason}


@router.get("/list")
async def list_stores(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None,
    region_name: Optional[str] = None,
    store_type: Optional[str] = None,
    business_type: Optional[str] = None,
    status: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("sales:store:view")),
    db: AsyncSession = Depends(get_db),
):
    """标准门店维分页查询（门店总览）。"""
    try:
        conds = []
        if keyword:
            kw = f"%{keyword.strip()}%"
            conds.append(or_(DimStore.store_code.ilike(kw), DimStore.store_name.ilike(kw)))
        if region_name:
            conds.append(DimStore.region_name == region_name)
        if store_type:
            conds.append(DimStore.store_type == store_type)
        if business_type:
            conds.append(DimStore.business_type == business_type)
        if status:
            conds.append(DimStore.status == status)
        data_scope = await get_data_scope(db, current_user)
        if data_scope.is_limited_store:
            conds.append(DimStore.store_code.in_(data_scope.store_codes or ["__NO_ACCESS__"]))

        total = (await db.execute(select(func.count()).select_from(DimStore).where(*conds))).scalar() or 0
        rows = (await db.execute(
            select(*_COLS).where(*conds).order_by(DimStore.store_code)
            .offset((page - 1) * page_size).limit(page_size)
        )).mappings().all()
        return {"success": True, "data": {"items": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}}
    except Exception:
        logger.exception("store list error")
        return {"success": False, "message": "查询失败，请查看服务日志"}


@router.get("/sales-analysis")
async def store_sales_analysis(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    keyword: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("sales:store:view")),
    db: AsyncSession = Depends(get_db),
):
    """独立门店销售数据：按日期范围汇总门店小票、商品动销和趋势。"""
    try:
        data_scope = await get_data_scope(db, current_user)
        allowed_store_codes = data_scope.store_codes if data_scope.is_limited_store else sorted(ALLOWED_STORE_CODES)
        latest_row = (await db.execute(text("""
            SELECT MAX(biz_date) AS latest_date
            FROM dwd.dwd_pos_ticket
            WHERE store_code = ANY(:store_codes)
              AND COALESCE(is_void, false) = false
              AND COALESCE(is_pending, false) = false
        """), {"store_codes": allowed_store_codes})).mappings().first()
        latest_date = latest_row["latest_date"] if latest_row else None
        if not latest_date:
            return {
                "success": True,
                "data": {
                    "date_range": {"start_date": start_date, "end_date": end_date},
                    "latest_sales_date": None,
                    "updated_at": None,
                    "summary": {},
                    "stores": [],
                    "trend": [],
                },
            }

        sd = _parse_date(start_date, latest_date)
        ed = _parse_date(end_date, latest_date)
        period_days = (ed - sd).days + 1
        prev_ed = sd - timedelta(days=1)
        prev_sd = prev_ed - timedelta(days=period_days - 1)
        week_sd = sd - timedelta(days=7)
        week_ed = ed - timedelta(days=7)
        kw = f"%{keyword.strip()}%" if keyword and keyword.strip() else ""
        params = {"sd": sd, "ed": ed, "store_codes": allowed_store_codes, "kw": kw}
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS dwd.dwd_store_recharge_daily (
                biz_date DATE NOT NULL,
                store_code VARCHAR(64) NOT NULL,
                recharge_amount NUMERIC(16, 2) NOT NULL DEFAULT 0,
                source VARCHAR(64) NOT NULL DEFAULT 'manual',
                note TEXT,
                created_at TIMESTAMP DEFAULT now(),
                updated_at TIMESTAMP DEFAULT now(),
                PRIMARY KEY (biz_date, store_code, source)
            )
        """))

        store_filter = """
            s.store_code = ANY(:store_codes)
            AND (:kw = '' OR s.store_code ILIKE :kw OR s.store_name ILIKE :kw)
        """

        rows = (await db.execute(text(f"""
            WITH stores AS (
                SELECT s.store_code, s.store_name, s.region_name, s.city, s.status
                FROM dim.dim_store s
                WHERE {store_filter}
            ), ticket AS (
                SELECT t.store_code,
                       COUNT(*)::int AS orders,
                       COALESCE(SUM(t.sales_qty), 0) AS sales_qty,
                       COALESCE(SUM(COALESCE(pay.sales_amount, t.sales_amount)), 0) AS sales_amount,
                       COALESCE(SUM(COALESCE(pay.actual_pay_amount, t.actual_pay_amount)), 0) AS actual_pay_amount,
                       COALESCE(SUM(COALESCE(pay.refund_amount, 0)), 0) AS refund_amount,
                       COALESCE(SUM(COALESCE(pay.sales_amount, t.sales_amount)) FILTER (
                           WHERE COALESCE(NULLIF(BTRIM(t.vip_code::text), ''),
                                          NULLIF(BTRIM(t.customer_code::text), '')) IS NOT NULL
                       ), 0) AS vip_sales_amount,
                       COALESCE(SUM(t.standard_amount), 0) AS standard_amount,
                       MAX(t.synced_at) AS last_synced_at
                FROM dwd.dwd_pos_ticket t
                LEFT JOIN ({PAY_DETAIL_SQL}) pay ON pay.ticket_no = t.ticket_no
                WHERE t.biz_date >= CAST(:sd AS date) AND t.biz_date <= CAST(:ed AS date)
                  AND t.store_code = ANY(:store_codes)
                  AND COALESCE(t.is_void, false) = false
                  AND COALESCE(t.is_pending, false) = false
                GROUP BY t.store_code
            ), recharge AS (
                SELECT store_code,
                       COALESCE(SUM(recharge_amount), 0) AS recharge_amount
                FROM dwd.dwd_store_recharge_daily
                WHERE biz_date >= CAST(:sd AS date) AND biz_date <= CAST(:ed AS date)
                  AND store_code = ANY(:store_codes)
                GROUP BY store_code
            ), goods AS (
                SELECT store_code,
                       COUNT(DISTINCT product_code)::int AS product_count,
                       COUNT(DISTINCT sku_code)::int AS sku_count
                FROM dwd.dwd_pos_sale_goods
                WHERE biz_date >= CAST(:sd AS date) AND biz_date <= CAST(:ed AS date)
                  AND store_code = ANY(:store_codes)
                GROUP BY store_code
            ), previous AS (
                SELECT t.store_code,
                       COALESCE(SUM(COALESCE(pay.sales_amount, t.sales_amount)), 0) AS previous_sales_amount
                FROM dwd.dwd_pos_ticket t
                LEFT JOIN ({PAY_DETAIL_SQL}) pay ON pay.ticket_no=t.ticket_no
                WHERE t.biz_date BETWEEN :prev_sd AND :prev_ed
                  AND t.store_code=ANY(:store_codes)
                  AND COALESCE(t.is_void,false)=false AND COALESCE(t.is_pending,false)=false
                GROUP BY t.store_code
            ), gross AS (
                SELECT store_code, COALESCE(SUM(gross_profit),0) gross_profit,
                       BOOL_AND(COALESCE(is_cost_complete,false)) is_cost_complete
                FROM dws.dws_store_daily
                WHERE stat_date BETWEEN :sd AND :ed AND channel='offline'
                  AND store_code=ANY(:store_codes)
                GROUP BY store_code
            ), inventory AS (
                SELECT store_code, COALESCE(SUM(total_cost_amount),0) inventory_amount
                FROM dws.dws_inventory_daily
                WHERE stat_date=(SELECT MAX(stat_date) FROM dws.dws_inventory_daily)
                  AND UPPER(store_code)=ANY(:store_codes)
                GROUP BY store_code
            )
            SELECT stores.store_code,
                   stores.store_name,
                   stores.region_name,
                   stores.city,
                   stores.status,
                   COALESCE(ticket.orders, 0) AS orders,
                   COALESCE(ticket.sales_qty, 0) AS sales_qty,
                   COALESCE(ticket.sales_amount, 0) AS sales_amount,
                   COALESCE(ticket.actual_pay_amount, 0) + COALESCE(recharge.recharge_amount, 0) AS actual_pay_amount,
                   COALESCE(recharge.recharge_amount, 0) AS recharge_amount,
                   COALESCE(ticket.refund_amount, 0) AS refund_amount,
                   COALESCE(ticket.vip_sales_amount, 0) AS vip_sales_amount,
                   COALESCE(previous.previous_sales_amount, 0) AS previous_sales_amount,
                   CASE WHEN COALESCE(previous.previous_sales_amount,0)>0
                        THEN ROUND(((ticket.sales_amount-previous.previous_sales_amount)/previous.previous_sales_amount)::numeric,4)
                        ELSE NULL END AS period_growth,
                   gross.gross_profit,
                   CASE WHEN COALESCE(ticket.sales_amount,0)>0 AND gross.gross_profit IS NOT NULL
                        THEN ROUND((gross.gross_profit/ticket.sales_amount)::numeric,4) END gross_margin,
                   COALESCE(gross.is_cost_complete,false) is_cost_complete,
                   COALESCE(inventory.inventory_amount,0) inventory_amount,
                   COALESCE(ticket.standard_amount, 0) AS standard_amount,
                   CASE WHEN COALESCE(ticket.standard_amount, 0) > 0
                        THEN ROUND((ticket.sales_amount / ticket.standard_amount)::numeric, 4)
                        ELSE 0 END AS discount_rate,
                   CASE WHEN COALESCE(ticket.orders, 0) > 0
                        THEN ROUND((ticket.sales_amount / ticket.orders)::numeric, 2)
                        ELSE 0 END AS customer_average_price,
                   CASE WHEN COALESCE(ticket.orders, 0) > 0
                        THEN ROUND((ticket.sales_qty / ticket.orders)::numeric, 2)
                        ELSE 0 END AS attach_rate,
                   COALESCE(goods.product_count, 0) AS product_count,
                   COALESCE(goods.sku_count, 0) AS sku_count,
                   ticket.last_synced_at
            FROM stores
            LEFT JOIN ticket ON ticket.store_code = stores.store_code
            LEFT JOIN recharge ON recharge.store_code = stores.store_code
            LEFT JOIN goods ON goods.store_code = stores.store_code
            LEFT JOIN previous ON previous.store_code=stores.store_code
            LEFT JOIN gross ON gross.store_code=stores.store_code
            LEFT JOIN inventory ON inventory.store_code=stores.store_code
            ORDER BY sales_amount DESC, stores.store_code
        """), {**params, "prev_sd": prev_sd, "prev_ed": prev_ed})).mappings().all()

        stores = []
        for idx, row in enumerate(rows, 1):
            item = dict(row)
            item["rank"] = idx
            for key in (
                "orders", "sales_qty", "sales_amount", "actual_pay_amount",
                "recharge_amount", "refund_amount", "standard_amount",
                "vip_sales_amount", "previous_sales_amount", "period_growth",
                "gross_profit", "gross_margin", "inventory_amount",
                "discount_rate", "customer_average_price", "attach_rate", "product_count", "sku_count",
            ):
                item[key] = float(item[key] or 0)
            item["orders"] = int(item["orders"])
            item["product_count"] = int(item["product_count"])
            item["sku_count"] = int(item["sku_count"])
            stores.append(item)

        week_rows = (await db.execute(text(f"""
            SELECT t.store_code,
                   COALESCE(SUM(COALESCE(pay.sales_amount, t.sales_amount)), 0) AS sales_amount
            FROM dwd.dwd_pos_ticket t
            LEFT JOIN ({PAY_DETAIL_SQL}) pay ON pay.ticket_no=t.ticket_no
            WHERE t.biz_date BETWEEN :week_sd AND :week_ed
              AND t.store_code=ANY(:store_codes)
              AND COALESCE(t.is_void,false)=false
              AND COALESCE(t.is_pending,false)=false
            GROUP BY t.store_code
        """), {
            "sd": week_sd,
            "ed": week_ed,
            "week_sd": week_sd,
            "week_ed": week_ed,
            "store_codes": allowed_store_codes,
        })).mappings().all()
        week_sales = {row["store_code"]: float(row["sales_amount"] or 0) for row in week_rows}
        for item in stores:
            item["day_over_day_growth"] = (
                item.get("period_growth") if period_days == 1
                else _growth_rate(item.get("sales_amount"), item.get("previous_sales_amount"))
            )
            item["week_over_week_growth"] = _growth_rate(
                item.get("sales_amount"), week_sales.get(item["store_code"])
            )

        trend_rows = (await db.execute(text(f"""
            WITH ticket AS (
                SELECT biz_date,
                       COALESCE(SUM(COALESCE(pay.sales_amount, t.sales_amount)), 0) AS sales_amount,
                       COALESCE(SUM(COALESCE(pay.actual_pay_amount, t.actual_pay_amount)), 0) AS actual_pay_amount,
                       COALESCE(SUM(COALESCE(pay.refund_amount, 0)), 0) AS refund_amount,
                       COUNT(*)::int AS orders,
                       COALESCE(SUM(t.sales_qty), 0) AS sales_qty
                FROM dwd.dwd_pos_ticket t
                LEFT JOIN ({PAY_DETAIL_SQL}) pay ON pay.ticket_no = t.ticket_no
                WHERE t.biz_date >= CAST(:sd AS date) AND t.biz_date <= CAST(:ed AS date)
                  AND t.store_code = ANY(:store_codes)
                  AND COALESCE(t.is_void, false) = false
                  AND COALESCE(t.is_pending, false) = false
                GROUP BY t.biz_date
            ), recharge AS (
                SELECT biz_date, COALESCE(SUM(recharge_amount), 0) AS recharge_amount
                FROM dwd.dwd_store_recharge_daily
                WHERE biz_date >= CAST(:sd AS date) AND biz_date <= CAST(:ed AS date)
                  AND store_code = ANY(:store_codes)
                GROUP BY biz_date
            )
            SELECT ticket.biz_date,
                   ticket.sales_amount,
                   ticket.actual_pay_amount + COALESCE(recharge.recharge_amount, 0) AS actual_pay_amount,
                   COALESCE(recharge.recharge_amount, 0) AS recharge_amount,
                   ticket.refund_amount,
                   ticket.orders,
                   ticket.sales_qty
            FROM ticket
            LEFT JOIN recharge ON recharge.biz_date = ticket.biz_date
            ORDER BY ticket.biz_date
        """), params)).mappings().all()
        trend = [dict(r) for r in trend_rows]
        for r in trend:
            r["biz_date"] = str(r["biz_date"])
            r["sales_amount"] = float(r["sales_amount"] or 0)
            r["actual_pay_amount"] = float(r["actual_pay_amount"] or 0)
            r["recharge_amount"] = float(r["recharge_amount"] or 0)
            r["refund_amount"] = float(r["refund_amount"] or 0)
            r["orders"] = int(r["orders"] or 0)
            r["sales_qty"] = float(r["sales_qty"] or 0)

        product_rows = (await db.execute(text("""
            WITH inventory AS (
                SELECT UPPER(warehouse_code::text) AS store_code, product_code,
                       MAX(goods_name) AS product_name,
                       COALESCE(SUM(qty),0) AS inventory_qty
                FROM dwd.v_apparel_inventory_balance
                WHERE UPPER(warehouse_code::text)=ANY(:store_codes)
                  AND product_code IS NOT NULL
                GROUP BY UPPER(warehouse_code::text), product_code
            ), sales AS (
                SELECT store_code, product_code, MAX(product_name) AS product_name,
                       COALESCE(SUM(sales_qty),0) AS sales_qty,
                       COALESCE(SUM(sales_amount),0) AS sales_amount
                FROM dwd.dwd_pos_sale_goods
                WHERE biz_date BETWEEN :sd AND :ed
                  AND store_code=ANY(:store_codes)
                  AND product_code IS NOT NULL
                GROUP BY store_code, product_code
            )
            SELECT COALESCE(i.store_code,s.store_code) store_code,
                   COALESCE(i.product_code,s.product_code) product_code,
                   COALESCE(NULLIF(s.product_name,''),i.product_name) product_name,
                   COALESCE(s.sales_qty,0) sales_qty,
                   COALESCE(s.sales_amount,0) sales_amount,
                   COALESCE(i.inventory_qty,0) inventory_qty
            FROM inventory i FULL OUTER JOIN sales s
              ON s.store_code=i.store_code AND s.product_code=i.product_code
        """), {"sd": sd, "ed": ed, "store_codes": allowed_store_codes})).mappings().all()
        products = [{
            "store_code": row["store_code"],
            "product_code": row["product_code"],
            "product_name": row["product_name"],
            "sales_qty": float(row["sales_qty"] or 0),
            "sales_amount": float(row["sales_amount"] or 0),
            "inventory_qty": float(row["inventory_qty"] or 0),
        } for row in product_rows]
        top_products = sorted(products, key=lambda item: (item["sales_qty"], item["sales_amount"]), reverse=True)[:8]
        slow_products = sorted(
            (item for item in products if item["inventory_qty"] > 0),
            key=lambda item: (item["sales_qty"], -item["inventory_qty"]),
        )[:8]

        exceptions = [dict(row) for row in (await db.execute(text("""
            SELECT id, exception_type, severity, store_code, product_code, sku_code,
                   description, is_converted_to_task, task_id, generated_at
            FROM dm.dm_exception_audit
            WHERE audit_date=:audit_date
              AND (store_code IS NULL OR store_code=ANY(:store_codes))
            ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'risk' THEN 2 ELSE 3 END,
                     id DESC
            LIMIT 12
        """), {"audit_date": ed, "store_codes": allowed_store_codes})).mappings().all()]

        inventory_freshness = (await db.execute(text("""
            SELECT MAX(synced_at) updated_at
            FROM dwd.v_apparel_inventory_balance
            WHERE UPPER(warehouse_code::text)=ANY(:inventory_codes)
        """), {"inventory_codes": sorted(ALLOWED_INVENTORY_CODES)})).mappings().first()
        inventory_date = (await db.execute(text("""
            SELECT MAX(stat_date) snapshot_date, MAX(etl_at) updated_at
            FROM dws.dws_inventory_daily
            WHERE UPPER(store_code)=ANY(:inventory_codes)
        """), {"inventory_codes": sorted(ALLOWED_INVENTORY_CODES)})).mappings().first()
        member_freshness = (await db.execute(text("""
            SELECT MAX(balance_updated_at) updated_at
            FROM dim.dim_member
            WHERE UPPER(COALESCE(register_store,''))=ANY(:inventory_codes)
        """), {"inventory_codes": sorted(ALLOWED_INVENTORY_CODES)})).mappings().first()

        total_sales = sum(float(x["sales_amount"] or 0) for x in stores)
        total_actual = sum(float(x["actual_pay_amount"] or 0) for x in stores)
        total_recharge = sum(float(x["recharge_amount"] or 0) for x in stores)
        total_refund = sum(float(x["refund_amount"] or 0) for x in stores)
        total_standard = sum(float(x["standard_amount"] or 0) for x in stores)
        total_orders = sum(int(x["orders"] or 0) for x in stores)
        total_qty = sum(float(x["sales_qty"] or 0) for x in stores)
        updated_at = max((x.get("last_synced_at") for x in stores if x.get("last_synced_at")), default=None)

        summary = {
            "total_sales_amount": round(total_sales, 2),
            "total_actual_pay_amount": round(total_actual, 2),
            "total_recharge_amount": round(total_recharge, 2),
            "total_refund_amount": round(total_refund, 2),
            "total_standard_amount": round(total_standard, 2),
            "total_orders": total_orders,
            "total_sales_qty": round(total_qty, 2),
            "customer_average_price": round(total_sales / total_orders, 2) if total_orders else 0,
            "attach_rate": round(total_qty / total_orders, 2) if total_orders else 0,
            "discount_rate": round(total_sales / total_standard, 4) if total_standard else 0,
            "active_stores_count": len([x for x in stores if float(x["sales_amount"] or 0) > 0]),
            "vip_sales_amount": round(sum(float(x.get("vip_sales_amount") or 0) for x in stores), 2),
            "gross_profit": round(sum(float(x.get("gross_profit") or 0) for x in stores), 2),
            "gross_margin": round(
                sum(float(x.get("gross_profit") or 0) for x in stores) / total_sales, 4
            ) if total_sales else 0,
            "inventory_amount": round(sum(float(x.get("inventory_amount") or 0) for x in stores), 2),
            "is_cost_complete": all(bool(x.get("is_cost_complete")) for x in stores if float(x["sales_amount"] or 0) > 0),
        }

        return {
            "success": True,
            "data": {
            "date_range": {"start_date": str(sd), "end_date": str(ed)},
                "comparison_range": {"start_date": str(prev_sd), "end_date": str(prev_ed)},
                "latest_sales_date": str(latest_date),
                "updated_at": str(updated_at) if updated_at else None,
                "source_freshness": {
                    "sales": {"business_date": str(ed), "updated_at": str(updated_at) if updated_at else None},
                    "inventory": {
                        "snapshot_date": str(inventory_date["snapshot_date"]) if inventory_date and inventory_date["snapshot_date"] else None,
                        "updated_at": str((inventory_date and inventory_date["updated_at"]) or (inventory_freshness and inventory_freshness["updated_at"])) if ((inventory_date and inventory_date["updated_at"]) or (inventory_freshness and inventory_freshness["updated_at"])) else None,
                    },
                    "member": {"updated_at": str(member_freshness["updated_at"]) if member_freshness and member_freshness["updated_at"] else None},
                },
                "pending_metrics": {
                    "footfall": _pending_metric("footfall", "客流数据源未接入"),
                    "conversion_count": _pending_metric("crm", "成交人数缺少可靠来源"),
                    "fitting_rate": _pending_metric("fitting", "试穿数据源未接入"),
                    "new_returning_customer": _pending_metric("crm", "新老客识别字段未接入"),
                    "guide_sales": _pending_metric("baison_pos", "导购业绩归属字段未校准"),
                },
                "summary": summary,
                "stores": stores,
                "trend": trend,
                "top_products": top_products,
                "slow_products": slow_products,
                "exceptions": exceptions,
            },
        }
    except Exception:
        logger.exception("store sales analysis error")
        return {"success": False, "message": "查询失败，请查看服务日志"}
