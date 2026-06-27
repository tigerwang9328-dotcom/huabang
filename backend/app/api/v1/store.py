"""门店运营中心 - 标准门店维(dim.dim_store)查询接口。

读取标准业务表 dim_store（不返回百胜原始字段、不暴露任何密钥）。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.dim import DimStore

logger = logging.getLogger("store.api")

router = APIRouter(prefix="/store", tags=["门店运营中心"])

_COLS = (
    DimStore.id, DimStore.store_code, DimStore.store_name, DimStore.region_name,
    DimStore.store_type, DimStore.business_type, DimStore.province, DimStore.city,
    DimStore.county, DimStore.address, DimStore.status, DimStore.source_system, DimStore.synced_at,
)


@router.get("/list")
async def list_stores(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None,
    region_name: Optional[str] = None,
    store_type: Optional[str] = None,
    business_type: Optional[str] = None,
    status: Optional[str] = None,
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

        total = (await db.execute(select(func.count()).select_from(DimStore).where(*conds))).scalar() or 0
        rows = (await db.execute(
            select(*_COLS).where(*conds).order_by(DimStore.store_code)
            .offset((page - 1) * page_size).limit(page_size)
        )).mappings().all()
        return {"success": True, "data": {"items": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}}
    except Exception:
        logger.exception("store list error")
        return {"success": False, "message": "查询失败，请查看服务日志"}
