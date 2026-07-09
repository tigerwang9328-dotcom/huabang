"""百胜 E3ERP 开放平台 API 接口（联调测试 + 店铺档案查询/同步）。

脱敏约束：任何响应/日志都不输出 AppKey/AppSecret/sign 原文；request_params 已脱敏。
"""
import logging
import re
import asyncio as _asyncio
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.database import AsyncSessionLocal, get_db
from app.integrations.baison.client import BaisonClient
from app.integrations.baison.exceptions import BaisonError
from app.integrations.baison.services.inventory_service import STOCK_METHOD, import_all_inventory
from app.integrations.baison.services.pos_sale_goods_service import PosSaleGoodsService
from app.integrations.baison.services.pos_ticket_service import PosTicketService, TICKET_METHOD
from app.integrations.baison.services.product_service import GOODS_LIST_METHOD, import_all_goods, import_goods_page
from app.integrations.baison.services.shop_service import (
    SHOP_LIST_METHOD,
    fetch_shop_list,
    import_all_shops,
    import_shop_page,
)
from app.integrations.baison.services.sku_service import SKU_LIST_METHOD, import_all_skus, import_sku_page
from app.integrations.baison.services.warehouse_service import (
    WAREHOUSE_LIST_METHOD,
    import_all_warehouses,
    import_warehouse_page,
)
from app.models.dim import DimBaisonShop
from app.models.sys import SysUser

logger = logging.getLogger("baison.api")

router = APIRouter(prefix="/integrations/baison", tags=["百胜E3ERP对接"])

_METHOD_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{3,120}$")

BAISON_API_CATALOG = [
    {
        "method": "base.shop.get_list",
        "name": "门店档案列表",
        "module": "基础档案",
        "status": "connected",
        "sync_key": "shop",
        "module_path": "/app/baison/shops",
        "pageable": True,
        "incremental": True,
        "target": "dim.dim_baison_shop",
        "remark": "已支持联调、分页同步与本地查询",
    },
    {
        "method": "base.warehouse.get_list",
        "name": "仓库档案列表",
        "module": "基础档案",
        "status": "connected",
        "sync_key": "warehouse",
        "module_path": "/app/inventory/warehouses",
        "pageable": True,
        "incremental": True,
        "target": "dim/dwd warehouse",
        "remark": "已有服务封装，待纳入统一调度面板",
    },
    {
        "method": GOODS_LIST_METHOD,
        "name": "商品档案列表",
        "module": "商品中心",
        "status": "connected",
        "sync_key": "product",
        "module_path": "/app/product/products",
        "pageable": True,
        "incremental": True,
        "target": "dim/dwd product",
        "remark": "已有服务封装，待纳入统一调度面板",
    },
    {
        "method": SKU_LIST_METHOD,
        "name": "SKU 档案列表",
        "module": "商品中心",
        "status": "connected",
        "sync_key": "sku",
        "module_path": "/app/product/skus",
        "pageable": True,
        "incremental": True,
        "target": "dim/dwd sku",
        "remark": "已有服务封装，待纳入统一调度面板",
    },
    {
        "method": STOCK_METHOD,
        "name": "即时库存列表",
        "module": "库存中心",
        "status": "connected",
        "sync_key": "inventory",
        "module_path": "/app/inventory/balance",
        "pageable": True,
        "incremental": True,
        "target": "dwd.dwd_inventory_balance",
        "remark": "已有服务封装，经营概览已读取库存指标",
    },
    {
        "method": "pos.storefx.sale_goods_get",
        "name": "POS 商品销售排行",
        "module": "零售交易",
        "status": "connected",
        "sync_key": "pos_sales",
        "module_path": "/app/dashboard",
        "pageable": True,
        "incremental": True,
        "target": "dwd.dwd_pos_sale_goods",
        "remark": "销售排行/商品汇总口径，不再作为经营概览日销核心口径",
    },
    {
        "method": TICKET_METHOD,
        "name": "POS 小票流水",
        "module": "零售交易",
        "status": "connected",
        "sync_key": "pos_tickets",
        "module_path": "/app/dashboard",
        "pageable": True,
        "incremental": True,
        "target": "ods.ods_baison_pos_ticket_api / dwd.dwd_pos_ticket / dws.*_daily",
        "remark": "真实订单流水口径，经营概览优先读取订单数、客单价、件单数与销售额",
    },
]

