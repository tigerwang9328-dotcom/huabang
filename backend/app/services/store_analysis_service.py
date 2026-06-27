"""门店分析统一数据服务 - Web 和 Mobile 共用"""
import logging
from typing import Optional
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PENDING = {"value": None, "display": "待接入", "status": "pending_data"}


def _pending(reason: str = "") -> dict:
    return {"value": None, "display": "待接入", "status": "pending_data", "reason": reason}


def _value(val, decimals: int = 0) -> dict:
    if val is None:
        return _pending()
    if isinstance(val, (int, float)):
        return {"value": round(float(val), decimals), "display": str(round(float(val), decimals)), "status": "ready"}
    return {"value": val, "display": str(val), "status": "ready"}


async def get_store_analysis_summary(db: AsyncSession) -> dict:
    """门店分析顶部指标"""
    # 门店统计
    total = await db.execute(text("SELECT COUNT(*) FROM dim.dim_store"))
    store_total = total.scalar() or 0

    active = await db.execute(text("SELECT COUNT(*) FROM dim.dim_store WHERE status = '营业'"))
    store_active = active.scalar() or 0

    disabled = await db.execute(text("SELECT COUNT(*) FROM dim.dim_store WHERE status = '停用'"))
    store_disabled = disabled.scalar() or 0

    regions_r = await db.execute(text("SELECT COUNT(DISTINCT region_name) FROM dim.dim_store WHERE region_name IS NOT NULL"))
    region_count = regions_r.scalar() or 0

    return {
        "updated_at": None,
        "summary": {
            "total_stores": _value(store_total),
            "active_stores": _value(store_active),
            "disabled_stores": _value(store_disabled),
            "region_count": _value(region_count),
            "today_sales": _pending("销售明细尚未接入"),
            "today_orders": _pending("销售明细尚未接入"),
            "today_items": _pending("销售明细尚未接入"),
        },
        "pending_fields": [
            {"field": "today_sales", "reason": "销售明细尚未接入"},
            {"field": "today_orders", "reason": "销售明细尚未接入"},
            {"field": "today_items", "reason": "销售明细尚未接入"},
        ],
    }


async def get_store_list(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    region_name: Optional[str] = None,
    store_type: Optional[str] = None,
    business_type: Optional[str] = None,
    status: Optional[str] = None,
) -> dict:
    """门店列表（复用现有 dim_store 查询逻辑）"""
    conds = []
    params = {}
    if keyword:
        kw = f"%{keyword.strip()}%"
        conds.append("(s.store_code ILIKE :kw OR s.store_name ILIKE :kw)")
        params["kw"] = kw
    if region_name:
        conds.append("s.region_name = :region_name")
        params["region_name"] = region_name
    if store_type:
        conds.append("s.store_type = :store_type")
        params["store_type"] = store_type
    if business_type:
        conds.append("s.business_type = :business_type")
        params["business_type"] = business_type
    if status:
        conds.append("s.status = :status")
        params["status"] = status

    where = " AND ".join(conds) if conds else "TRUE"

    total_r = await db.execute(
        text(f"SELECT COUNT(*) FROM dim.dim_store s WHERE {where}").params(**params)
    )
    total = total_r.scalar() or 0

    rows_r = await db.execute(
        text(f"""SELECT s.id, s.store_code, s.store_name, s.region_name, s.store_type,
                        s.business_type, s.province, s.city, s.county, s.address,
                        s.status, s.source_system, s.synced_at
                 FROM dim.dim_store s WHERE {where}
                 ORDER BY s.store_code
                 LIMIT :lim OFFSET :off""")
        .params(**params, lim=page_size, off=(page - 1) * page_size)
    )
    items = [dict(r._mapping) for r in rows_r]

    # 计算最后同步时间
    synced = await db.execute(text("SELECT MAX(synced_at) FROM dim.dim_store"))
    last_sync = synced.scalar()

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "last_synced_at": str(last_sync) if last_sync else None,
    }
