"""商品经营中心 - 标准商品维(dim.dim_product)查询 + 百胜商品主档同步。

读取标准业务表 dim_product（不返回 raw_data / 成本价 / 任何密钥）。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
import asyncio as _asyncio

from app.core.database import AsyncSessionLocal
from app.integrations.baison.services.product_service import GOODS_LIST_METHOD, import_all_goods, import_goods_page
from app.integrations.baison.services.sku_service import SKU_LIST_METHOD, import_all_skus, import_sku_page
from app.models.dim import DimProduct, DimSku

logger = logging.getLogger("product.api")

router = APIRouter(tags=["商品经营中心"])

# 列表返回字段（不含 raw_data / cost_price）
_COLS = (
    DimProduct.id, DimProduct.product_code, DimProduct.product_name,
    DimProduct.category_code, DimProduct.category_name, DimProduct.brand_name,
    DimProduct.top_category_name, DimProduct.year, DimProduct.season,
    DimProduct.tag_price, DimProduct.market_price, DimProduct.supplier_name,
    DimProduct.status, DimProduct.source_system, DimProduct.synced_at,
)
# 未接入指标占位
_PENDING = {"sales_qty": "待接入", "sales_amount": "待接入", "inventory_qty": "待接入",
            "lifecycle_stage": "待接入", "ai_suggestion": "待接入"}


class ProductSyncRequest(BaseModel):
    full_sync: bool = True
    page_size: int = 20
    startModified: Optional[str] = "2026-01-01 00:00:00"
    endModified: Optional[str] = "2026-12-31 23:59:59"
    opt_user_code: str = "000"


@router.get("/product/list")
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None,
    brand_name: Optional[str] = None,
    category_name: Optional[str] = None,
    season: Optional[str] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
    source_system: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """标准商品维分页查询（商品主档）。"""
    try:
        conds = []
        if keyword:
            kw = f"%{keyword.strip()}%"
            conds.append(or_(DimProduct.product_code.ilike(kw), DimProduct.product_name.ilike(kw)))
        if brand_name:
            conds.append(DimProduct.brand_name == brand_name)
        if category_name:
            conds.append(DimProduct.category_name == category_name)
        if season:
            conds.append(DimProduct.season == season)
        if year is not None:
            conds.append(DimProduct.year == year)
        if status:
            conds.append(DimProduct.status == status)
        if source_system:
            conds.append(DimProduct.source_system == source_system)

        total = (await db.execute(select(func.count()).select_from(DimProduct).where(*conds))).scalar() or 0
        rows = (await db.execute(
            select(*_COLS).where(*conds).order_by(DimProduct.product_code)
            .offset((page - 1) * page_size).limit(page_size)
        )).mappings().all()
        items = [{**dict(r), **_PENDING} for r in rows]
        return {"success": True, "data": {"items": items, "total": total, "page": page, "page_size": page_size}}
    except Exception:
        logger.exception("product list error")
        return {"success": False, "message": "查询失败，请查看服务日志"}


@router.post("/sync/baison/products")
async def sync_baison_products(req: ProductSyncRequest, db: AsyncSession = Depends(get_db)):
    """同步百胜商品主档（prm.goods.list_get）。full_sync=True 走全量分页。"""
    try:
        if req.full_sync:
            r = await import_all_goods(db, req.page_size, req.startModified, req.endModified, req.opt_user_code)
        else:
            r = await import_goods_page(db, 1, req.page_size, req.startModified, req.endModified, req.opt_user_code)
        if not r.get("ok"):
            return {"success": False, "message": "同步失败", "error": r.get("error"), "data": r}
        return {
            "success": True, "message": "同步完成",
            "data": {
                "method": GOODS_LIST_METHOD,
                "page_total": r.get("page_total"),
                "total_result": r.get("total_result"),
                "ods_inserted": r.get("ods_inserted", 0),
                "ods_updated": r.get("ods_updated", 0),
                "dim_inserted": r.get("dim_inserted", 0),
                "dim_updated": r.get("dim_updated", 0),
                "skipped": r.get("skipped", 0),
                "batch_no": r.get("batch_no"),
            },
        }
    except Exception:
        logger.exception("product sync error")
        return {"success": False, "message": "内部错误，请查看服务日志"}


# SKU 列表返回字段（不含 raw_data / 成本价 / ckj / cbj）
_SKU_COLS = (
    DimSku.id, DimSku.sku_code, DimSku.product_code, DimSku.product_name,
    DimSku.barcode, DimSku.color_code, DimSku.color_name, DimSku.size_code, DimSku.size_name,
    DimSku.brand_name, DimSku.season_name, DimSku.tag_price, DimSku.market_price,
    DimSku.status, DimSku.source_system, DimSku.synced_at,
)
_SKU_PENDING = {"inventory_qty": "待接入", "sales_qty": "待接入", "sales_amount": "待接入", "ai_suggestion": "待接入"}


class SkuSyncRequest(BaseModel):
    full_sync: bool = True
    page_size: int = 20


@router.get("/product/sku-list")
async def list_skus(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None,
    product_code: Optional[str] = None,
    brand_name: Optional[str] = None,
    color_name: Optional[str] = None,
    size_name: Optional[str] = None,
    season_name: Optional[str] = None,
    status: Optional[str] = None,
    source_system: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """标准 SKU 维分页查询（SKU档案）。不返回 raw_data / 成本价。"""
    try:
        conds = []
        if keyword:
            kw = f"%{keyword.strip()}%"
            conds.append(or_(DimSku.sku_code.ilike(kw), DimSku.barcode.ilike(kw),
                             DimSku.product_code.ilike(kw), DimSku.product_name.ilike(kw)))
        if product_code:
            conds.append(DimSku.product_code == product_code.strip())
        if brand_name:
            conds.append(DimSku.brand_name == brand_name)
        if color_name:
            conds.append(DimSku.color_name == color_name)
        if size_name:
            conds.append(DimSku.size_name == size_name)
        if season_name:
            conds.append(DimSku.season_name == season_name)
        if status:
            conds.append(DimSku.status == status)
        if source_system:
            conds.append(DimSku.source_system == source_system)

        total = (await db.execute(select(func.count()).select_from(DimSku).where(*conds))).scalar() or 0
        rows = (await db.execute(
            select(*_SKU_COLS).where(*conds).order_by(DimSku.sku_code)
            .offset((page - 1) * page_size).limit(page_size)
        )).mappings().all()
        items = [{**dict(r), **_SKU_PENDING} for r in rows]
        return {"success": True, "data": {"items": items, "total": total, "page": page, "page_size": page_size}}
    except Exception:
        logger.exception("sku list error")
        return {"success": False, "message": "查询失败，请查看服务日志"}


async def _bg_full_sku_sync():
    async with AsyncSessionLocal() as bg_db:
        try:
            await import_all_skus(bg_db, 20)
            await bg_db.commit()
        except Exception:
            logger.exception("background sku full sync error")


@router.post("/sync/baison/skus")
async def sync_baison_skus(req: SkuSyncRequest, db: AsyncSession = Depends(get_db)):
    """同步百胜 SKU 档案（prm.goods.sku_list_get）。

    full_sync=True：全量约 2048 页/40944 条、约 15 分钟，放后台任务执行并立即返回（避免网关超时）。
    full_sync=False：仅同步第 1 页（快速验证），返回明细计数。
    """
    try:
        if req.full_sync:
            _asyncio.create_task(_bg_full_sku_sync())
            return {"success": True, "message": "SKU 全量同步已在后台启动（约 2048 页 / 40944 条，约 15 分钟），完成后请刷新列表",
                    "data": {"method": SKU_LIST_METHOD, "page_total": 2048, "total_result": 40944, "mode": "background"}}
        r = await import_sku_page(db, 1, req.page_size)
        if not r.get("ok"):
            return {"success": False, "message": "同步失败", "error": r.get("error"), "data": r}
        return {"success": True, "message": "首页同步完成",
                "data": {"method": SKU_LIST_METHOD, "page_total": r.get("page_total"), "total_result": r.get("total_result"),
                         "ods_inserted": r.get("ods_inserted"), "ods_updated": r.get("ods_updated"),
                         "dim_inserted": r.get("dim_inserted"), "dim_updated": r.get("dim_updated"),
                         "skipped": r.get("skipped"), "batch_no": r.get("batch_no")}}
    except Exception:
        logger.exception("sku sync error")
        return {"success": False, "message": "内部错误，请查看服务日志"}
