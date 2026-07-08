"""库存预警中心 - 标准仓库维(dim.dim_warehouse)查询 + 百胜仓库档案同步。

读取标准业务表 dim_warehouse（不返回 raw_data / 任何密钥）。仓库档案≠库存余额，本接口不含库存数量。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.integrations.baison.services.warehouse_service import WAREHOUSE_LIST_METHOD, import_all_warehouses, import_warehouse_page
import asyncio as _asyncio
from app.core.database import AsyncSessionLocal
from app.integrations.baison.services.inventory_service import STOCK_METHOD, import_all_inventory
from app.models.baison_ods import DwdInventoryBalance
from app.models.dim import DimWarehouse
from app.models.sys import SysUser
from app.services.inventory_analysis_service import (
    get_inventory_analysis_summary,
    get_inventory_balance_list,
    get_inventory_overview,
    get_warehouse_list,
)

logger = logging.getLogger("inventory.api")

router = APIRouter(tags=["库存预警中心"])

_WH_COLS = (
    DimWarehouse.id, DimWarehouse.warehouse_code, DimWarehouse.warehouse_name,
    DimWarehouse.warehouse_nature, DimWarehouse.warehouse_category_name, DimWarehouse.channel_code,
    DimWarehouse.region_name, DimWarehouse.default_location_code, DimWarehouse.default_location_name,
    DimWarehouse.status, DimWarehouse.is_enabled, DimWarehouse.source_system, DimWarehouse.synced_at,
)
_WH_PENDING = {"stock_warning_count": "待配置", "ai_suggestion": "待配置"}


class WarehouseSyncRequest(BaseModel):
    full_sync: bool = True
    page_size: int = 20
    opt_user_code: str = "000"


@router.get("/inventory/warehouses")
async def list_warehouses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None,
    warehouse_nature: Optional[str] = None,
    warehouse_category_name: Optional[str] = None,
    region_name: Optional[str] = None,
    status: Optional[str] = None,
    source_system: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """标准仓库维分页查询（仓库档案 + 百胜库存汇总）。不返回 raw_data。"""
    try:
        data = await get_warehouse_list(
            db, page, page_size, keyword, warehouse_nature, warehouse_category_name, region_name, status
        )
        for item in data.get("items", []):
            item.update(_WH_PENDING)
        return {"success": True, "data": data}
    except Exception:
        logger.exception("warehouse list error")
        return {"success": False, "message": "查询失败，请查看服务日志"}


@router.post("/sync/baison/warehouses")
async def sync_baison_warehouses(
    req: WarehouseSyncRequest,
    current_user: SysUser = Depends(require_permission("sync:import")),
    db: AsyncSession = Depends(get_db),
):
    """同步百胜仓库档案（base.warehouse_list_get）。仅 59 条/3 页，全量同步直接返回。"""
    try:
        if req.full_sync:
            r = await import_all_warehouses(db, req.page_size, req.opt_user_code)
        else:
            r = await import_warehouse_page(db, 1, req.page_size, req.opt_user_code)
        if not r.get("ok"):
            return {"success": False, "message": "同步失败", "error": r.get("error"), "data": r}
        return {"success": True, "message": "同步完成",
                "data": {"method": WAREHOUSE_LIST_METHOD, "page_count": r.get("page_count"), "record_count": r.get("record_count"),
                         "ods_inserted": r.get("ods_inserted"), "ods_updated": r.get("ods_updated"),
                         "dim_inserted": r.get("dim_inserted"), "dim_updated": r.get("dim_updated"),
                         "skipped": r.get("skipped"), "batch_no": r.get("batch_no")}}
    except Exception:
        logger.exception("warehouse sync error")
        return {"success": False, "message": "内部错误，请查看服务日志"}


# 库存余额返回字段（不含 raw_data）
_INV_COLS = (
    DwdInventoryBalance.id, DwdInventoryBalance.warehouse_code, DwdInventoryBalance.warehouse_name,
    DwdInventoryBalance.product_code, DwdInventoryBalance.sku_code, DwdInventoryBalance.barcode,
    DwdInventoryBalance.goods_name, DwdInventoryBalance.color_name, DwdInventoryBalance.size_name,
    DwdInventoryBalance.location_name, DwdInventoryBalance.qty, DwdInventoryBalance.lock_qty,
    DwdInventoryBalance.road_qty, DwdInventoryBalance.available_qty,
    DwdInventoryBalance.source_system, DwdInventoryBalance.synced_at,
)
_INV_PENDING = {"ai_suggestion": "待配置"}


class InventorySyncRequest(BaseModel):
    full_sync: bool = True
    page_size: int = 20


@router.get("/inventory/balance")
async def list_inventory_balance(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None,
    warehouse_code: Optional[str] = None,
    product_code: Optional[str] = None,
    color_name: Optional[str] = None,
    size_name: Optional[str] = None,
    only_positive: Optional[int] = None,
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """标准库存余额分页查询。available_qty = num - lock_num，库存金额按 SKU 成本计算。"""
    try:
        data = await get_inventory_balance_list(
            db, page, page_size, keyword, warehouse_code, product_code, color_name, size_name, bool(only_positive)
        )
        for item in data.get("items", []):
            item.update(_INV_PENDING)
        return {"success": True, "data": data}
    except Exception:
        logger.exception("inventory balance list error")
        return {"success": False, "message": "查询失败，请查看服务日志"}


@router.get("/inventory/summary")
async def inventory_summary(
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """库存管理顶部汇总，基于百胜库存余额和 SKU 成本。"""
    try:
        data = await get_inventory_analysis_summary(db)
        return {"success": True, "updated_at": data.get("updated_at"), "data": data}
    except Exception:
        logger.exception("inventory summary error")
        return {"success": False, "message": "查询失败，请查看服务日志"}


@router.get("/inventory/overview")
async def inventory_overview(
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """库存管理仓库总览，按 7 店 + 3 仓白名单汇总。"""
    try:
        data = await get_inventory_overview(db)
        return {"success": True, "data": data}
    except Exception:
        logger.exception("inventory overview error")
        return {"success": False, "message": "查询失败，请查看服务日志"}


async def _bg_full_inventory_sync():
    async with AsyncSessionLocal() as bg_db:
        try:
            await import_all_inventory(bg_db, 20)
        except Exception:
            logger.exception("background inventory full sync error")


@router.post("/sync/baison/inventory")
async def sync_baison_inventory(
    req: InventorySyncRequest,
    current_user: SysUser = Depends(require_permission("sync:import")),
    db: AsyncSession = Depends(get_db),
):
    """同步百胜实物库存（stock.goods_sscx，逐店全量）。耗时长 -> 后台任务立即返回。"""
    try:
        if req.full_sync:
            _asyncio.create_task(_bg_full_inventory_sync())
            return {"success": True, "message": "库存余额逐店全量同步已在后台启动，完成后请刷新列表",
                    "data": {"method": STOCK_METHOD, "mode": "background"}}
        r = await import_all_inventory(db, req.page_size, store_limit=3)
        if not r.get("ok"):
            return {"success": False, "message": "同步失败", "error": r.get("error"), "data": r}
        return {"success": True, "message": "同步完成(前3店验证)", "data": r}
    except Exception:
        logger.exception("inventory sync error")
        return {"success": False, "message": "内部错误，请查看服务日志"}
