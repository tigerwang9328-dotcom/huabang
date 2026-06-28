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

logger = logging.getLogger("inventory.api")

router = APIRouter(tags=["库存预警中心"])

_WH_COLS = (
    DimWarehouse.id, DimWarehouse.warehouse_code, DimWarehouse.warehouse_name,
    DimWarehouse.warehouse_nature, DimWarehouse.warehouse_category_name, DimWarehouse.channel_code,
    DimWarehouse.region_name, DimWarehouse.default_location_code, DimWarehouse.default_location_name,
    DimWarehouse.status, DimWarehouse.is_enabled, DimWarehouse.source_system, DimWarehouse.synced_at,
)
_WH_PENDING = {"inventory_qty": "待接入", "inventory_amount": "待接入",
               "stock_warning_count": "待接入", "ai_suggestion": "待接入"}


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
    """标准仓库维分页查询（仓库档案）。不返回 raw_data。"""
    try:
        conds = []
        if keyword:
            kw = f"%{keyword.strip()}%"
            conds.append(or_(DimWarehouse.warehouse_code.ilike(kw), DimWarehouse.warehouse_name.ilike(kw),
                             DimWarehouse.region_name.ilike(kw)))
        if warehouse_nature:
            conds.append(DimWarehouse.warehouse_nature == warehouse_nature)
        if warehouse_category_name:
            conds.append(DimWarehouse.warehouse_category_name == warehouse_category_name)
        if region_name:
            conds.append(DimWarehouse.region_name == region_name)
        if status:
            conds.append(DimWarehouse.status == status)
        if source_system:
            conds.append(DimWarehouse.source_system == source_system)

        total = (await db.execute(select(func.count()).select_from(DimWarehouse).where(*conds))).scalar() or 0
        rows = (await db.execute(
            select(*_WH_COLS).where(*conds).order_by(DimWarehouse.warehouse_code)
            .offset((page - 1) * page_size).limit(page_size)
        )).mappings().all()
        items = [{**dict(r), **_WH_PENDING} for r in rows]
        return {"success": True, "data": {"items": items, "total": total, "page": page, "page_size": page_size}}
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


# 库存余额返回字段（不含 raw_data；库存金额本接口无 -> 待接入）
_INV_COLS = (
    DwdInventoryBalance.id, DwdInventoryBalance.warehouse_code, DwdInventoryBalance.warehouse_name,
    DwdInventoryBalance.product_code, DwdInventoryBalance.sku_code, DwdInventoryBalance.barcode,
    DwdInventoryBalance.goods_name, DwdInventoryBalance.color_name, DwdInventoryBalance.size_name,
    DwdInventoryBalance.location_name, DwdInventoryBalance.qty, DwdInventoryBalance.lock_qty,
    DwdInventoryBalance.road_qty, DwdInventoryBalance.available_qty,
    DwdInventoryBalance.source_system, DwdInventoryBalance.synced_at,
)
_INV_PENDING = {"inventory_amount": "待接入", "ai_suggestion": "待接入"}


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
    """标准库存余额分页查询。available_qty = num - lock_num。库存金额待接入（接口无金额）。"""
    try:
        conds = []
        if keyword:
            kw = f"%{keyword.strip()}%"
            conds.append(or_(DwdInventoryBalance.product_code.ilike(kw), DwdInventoryBalance.sku_code.ilike(kw),
                             DwdInventoryBalance.barcode.ilike(kw), DwdInventoryBalance.goods_name.ilike(kw)))
        if warehouse_code:
            conds.append(DwdInventoryBalance.warehouse_code == warehouse_code.strip())
        if product_code:
            conds.append(DwdInventoryBalance.product_code == product_code.strip())
        if color_name:
            conds.append(DwdInventoryBalance.color_name == color_name)
        if size_name:
            conds.append(DwdInventoryBalance.size_name == size_name)
        if only_positive:
            conds.append(DwdInventoryBalance.qty > 0)

        total = (await db.execute(select(func.count()).select_from(DwdInventoryBalance).where(*conds))).scalar() or 0
        rows = (await db.execute(
            select(*_INV_COLS).where(*conds)
            .order_by(DwdInventoryBalance.warehouse_code, DwdInventoryBalance.product_code)
            .offset((page - 1) * page_size).limit(page_size)
        )).mappings().all()
        items = []
        for r in rows:
            d = dict(r)
            for k in ("qty", "lock_qty", "road_qty", "available_qty"):
                if d.get(k) is not None:
                    d[k] = float(d[k])
            items.append({**d, **_INV_PENDING})
        return {"success": True, "data": {"items": items, "total": total, "page": page, "page_size": page_size}}
    except Exception:
        logger.exception("inventory balance list error")
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
