"""库存预警中心 - 标准仓库维(dim.dim_warehouse)查询 + 百胜仓库档案同步。

读取标准业务表 dim_warehouse（不返回 raw_data / 任何密钥）。仓库档案≠库存余额，本接口不含库存数量。
"""
import logging
import uuid
import json
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.core.field_permissions import get_user_field_rules
from app.core.standard_purchase_price import mask_standard_purchase_price_fields
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
from app.services.command_center_service import inventory_warning_source_id

logger = logging.getLogger("inventory.api")

router = APIRouter(tags=["库存预警中心"])


async def _apply_standard_price_permission(
    db: AsyncSession, current_user: SysUser, data: dict
) -> dict:
    rules = await get_user_field_rules(db, current_user, "product")
    can_view = bool(
        current_user.is_admin or rules.get("standard_purchase_price") == "none"
    )
    payload = mask_standard_purchase_price_fields(data, can_view)
    payload["permissions"] = {
        "can_view_standard_purchase_price": can_view,
    }
    return payload

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
    current_user: SysUser = Depends(require_permission("inventory:overview:view")),
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
    current_user: SysUser = Depends(require_permission("inventory:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """标准库存余额分页查询。available_qty = num - lock_num，库存金额按 SKU 成本计算。"""
    try:
        data = await get_inventory_balance_list(
            db, page, page_size, keyword, warehouse_code, product_code, color_name, size_name, bool(only_positive)
        )
        for item in data.get("items", []):
            item.update(_INV_PENDING)
        data = await _apply_standard_price_permission(db, current_user, data)
        return {"success": True, "data": data}
    except Exception:
        logger.exception("inventory balance list error")
        return {"success": False, "message": "查询失败，请查看服务日志"}


@router.get("/inventory/summary")
async def inventory_summary(
    current_user: SysUser = Depends(require_permission("inventory:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """库存管理顶部汇总，基于百胜库存余额和 SKU 成本。"""
    try:
        data = await get_inventory_analysis_summary(db)
        data = await _apply_standard_price_permission(db, current_user, data)
        return {"success": True, "updated_at": data.get("updated_at"), "data": data}
    except Exception:
        logger.exception("inventory summary error")
        return {"success": False, "message": "查询失败，请查看服务日志"}


@router.get("/inventory/overview")
async def inventory_overview(
    current_user: SysUser = Depends(require_permission("inventory:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """库存管理仓库总览，按 7 店 + 3 仓白名单汇总。"""
    try:
        data = await get_inventory_overview(db)
        data = await _apply_standard_price_permission(db, current_user, data)
        return {"success": True, "data": data}
    except Exception:
        logger.exception("inventory overview error")
        return {"success": False, "message": "查询失败，请查看服务日志"}


@router.get("/inventory/warnings")
async def list_inventory_warnings(
    warning_date: Optional[date] = None,
    store_code: Optional[str] = None,
    warning_type: Optional[str] = None,
    warning_level: Optional[str] = None,
    task_status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: SysUser = Depends(require_permission("inventory:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """真实库存预警明细，支持按日期、仓店、类型、等级和任务状态下钻。"""
    query_date = warning_date or (
        await db.execute(text("SELECT MAX(warning_date) FROM dm.dm_inventory_warning"))
    ).scalar()
    if not query_date:
        data = await _apply_standard_price_permission(
            db, current_user,
            {"items": [], "total": 0, "page": page, "page_size": page_size},
        )
        return {"success": True, "data": data}
    conditions = ["w.warning_date=:warning_date"]
    params = {"warning_date": query_date, "limit": page_size, "offset": (page - 1) * page_size}
    if store_code:
        conditions.append("UPPER(w.store_code)=:store_code")
        params["store_code"] = store_code.upper()
    if warning_type:
        conditions.append("w.warning_type=:warning_type")
        params["warning_type"] = warning_type
    if warning_level:
        conditions.append("w.warning_level=:warning_level")
        params["warning_level"] = warning_level
    if task_status == "converted":
        conditions.append("w.is_converted_to_task=true")
    elif task_status == "unconverted":
        conditions.append("COALESCE(w.is_converted_to_task,false)=false")
    where_sql = " AND ".join(conditions)
    total = (await db.execute(text(f"SELECT COUNT(*) FROM dm.dm_inventory_warning w WHERE {where_sql}"), params)).scalar() or 0
    rows = (await db.execute(text(f"""
        SELECT w.id, w.warning_date, w.store_code, COALESCE(s.store_name, wh.warehouse_name, w.store_code) store_name,
               w.product_code, COALESCE(p.product_name, w.product_code) product_name, w.sku_code,
               w.warning_type, w.warning_level, w.current_quantity, w.current_cost_amount,
               w.age_days, w.sellable_days, w.description, w.is_converted_to_task,
               w.task_id, w.rule_id, w.thresholds, w.evidence, w.source_name,
               w.generated_at
        FROM dm.dm_inventory_warning w
        LEFT JOIN dim.dim_store s ON s.store_code=w.store_code AND s.source_system='baison'
        LEFT JOIN dim.dim_warehouse wh ON wh.warehouse_code=w.store_code AND wh.source_system='baison'
        LEFT JOIN dim.dim_product p ON p.product_code=w.product_code AND p.source_system='baison'
        WHERE {where_sql}
        ORDER BY CASE w.warning_level WHEN 'critical' THEN 1 WHEN 'risk' THEN 2 ELSE 3 END,
                 COALESCE(w.current_cost_amount,0) DESC, w.id DESC
        LIMIT :limit OFFSET :offset
    """), params)).mappings().all()
    items = []
    for row in rows:
        item = dict(row)
        item["warning_date"] = str(item["warning_date"])
        item["current_quantity"] = float(item.get("current_quantity") or 0)
        item["current_cost_amount"] = float(item.get("current_cost_amount") or 0)
        item["thresholds"] = item.get("thresholds") or {}
        item["evidence"] = item.get("evidence") or {}
        item["generated_at"] = str(item["generated_at"]) if item.get("generated_at") else None
        items.append(item)
    data = await _apply_standard_price_permission(db, current_user, {
        "items": items,
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "warning_date": str(query_date),
    })
    return {"success": True, "data": data}


@router.post("/inventory/warnings/{warning_id}/task-draft")
async def create_inventory_warning_task_draft(
    warning_id: int,
    current_user: SysUser = Depends(require_permission("task:create")),
    db: AsyncSession = Depends(get_db),
):
    warning = (await db.execute(text("SELECT * FROM dm.dm_inventory_warning WHERE id=:id"), {"id": warning_id})).mappings().first()
    if not warning:
        return {"success": False, "message": "库存预警不存在"}
    source_id = inventory_warning_source_id(
        warning["warning_date"], warning.get("store_code"), warning.get("product_code"),
        warning.get("sku_code"), warning["warning_type"],
    )
    existing = (await db.execute(text("""
        SELECT id, task_no FROM app.app_action_task
        WHERE source_type='inventory_warning' AND source_id=:source_id AND is_deleted=false
        ORDER BY id DESC LIMIT 1
    """), {"source_id": source_id})).mappings().first()
    if existing:
        await db.execute(text("""
            UPDATE dm.dm_inventory_warning SET is_converted_to_task=true, task_id=:task_id WHERE id=:id
        """), {"task_id": existing["id"], "id": warning_id})
        await db.commit()
        return {"success": True, "data": dict(existing), "message": "该预警已有任务草稿"}
    task_no = f"INV-{warning['warning_date'].strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    task_id = (await db.execute(text("""
        INSERT INTO app.app_action_task (
            task_no, title, description, data_evidence_text, suggested_actions,
            feedback_requirement, source_type, source_id, related_store_code,
            related_date, assignee_role, creator_id, status, due_date, is_deleted
        ) VALUES (
            :task_no, :title, :description, :evidence, CAST(:actions AS json),
            '提交处理结果、图片或调拨/清仓记录', 'inventory_warning', :source_id, :store_code,
            :related_date, 'store_manager', :creator_id, 'draft', :due_date, false
        ) RETURNING id
    """), {
        "task_no": task_no,
        "title": f"【库存预警】{warning.get('product_code') or warning.get('sku_code') or '库存异常'}",
        "description": warning.get("description") or "请复核库存预警",
        "evidence": json.dumps({
            "rule_id": warning.get("rule_id"),
            "source_name": warning.get("source_name"),
            "thresholds": warning.get("thresholds") or {},
            "evidence": warning.get("evidence") or {},
            "current_quantity": float(warning.get("current_quantity") or 0),
            "current_cost_amount": float(warning.get("current_cost_amount") or 0),
        }, ensure_ascii=False, default=str),
        "actions": json.dumps(["复核库存、动销和尺码；提交补货、调拨、返仓或清仓处理意见"], ensure_ascii=False),
        "source_id": source_id,
        "store_code": warning.get("store_code"),
        "related_date": warning["warning_date"],
        "creator_id": current_user.id,
        "due_date": date.today() + timedelta(days=3),
    })).scalar_one()
    await db.execute(text("""
        UPDATE dm.dm_inventory_warning SET is_converted_to_task=true, task_id=:task_id WHERE id=:id
    """), {"task_id": task_id, "id": warning_id})
    await db.commit()
    return {"success": True, "data": {"id": task_id, "task_no": task_no}, "message": "任务草稿已创建，等待确认派发"}


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