# 列表接口返回字段（不含 raw_data，避免太重）
_LIST_COLUMNS = (
    DimBaisonShop.id, DimBaisonShop.shop_id, DimBaisonShop.shop_code, DimBaisonShop.shop_name,
    DimBaisonShop.shop_type, DimBaisonShop.online_type, DimBaisonShop.area_code, DimBaisonShop.area_name,
    DimBaisonShop.category_code, DimBaisonShop.category_name, DimBaisonShop.province, DimBaisonShop.city,
    DimBaisonShop.county, DimBaisonShop.address, DimBaisonShop.channel_code, DimBaisonShop.channel_name,
    DimBaisonShop.discount_rate, DimBaisonShop.last_changed, DimBaisonShop.is_enabled, DimBaisonShop.synced_at,
)


class ShopListRequest(BaseModel):
    page: int = 1
    page_size: int = 20
    startModified: Optional[str] = None
    endModified: Optional[str] = None


class ShopSyncRequest(BaseModel):
    full_sync: bool = True
    page_size: int = 20
    startModified: Optional[str] = None
    endModified: Optional[str] = None


class BaisonApiTestRequest(BaseModel):
    method: str = Field(..., min_length=3, max_length=120)
    params: dict[str, Any] = Field(default_factory=dict)
    timeout: float = Field(default=30.0, ge=1.0, le=60.0)
    include_raw_response: bool = True


class BaisonModuleSyncRequest(BaseModel):
    full_sync: bool = True
    page_size: int = Field(default=20, ge=1, le=200)
    startModified: Optional[str] = None
    endModified: Optional[str] = None
    opt_user_code: str = "000"
    store_limit: Optional[int] = Field(default=None, ge=1, le=200)
    max_pages: int = Field(default=0, ge=0, le=5000)
    start_date: Optional[str] = None
    end_date: Optional[str] = None


async def _sync_module(
    module_key: str,
    req: BaisonModuleSyncRequest,
    db: AsyncSession,
    operator_id: Optional[int] = None,
) -> dict:
    """执行一次百胜模块同步，把数据写入中台对应 ODS/DIM/DWD 表。"""
    if module_key == "shop":
        if req.full_sync:
            return await import_all_shops(db, req.page_size, req.startModified, req.endModified, operator_id)
        return await import_shop_page(db, 1, req.page_size, req.startModified, req.endModified, operator_id)

    if module_key == "warehouse":
        if req.full_sync:
            return await import_all_warehouses(db, req.page_size, req.opt_user_code, operator_id)
        return await import_warehouse_page(db, 1, req.page_size, req.opt_user_code, operator_id)

    if module_key == "product":
        if req.full_sync:
            return await import_all_goods(
                db, req.page_size, req.startModified, req.endModified, req.opt_user_code, operator_id
            )
        return await import_goods_page(
            db, 1, req.page_size, req.startModified, req.endModified, req.opt_user_code, operator_id
        )

    if module_key == "sku":
        if req.full_sync:
            return await import_all_skus(db, req.page_size, operator_id)
        return await import_sku_page(db, 1, req.page_size, operator_id)

    if module_key == "inventory":
        if req.full_sync:
            return await import_all_inventory(db, req.page_size, operator_id)
        return await import_all_inventory(db, req.page_size, operator_id, store_limit=req.store_limit or 3)

    if module_key == "pos_sales":
        end_dt = datetime.strptime(req.end_date, "%Y-%m-%d %H:%M:%S") if req.end_date else datetime.now()
        start_dt = (
            datetime.strptime(req.start_date, "%Y-%m-%d %H:%M:%S")
            if req.start_date
            else end_dt - timedelta(days=1)
        )
        stores_q = select(DimBaisonShop.shop_code).where(
            DimBaisonShop.shop_code.is_not(None),
            or_(DimBaisonShop.is_enabled.is_(None), DimBaisonShop.is_enabled != "0"),
        ).order_by(DimBaisonShop.shop_code)
        if req.store_limit:
            stores_q = stores_q.limit(req.store_limit)
        stores = list((await db.execute(stores_q)).scalars().all())
        if not stores:
            return {"ok": False, "error": "未找到可同步的百胜门店，请先同步门店档案"}

        service = PosSaleGoodsService()
        result = await service.sync_multiple_stores(
            stores,
            start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            req.max_pages,
        )
        try:
            summary = await service.rebuild_dws_summary(
                start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            )
        except Exception as exc:
            logger.warning("pos sales dws rebuild skipped: %s", exc.__class__.__name__)
            summary = {"warning": "DWS汇总重建失败，请查看服务日志"}
        return {"ok": True, "method": "pos.storefx.sale_goods_get", **result, "summary": summary}

    if module_key == "pos_tickets":
        end_dt = datetime.strptime(req.end_date, "%Y-%m-%d %H:%M:%S") if req.end_date else datetime.now()
        start_dt = (
            datetime.strptime(req.start_date, "%Y-%m-%d %H:%M:%S")
            if req.start_date
            else end_dt - timedelta(days=1)
        )
        service = PosTicketService()
        return await service.sync_range(
            start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            max_pages=req.max_pages,
            page_size=req.page_size,
        )

    return {"ok": False, "error": f"未知同步模块: {module_key}"}


