"""小程序/移动端标准 API 出口 — 数据与 Web 端完全一致，复用同一 service 层"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.v1.deps import get_current_user, require_permission
from app.models.sys import SysUser
from app.services.business_overview_service import get_overview
from app.services.store_analysis_service import get_store_analysis_summary, get_store_list
from app.services.product_analysis_service import get_product_analysis_summary, get_product_list, get_sku_list
from app.services.inventory_analysis_service import (
    get_inventory_analysis_summary, get_inventory_overview,
    get_warehouse_list, get_inventory_balance_list,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mobile", tags=["小程序移动端"])


@router.get("/overview")
async def mobile_overview(
    stat_date: Optional[str] = Query(None),
    current_user: SysUser = Depends(require_permission("dashboard:view")),
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
    current_user: SysUser = Depends(require_permission("dashboard:view")),
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
    current_user: SysUser = Depends(require_permission("dashboard:view")),
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


@router.get("/inventory-analysis")
async def mobile_inventory_analysis(
    tab: str = Query("overview", description="overview|balance|warehouses"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None, warehouse_code: Optional[str] = None,
    product_code: Optional[str] = None, color_name: Optional[str] = None,
    size_name: Optional[str] = None, only_positive: Optional[int] = None,
    warehouse_nature: Optional[str] = None, warehouse_category_name: Optional[str] = None,
    region_name: Optional[str] = None, status: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("dashboard:view")),
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
