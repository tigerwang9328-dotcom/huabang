"""百胜 E3ERP 开放平台 API 接口（联调测试 + 店铺档案查询/同步）。

脱敏约束：任何响应/日志都不输出 AppKey/AppSecret/sign 原文；request_params 已脱敏。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.integrations.baison.exceptions import BaisonError
from app.integrations.baison.services.shop_service import (
    SHOP_LIST_METHOD,
    fetch_shop_list,
    import_all_shops,
    import_shop_page,
)
from app.models.dim import DimBaisonShop

logger = logging.getLogger("baison.api")

router = APIRouter(prefix="/integrations/baison", tags=["百胜E3ERP对接"])

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


# ------------------------- 联调测试 -------------------------
@router.post("/test/shop-list")
async def test_shop_list(req: ShopListRequest):
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
async def sync_shop_list_to_db(req: ShopListRequest, db: AsyncSession = Depends(get_db)):
    """同步单页门店并落库 dim.dim_baison_shop。"""
    try:
        result = await import_shop_page(db, req.page, req.page_size, req.startModified, req.endModified)
        return {"success": result.get("ok", False), "method": SHOP_LIST_METHOD, **result}
    except Exception:
        logger.exception("baison shop sync(page) error")
        return {"success": False, "method": SHOP_LIST_METHOD, "error": "内部错误，请查看服务日志"}


@router.post("/sync/shops")
async def sync_shops(req: ShopSyncRequest, db: AsyncSession = Depends(get_db)):
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
async def get_shop_detail(shop_code: str, db: AsyncSession = Depends(get_db)):
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
