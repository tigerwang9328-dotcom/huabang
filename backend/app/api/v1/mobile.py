"""小程序/移动端标准 API 出口 — 数据与 Web 端完全一致，复用同一 service 层"""
import logging
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.store_whitelist import ALLOWED_INVENTORY_CODES, ALLOWED_STORE_CODES
from app.core.database import get_db
from app.api.v1.deps import get_current_user, require_permission
from app.models.sys import SysUser
from app.services.business_overview_service import get_overview
from app.services.command_center_service import get_command_center_snapshot
from app.services.store_analysis_service import get_store_analysis_summary, get_store_list
from app.services.product_analysis_service import get_product_analysis_summary, get_product_list, get_sku_list
from app.services.inventory_analysis_service import (
    get_inventory_analysis_summary, get_inventory_overview,
    get_warehouse_list, get_inventory_balance_list,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mobile", tags=["小程序移动端"])


@router.get("/command-center")
async def mobile_command_center(
    stat_date: Optional[str] = Query(None),
    current_user: SysUser = Depends(require_permission("dashboard:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """移动经营指挥台 — 直接复用 Web 端统一经营快照。"""
    report_date = date.fromisoformat(stat_date) if stat_date else (
        await db.execute(text("SELECT MAX(report_date) FROM dm.dm_boss_daily_report"))
    ).scalar()
    snapshot = (
        await get_command_center_snapshot(db, report_date)
        if report_date
        else {"available": False, "report_date": None}
    )
    return {"success": True, "data": snapshot}


@router.get("/overview")
async def mobile_overview(
    stat_date: Optional[str] = Query(None),
    current_user: SysUser = Depends(require_permission("dashboard:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """移动端经营概览 — 与 /dashboard/overview 同一 service"""
    data = await get_overview(db, stat_date)
    return {"success": True, "data_date": data["stat_date"], "updated_at": data.get("updated_at"),
            "data": data, "pending_fields": data.get("pending_fields", [])}


@router.get("/store-analysis")
async def mobile_store_analysis(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None, region_name: Optional[str] = None,
    store_type: Optional[str] = None, business_type: Optional[str] = None,
    status: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("dashboard:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """移动端门店分析"""
    summary = await get_store_analysis_summary(db)
    store_data = await get_store_list(db, page, page_size, keyword, region_name, store_type, business_type, status)
    return {"success": True, "data_date": None, "updated_at": summary.get("updated_at"),
            "data": {"summary": summary["summary"], "stores": store_data, "total": store_data["total"]},
            "pending_fields": summary.get("pending_fields", [])}


@router.get("/product-analysis")
async def mobile_product_analysis(
    tab: str = Query("overview", description="overview|products|skus"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None, brand_name: Optional[str] = None,
    category_name: Optional[str] = None, season: Optional[str] = None,
    year: Optional[int] = None, status: Optional[str] = None,
    product_code: Optional[str] = None, color_name: Optional[str] = None,
    size_name: Optional[str] = None, season_name: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("dashboard:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """移动端商品分析"""
    summary = await get_product_analysis_summary(db)
    result = {"summary": summary["summary"]}
    if tab == "products":
        result["products"] = await get_product_list(db, page, page_size, keyword, brand_name, category_name, season, year, status)
    elif tab == "skus":
        result["skus"] = await get_sku_list(db, page, page_size, keyword, product_code, brand_name, color_name, size_name, season_name, status)
    else:
        result["products"] = await get_product_list(db, page, page_size, keyword, brand_name, category_name, season, year, status)
    return {"success": True, "data_date": None, "updated_at": summary.get("updated_at"),
            "data": result, "pending_fields": summary.get("pending_fields", [])}


def _style_sort_sql(mode: str, sort_by: str) -> str:
    if mode == "best":
        return "sales_qty DESC, sales_amount DESC, inventory_qty DESC, product_code"
    if mode == "warning":
        return "inventory_qty ASC, sales_qty DESC, product_code"
    if mode == "slow":
        return "inventory_qty DESC, product_code"
    if sort_by == "inventory_asc":
        return "inventory_qty ASC, sales_qty ASC, product_code"
    if sort_by == "sales_desc":
        return "sales_qty DESC, sales_amount DESC, inventory_qty DESC, product_code"
    if sort_by == "sales_asc":
        return "sales_qty ASC, sales_amount ASC, inventory_qty ASC, product_code"
    if sort_by == "amount_desc":
        return "inventory_amount DESC, inventory_qty DESC, product_code"
    if sort_by == "amount_asc":
        return "inventory_amount ASC, inventory_qty ASC, product_code"
    if sort_by == "turn_desc":
        return "turn_rate DESC, sales_qty DESC, product_code"
    if sort_by == "turn_asc":
        return "turn_rate ASC, sales_qty ASC, product_code"
    if sort_by == "code_asc":
        return "product_code ASC"
    if sort_by == "code_desc":
        return "product_code DESC"
    return "inventory_qty DESC, sales_qty DESC, product_code"


@router.get("/inventory-styles")
async def mobile_inventory_styles(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    keyword: Optional[str] = None,
    mode: str = Query("all", description="all|best|slow"),
    sort_by: str = Query("inventory_desc", description="inventory_desc|sales_desc|turn_desc|code_asc"),
    current_user: SysUser = Depends(require_permission("dashboard:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """移动端库存款式明细：按款式聚合库存，并拼接最近 7 天销售，用于畅销/滞销排序。"""
    mode = mode if mode in {"all", "best", "warning", "slow"} else "all"
    sort_by = sort_by if sort_by in {
        "inventory_desc", "inventory_asc",
        "sales_desc", "sales_asc",
        "amount_desc", "amount_asc",
        "turn_desc", "turn_asc",
        "code_asc", "code_desc",
    } else "inventory_desc"
    kw = f"%{keyword.strip()}%" if keyword and keyword.strip() else ""
    mode_cond = "TRUE"
    if mode == "best":
        mode_cond = "sales_qty > 0"
    elif mode == "warning":
        mode_cond = "inventory_qty <= 0 OR (sales_qty > 0 AND inventory_qty <= sales_qty)"
    elif mode == "slow":
        mode_cond = "inventory_qty > 0 AND sales_qty <= 0"
    order_sql = _style_sort_sql(mode, sort_by)
    params = {
        "inventory_codes": sorted(ALLOWED_INVENTORY_CODES),
        "store_codes": sorted(ALLOWED_STORE_CODES),
        "kw": kw,
        "lim": page_size,
        "off": (page - 1) * page_size,
    }
    base_sql = f"""
        WITH sales_window AS (
            SELECT MAX(biz_date) AS end_date, MAX(biz_date) - INTERVAL '6 days' AS start_date
            FROM dwd.dwd_pos_sale_goods
            WHERE store_code = ANY(:store_codes)
        ), inv AS (
            SELECT b.product_code,
                   COALESCE(SUM(GREATEST(b.qty, 0)), 0) AS inventory_qty,
                   COALESCE(SUM(GREATEST(b.qty, 0) * price.standard_purchase_price)
                       FILTER (WHERE price.standard_purchase_price IS NOT NULL), 0) AS inventory_amount,
                   COALESCE(SUM(GREATEST(b.qty, 0))
                       FILTER (WHERE price.standard_purchase_price IS NULL), 0)
                       AS missing_standard_purchase_price_qty,
                   CASE WHEN SUM(GREATEST(b.qty, 0)) > 0
                        THEN COALESCE(SUM(GREATEST(b.qty, 0))
                            FILTER (WHERE price.standard_purchase_price IS NOT NULL), 0)::numeric
                             / SUM(GREATEST(b.qty, 0))
                        ELSE 0 END AS standard_purchase_price_coverage_rate,
                   COALESCE(SUM(b.available_qty), 0) AS available_qty,
                   COUNT(DISTINCT b.sku_code) FILTER (
                       WHERE b.sku_code IS NOT NULL AND BTRIM(b.sku_code::text) <> ''
                   ) AS sku_count,
                   MAX(b.synced_at) AS last_synced_at
            FROM dwd.v_apparel_inventory_balance b
            LEFT JOIN dim.v_baison_sku_standard_purchase_price price
              ON price.product_code = b.product_code
             AND TRIM(LEADING '-' FROM price.color_code) =
                 TRIM(LEADING '-' FROM COALESCE(BTRIM(b.color_code::text), ''))
             AND price.size_code = COALESCE(BTRIM(b.size_code::text), '')
            WHERE UPPER(COALESCE(b.warehouse_code, '')::text) = ANY(:inventory_codes)
            GROUP BY b.product_code
        ), sales AS (
            SELECT g.product_code,
                   COALESCE(SUM(g.sales_qty), 0) AS sales_qty,
                   COALESCE(SUM(g.sales_amount), 0) AS sales_amount
            FROM dwd.dwd_pos_sale_goods g
            CROSS JOIN sales_window sw
            WHERE g.store_code = ANY(:store_codes)
              AND sw.end_date IS NOT NULL
              AND g.biz_date >= sw.start_date
              AND g.biz_date <= sw.end_date
            GROUP BY g.product_code
        ), base AS (
            SELECT p.product_code,
                   p.product_name,
                   p.brand_name,
                   p.category_name,
                   p.top_category_name,
                   p.year,
                   p.season,
                   p.tag_price,
                   p.market_price,
                   p.status,
                   COALESCE(inv.inventory_qty, 0) AS inventory_qty,
                   COALESCE(inv.inventory_amount, 0) AS inventory_amount,
                   COALESCE(inv.missing_standard_purchase_price_qty, 0)
                       AS missing_standard_purchase_price_qty,
                   COALESCE(inv.standard_purchase_price_coverage_rate, 0)
                       AS standard_purchase_price_coverage_rate,
                   COALESCE(inv.available_qty, 0) AS available_qty,
                   COALESCE(inv.sku_count, 0) AS sku_count,
                   COALESCE(sales.sales_qty, 0) AS sales_qty,
                   COALESCE(sales.sales_amount, 0) AS sales_amount,
                   CASE
                       WHEN COALESCE(inv.inventory_qty, 0) > 0 THEN COALESCE(sales.sales_qty, 0) / inv.inventory_qty
                       WHEN COALESCE(sales.sales_qty, 0) > 0 THEN 99
                       ELSE 0
                   END AS turn_rate,
                   inv.last_synced_at
            FROM dim.dim_product p
            LEFT JOIN inv ON inv.product_code = p.product_code
            LEFT JOIN sales ON sales.product_code = p.product_code
            WHERE (:kw = '' OR p.product_code ILIKE :kw OR p.product_name ILIKE :kw OR p.brand_name ILIKE :kw)
              AND (COALESCE(inv.inventory_qty, 0) > 0 OR COALESCE(sales.sales_qty, 0) > 0)
        )
    """
    total = (await db.execute(text(base_sql + f" SELECT COUNT(*) FROM base WHERE {mode_cond}"), params)).scalar() or 0
    rows = (await db.execute(text(base_sql + f"""
        SELECT *
        FROM base
        WHERE {mode_cond}
        ORDER BY {order_sql}
        LIMIT :lim OFFSET :off
    """), params)).mappings().all()
    items = []
    for row in rows:
        item = dict(row)
        for key in (
            "inventory_qty", "inventory_amount",
            "missing_standard_purchase_price_qty",
            "standard_purchase_price_coverage_rate",
            "available_qty", "sku_count", "sales_qty", "sales_amount", "turn_rate",
        ):
            item[key] = float(item[key] or 0)
        item["inventory_amount_status"] = (
            "estimated"
            if item["missing_standard_purchase_price_qty"] > 0
            else "ready"
        )
        if item["inventory_qty"].is_integer():
            item["inventory_qty"] = int(item["inventory_qty"])
        if item["available_qty"].is_integer():
            item["available_qty"] = int(item["available_qty"])
        if item["sales_qty"].is_integer():
            item["sales_qty"] = int(item["sales_qty"])
        item["sku_count"] = int(item["sku_count"] or 0)
        item["inventory_amount"] = round(float(item["inventory_amount"] or 0), 2)
        item["sales_amount"] = round(float(item["sales_amount"] or 0), 2)
        item["turn_rate"] = round(float(item["turn_rate"] or 0), 4)
        if item.get("last_synced_at"):
            item["last_synced_at"] = str(item["last_synced_at"])
        item["lifecycle_stage"] = "动销" if float(item["sales_qty"] or 0) > 0 else "待动销"
        item["ai_suggestion"] = "关注补货" if float(item["sales_qty"] or 0) > 0 and float(item["inventory_qty"] or 0) <= 0 else (
            "重点清理" if mode == "slow" or (float(item["inventory_qty"] or 0) > 0 and float(item["sales_qty"] or 0) <= 0) else "正常"
        )
        items.append(item)
    return {"success": True, "data": {"items": items, "total": total, "page": page, "page_size": page_size}}


@router.get("/inventory-analysis")
async def mobile_inventory_analysis(
    tab: str = Query("overview", description="overview|balance|warehouses"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None, warehouse_code: Optional[str] = None,
    product_code: Optional[str] = None, color_name: Optional[str] = None,
    size_name: Optional[str] = None, only_positive: Optional[int] = None,
    warehouse_nature: Optional[str] = None, warehouse_category_name: Optional[str] = None,
    region_name: Optional[str] = None, status: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("dashboard:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """移动端库存分析"""
    summary = await get_inventory_analysis_summary(db)
    result = {"summary": summary["summary"]}
    if tab == "balance":
        result["inventory_balance"] = await get_inventory_balance_list(
            db, page, page_size, keyword, warehouse_code, product_code, color_name, size_name, bool(only_positive)
        )
    elif tab == "warehouses":
        result["warehouses"] = await get_warehouse_list(
            db, page, page_size, keyword, warehouse_nature, warehouse_category_name, region_name, status
        )
    else:
        overview_data = await get_inventory_overview(db)
        result["overview"] = overview_data
    return {"success": True, "data_date": None, "updated_at": summary.get("updated_at"),
            "data": result, "pending_fields": summary.get("pending_fields", [])}
