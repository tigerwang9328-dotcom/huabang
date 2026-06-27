"""经营概览 API - 使用统一 business_overview_service"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from datetime import date, timedelta
from app.core.database import get_db
from app.api.v1.deps import get_current_user, require_permission
from app.models.sys import SysUser
from app.services.business_overview_service import get_overview
from app.schemas.common import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["驾驶舱"])


@router.get("/overview", response_model=ApiResponse)
async def overview(
    stat_date: Optional[str] = Query(None, description="统计日期YYYY-MM-DD，默认昨日"),
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """经营概览 — 只显示真实基础数据，未接入指标统一返回「待接入」"""
    data = await get_overview(db, stat_date)
    return ApiResponse.ok(data=data)


@router.get("/sales-trend", response_model=ApiResponse)
async def get_sales_trend(
    days: int = Query(7, ge=3, le=30),
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """近N天销售趋势"""
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)
    try:
        result = await db.execute(
            select(text("stat_date, total_sales_amount, total_order_count"))
            .select_from(text("dws.dws_company_daily"))
            .where(text("stat_date >= :s AND stat_date <= :e"))
            .params(s=start_date, e=end_date)
            .order_by(text("stat_date"))
        )
        rows = result.mappings().all()
        trend = []
        for r in rows:
            trend.append({
                "date": str(r["stat_date"]),
                "total_sales": float(r["total_sales_amount"]) if r["total_sales_amount"] else None,
                "order_count": int(r["total_order_count"]) if r["total_order_count"] else None,
            })
        return ApiResponse.ok(data={"trend": trend, "days": days, "note": "销售明细未接入时显示为空" if not any(t["total_sales"] for t in trend) else None})
    except Exception:
        logger.exception("sales trend error")
        return ApiResponse.ok(data={"trend": [], "days": days, "note": "销售趋势数据暂不可用"})


@router.get("/store-rank", response_model=ApiResponse)
async def get_store_rank(
    stat_date: Optional[str] = None,
    top_n: int = Query(10, ge=3, le=50),
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """门店销售排行 — 销售未接入时返回门店基础列表"""
    try:
        r = await db.execute(
            select(text("store_code, net_sales_amount, order_count, avg_order_value, items_per_order"))
            .select_from(text("dws.dws_store_daily"))
            .where(text("net_sales_amount IS NOT NULL"))
            .order_by(text("net_sales_amount DESC"))
            .limit(top_n)
        )
        rows = r.mappings().all()
        if rows:
            rank = [
                {"rank": i + 1, "store_code": row["store_code"],
                 "net_sales": float(row["net_sales_amount"]) if row["net_sales_amount"] else 0,
                 "order_count": row["order_count"],
                 "avg_order_value": float(row["avg_order_value"]) if row["avg_order_value"] else None,
                 "items_per_order": float(row["items_per_order"]) if row["items_per_order"] else None}
                for i, row in enumerate(rows)
            ]
            return ApiResponse.ok(data={"stat_date": str(rows[0].get("stat_date", "")), "rank": rank})
    except Exception:
        logger.exception("store rank error")

    # 无销售数据时返回空排行+提示
    return ApiResponse.ok(data={"stat_date": None, "rank": [], "note": "销售数据尚未接入，排行暂不可用"})


@router.get("/task-summary", response_model=ApiResponse)
async def get_task_summary(
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """任务汇总"""
    try:
        result = await db.execute(
            select(
                text("status"),
                func.count().label("cnt")
            ).select_from(text("app.app_action_task")).where(text("is_deleted = false")).group_by(text("status"))
        )
        rows = result.fetchall()
        status_map = {r.status: r.cnt for r in rows}
        return ApiResponse.ok(data={
            "draft": status_map.get("draft", 0), "pending": status_map.get("pending", 0),
            "processing": status_map.get("processing", 0), "feedback_submitted": status_map.get("feedback_submitted", 0),
            "review_passed": status_map.get("review_passed", 0), "review_failed": status_map.get("review_failed", 0),
            "overdue": status_map.get("overdue", 0), "closed": status_map.get("closed", 0),
            "cancelled": status_map.get("cancelled", 0),
        })
    except Exception:
        logger.exception("task summary error")
        return ApiResponse.ok(data={})