async def _background_sync_module(module_key: str, req: BaisonModuleSyncRequest, operator_id: Optional[int]):
    async with AsyncSessionLocal() as bg_db:
        try:
            result = await _sync_module(module_key, req, bg_db, operator_id)
            await bg_db.commit()
            logger.info("baison background sync done module=%s result=%s", module_key, result)
        except Exception:
            await bg_db.rollback()
            logger.exception("baison background sync failed module=%s", module_key)


# ------------------------- 接口目录 / 通用联调 -------------------------
@router.get("/catalog")
async def get_baison_api_catalog(
    current_user: SysUser = Depends(require_permission("system:baison-api:view")),
):
    """百胜接口目录：用于前端接口管理页展示已接入/待编排状态。"""
    modules = sorted({item["module"] for item in BAISON_API_CATALOG})
    return {
        "success": True,
        "data": {
            "items": BAISON_API_CATALOG,
            "modules": modules,
            "total": len(BAISON_API_CATALOG),
        },
    }


@router.post("/api-test")
async def test_baison_api(
    req: BaisonApiTestRequest,
    current_user: SysUser = Depends(require_permission("sync:import")),
):
    """通用联调：按百胜 method + params 调用开放平台，不做落库。"""
    method = req.method.strip()
    if not _METHOD_PATTERN.match(method):
        return {"success": False, "message": "method 格式不合法，仅允许字母、数字、点、下划线、冒号和短横线"}

    try:
        client = BaisonClient()
        resp = await run_in_threadpool(client.request, method, req.params, timeout=req.timeout)
        data_preview = resp.data
        raw_response = resp.raw_response if req.include_raw_response else None
        if raw_response and len(raw_response) > 20000:
            raw_response = raw_response[:20000] + "...[truncated]"

        return {
            "success": resp.status_code < 400,
            "message": "调用完成" if resp.status_code < 400 else "HTTP 调用失败",
            "data": {
                "method": method,
                "status_code": resp.status_code,
                "parsed": data_preview,
                "raw_response": raw_response,
                "request_params": resp.request_params,
            },
        }
    except BaisonError as exc:
        logger.warning("baison generic api-test failed method=%s err=%s", method, exc.__class__.__name__)
        return {"success": False, "method": method, "error": f"{exc.__class__.__name__}: {exc}"}
    except Exception:
        logger.exception("baison generic api-test unexpected error method=%s", method)
        return {"success": False, "method": method, "error": "内部错误，请查看服务日志"}


@router.post("/sync/module/{module_key}")
async def sync_baison_module(
    module_key: str,
    req: BaisonModuleSyncRequest,
    current_user: SysUser = Depends(require_permission("sync:import")),
    db: AsyncSession = Depends(get_db),
):
    """统一同步入口：按模块把百胜数据拉取并写入中台对应模块表。"""
    module_key = module_key.strip()
    if module_key not in {"shop", "warehouse", "product", "sku", "inventory", "pos_sales", "pos_tickets"}:
        return {"success": False, "message": f"不支持的同步模块: {module_key}"}

    background_modules = {"sku", "inventory", "pos_sales", "pos_tickets"}
    if req.full_sync and module_key in background_modules:
        _asyncio.create_task(_background_sync_module(module_key, req, current_user.id))
        return {
            "success": True,
            "message": f"{module_key} 全量同步已在后台启动，完成后请刷新对应模块",
            "data": {"module_key": module_key, "mode": "background"},
        }

    try:
        result = await _sync_module(module_key, req, db, current_user.id)
        if not result.get("ok", result.get("status") == "success"):
            return {"success": False, "message": "同步失败", "data": result, "error": result.get("error")}
        return {"success": True, "message": "同步完成，数据已写入对应模块", "data": result}
    except Exception:
        logger.exception("baison module sync error module=%s", module_key)
        return {"success": False, "message": "内部错误，请查看服务日志"}


# ------------------------- 联调测试 -------------------------
@router.post("/test/shop-list")
async def test_shop_list(
    req: ShopListRequest,
    current_user: SysUser = Depends(require_permission("sync:import")),
):
    """联调测试：调用 base.shop.get_list 拉取门店档案（不落库）。"""
    try:
        result = await run_in_threadpool(
            fetch_shop_list, req.page, req.page_size, req.startModified, req.endModified
        )
        shops = result["shops"]
        return {
            "success": result["ok"], "method": result["method"], "message": result["message"],
            "filter": result["filter"], "shop_count": len(shops), "sample": shops[:3],
            "request_params": result["request_params"], "raw_response": result["raw_response"],
        }
    except BaisonError as exc:
        logger.warning("baison shop-list test failed: %s", exc.__class__.__name__)
        return {"success": False, "method": SHOP_LIST_METHOD, "error": f"{exc.__class__.__name__}: {exc}"}
    except Exception:
        logger.exception("baison shop-list unexpected error")
        return {"success": False, "method": SHOP_LIST_METHOD, "error": "内部错误，请查看服务日志"}


