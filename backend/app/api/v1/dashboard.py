from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import date, timedelta
from typing import Optional
from app.core.database import get_db
from app.api.v1.deps import get_current_user, require_permission
from app.models.sys import SysUser
from app.models.dws import DwsCompanyDaily, DwsStoreDailySales, DwsInventoryDaily
from app.models.dm import DmBossDailyReport
from app.models.app import AppActionTask
from app.schemas.common import ApiResponse, safe_div
from app.services.business_overview_service import get_overview as get_business_overview
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["驾驶舱"])


@router.get("/overview", response_model=ApiResponse)
async def get_overview(
    stat_date: Optional[str] = Query(None, description="统计日期YYYY-MM-DD，默认昨日"),
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """首页核心指标概览"""
    data = await get_business_overview(db, stat_date)
    return ApiResponse.ok(data=data)


@router.get("/sales-trend", response_model=ApiResponse)
async def get_sales_trend(
    days: int = Query(7, ge=3, le=30),
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """近N天销售趋势"""
    latest_result = await db.execute(text("""
        SELECT MAX(biz_date)
        FROM dwd.dwd_pos_sale_goods
        WHERE sales_amount IS NOT NULL
    """))
    end_date = latest_result.scalar() or (date.today() - timedelta(days=1))
    start_date = end_date - timedelta(days=days - 1)

    result = await db.execute(text("""
        SELECT biz_date,
               COALESCE(SUM(sales_amount), 0) AS total_sales,
               COALESCE(SUM(sales_qty), 0) AS item_count
        FROM dwd.dwd_pos_sale_goods
        WHERE biz_date BETWEEN :start_date AND :end_date
        GROUP BY biz_date
        ORDER BY biz_date
    """), {"start_date": start_date, "end_date": end_date})
    rows = result.mappings().all()

    trend = [
        {
            "date": str(r["biz_date"]),
            "total_sales": float(r["total_sales"] or 0),
            "offline_sales": float(r["total_sales"] or 0),
            "online_sales": 0,
            "order_count": 0,
            "item_count": int(float(r["item_count"] or 0)),
            "net_sales": float(r["total_sales"] or 0),
        }
        for r in rows
    ]
    return ApiResponse.ok(data={"trend": trend, "days": days})


@router.get("/store-rank", response_model=ApiResponse)
async def get_store_rank(
    stat_date: Optional[str] = None,
    top_n: int = Query(10, ge=3, le=50),
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """门店销售排行"""
    query_date = date.fromisoformat(stat_date) if stat_date else date.today() - timedelta(days=1)

    result = await db.execute(
        select(DwsStoreDailySales)
        .where(
            DwsStoreDailySales.stat_date == query_date,
            DwsStoreDailySales.channel != "online",
        )
        .order_by(DwsStoreDailySales.net_sales_amount.desc())
        .limit(top_n)
    )
    rows = result.scalars().all()

    rank = [
        {
            "rank": i + 1,
            "store_code": r.store_code,
            "net_sales": float(r.net_sales_amount) if r.net_sales_amount else 0,
            "order_count": r.order_count,
            "avg_order_value": float(r.avg_order_value) if r.avg_order_value else 0,
            "items_per_order": float(r.items_per_order) if r.items_per_order else 0,
        }
        for i, r in enumerate(rows)
    ]
    return ApiResponse.ok(data={"stat_date": str(query_date), "rank": rank})


@router.get("/task-summary", response_model=ApiResponse)
async def get_task_summary(
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """任务汇总（今日待处理/逾期/完成趋势）"""
    result = await db.execute(
        select(
            AppActionTask.status,
            func.count().label("cnt")
        )
        .where(AppActionTask.is_deleted == False)
        .group_by(AppActionTask.status)
    )
    rows = result.fetchall()
    status_map = {r.status: r.cnt for r in rows}

    return ApiResponse.ok(data={
        "draft": status_map.get("draft", 0),
        "pending": status_map.get("pending", 0),
        "processing": status_map.get("processing", 0),
        "feedback_submitted": status_map.get("feedback_submitted", 0),
        "review_passed": status_map.get("review_passed", 0),
        "review_failed": status_map.get("review_failed", 0),
        "overdue": status_map.get("overdue", 0),
        "closed": status_map.get("closed", 0),
        "cancelled": status_map.get("cancelled", 0),
    })