# ------------------------- 同步落库 -------------------------
@router.post("/sync/shop-list")
async def sync_shop_list_to_db(
    req: ShopListRequest,
    current_user: SysUser = Depends(require_permission("sync:import")),
    db: AsyncSession = Depends(get_db),
):
    """同步单页门店并落库 dim.dim_baison_shop。"""
    try:
        result = await import_shop_page(db, req.page, req.page_size, req.startModified, req.endModified)
        return {"success": result.get("ok", False), "method": SHOP_LIST_METHOD, **result}
    except Exception:
        logger.exception("baison shop sync(page) error")
        return {"success": False, "method": SHOP_LIST_METHOD, "error": "内部错误，请查看服务日志"}


@router.post("/sync/shops")
async def sync_shops(
    req: ShopSyncRequest,
    current_user: SysUser = Depends(require_permission("sync:import")),
    db: AsyncSession = Depends(get_db),
):
    """门店档案同步（前端“同步门店数据”按钮）。full_sync=True 走全量分页。"""
    try:
        if req.full_sync:
            r = await import_all_shops(db, req.page_size, req.startModified, req.endModified)
        else:
            r = await import_shop_page(db, 1, req.page_size, req.startModified, req.endModified)
        if not r.get("ok"):
            return {"success": False, "message": "同步失败", "error": r.get("error"), "data": r}
        return {
            "success": True, "message": "同步完成",
            "data": {
                "total_pages": r.get("total_pages", 1),
                "total_records": r.get("total_records", r.get("total_rows", 0)),
                "inserted": r.get("inserted", 0),
                "updated": r.get("updated", 0),
                "skipped": r.get("skipped", 0),
                "batch_no": r.get("batch_no"),
            },
        }
    except Exception:
        logger.exception("baison shops sync error")
        return {"success": False, "message": "内部错误，请查看服务日志"}


# ------------------------- 查询 -------------------------
@router.get("/shops")
async def list_shops(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None,
    area_name: Optional[str] = None,
    shop_type: Optional[str] = None,
    online_type: Optional[str] = None,
    is_enabled: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("system:baison-api:view")),
    db: AsyncSession = Depends(get_db),
):
    """门店档案分页查询（不返回 raw_data）。"""
    try:
        conditions = []
        if keyword:
            kw = f"%{keyword.strip()}%"
            conditions.append(or_(DimBaisonShop.shop_code.ilike(kw), DimBaisonShop.shop_name.ilike(kw)))
        if area_name:
            conditions.append(DimBaisonShop.area_name == area_name)
        if shop_type:
            conditions.append(DimBaisonShop.shop_type == shop_type)
        if online_type:
            conditions.append(DimBaisonShop.online_type == online_type)
        if is_enabled is not None and is_enabled != "":
            conditions.append(DimBaisonShop.is_enabled == is_enabled)

        total = (await db.execute(
            select(func.count()).select_from(DimBaisonShop).where(*conditions)
        )).scalar() or 0

        rows = (await db.execute(
            select(*_LIST_COLUMNS).where(*conditions)
            .order_by(DimBaisonShop.shop_code)
            .offset((page - 1) * page_size).limit(page_size)
        )).mappings().all()

        items = [dict(r) for r in rows]
        return {"success": True, "data": {"items": items, "total": total, "page": page, "page_size": page_size}}
    except Exception:
        logger.exception("baison list_shops error")
        return {"success": False, "message": "查询失败，请查看服务日志"}


@router.get("/shops/{shop_code}")
async def get_shop_detail(
    shop_code: str,
    current_user: SysUser = Depends(require_permission("system:baison-api:view")),
    db: AsyncSession = Depends(get_db),
):
    """门店详情（含 raw_data）。"""
    try:
        obj = (await db.execute(
            select(DimBaisonShop).where(DimBaisonShop.shop_code == shop_code)
        )).scalar_one_or_none()
        if obj is None:
            return {"success": False, "message": "门店不存在"}
        data = {c.name: getattr(obj, c.name) for c in DimBaisonShop.__table__.columns}
        return {"success": True, "data": data}
    except Exception:
        logger.exception("baison get_shop_detail error")
        return {"success": False, "message": "查询失败，请查看服务日志"}
