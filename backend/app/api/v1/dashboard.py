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
from app.core.store_whitelist import allowed_store_sql_in
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
    end_date: Optional[str] = Query(None, description="结束日期YYYY-MM-DD，默认最新数据日期"),
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """近N天销售趋势"""
    if end_date:
        end_dt = date.fromisoformat(end_date)
    else:
        latest_result = await db.execute(text("""
            SELECT MAX(stat_date)
            FROM dws.dws_company_daily
            WHERE total_sales_amount IS NOT NULL
        """))
        end_dt = latest_result.scalar() or (date.today() - timedelta(days=1))
    start_dt = end_dt - timedelta(days=days - 1)

    result = await db.execute(text("""
        SELECT stat_date AS biz_date,
               COALESCE(total_sales_amount, 0) AS total_sales,
               COALESCE(total_order_count, 0) AS order_count,
               COALESCE(total_item_count, 0) AS item_count
        FROM dws.dws_company_daily
        WHERE stat_date BETWEEN :start_date AND :end_date
        ORDER BY stat_date
    """), {"start_date": start_dt, "end_date": end_dt})
    rows = result.mappings().all()

    trend = [
        {
            "date": str(r["biz_date"]),
            "total_sales": float(r["total_sales"] or 0),
            "offline_sales": float(r["total_sales"] or 0),
            "online_sales": 0,
            "order_count": int(r["order_count"] or 0),
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
    """门店销售排行

    未指定日期时使用 DWD 小票中最新有效业务日，排行口径与门店分析/经营概览一致：
    销售额、实收金额均来自小票支付口径，避免商品明细金额绕开支付方式口径。
    """
    if stat_date:
        query_date = date.fromisoformat(stat_date)
    else:
        latest_result = await db.execute(text("""
            SELECT MAX(biz_date)
            FROM dwd.dwd_pos_ticket
            WHERE sales_amount IS NOT NULL
              AND COALESCE(is_void, false) = false
              AND COALESCE(is_pending, false) = false
        """))
        query_date = latest_result.scalar() or (date.today() - timedelta(days=1))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS dwd.dwd_store_recharge_daily (
            biz_date DATE NOT NULL,
            store_code VARCHAR(64) NOT NULL,
            recharge_amount NUMERIC(16, 2) NOT NULL DEFAULT 0,
            source VARCHAR(64) NOT NULL DEFAULT 'manual',
            note TEXT,
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now(),
            PRIMARY KEY (biz_date, store_code, source)
        )
    """))
    store_in = allowed_store_sql_in()
    result = await db.execute(text(f"""
        WITH ticket AS (
            SELECT store_code,
                   COALESCE(SUM(sales_amount), 0) AS net_sales,
                   COALESCE(SUM(actual_pay_amount), 0) AS actual_pay_amount,
                   COUNT(*)::int AS order_count,
                   COALESCE(SUM(sales_qty), 0) AS item_count
            FROM dwd.dwd_pos_ticket
            WHERE biz_date = :query_date
              AND COALESCE(store_code, '') IN {store_in}
              AND COALESCE(is_void, false) = false
              AND COALESCE(is_pending, false) = false
            GROUP BY store_code
        ), recharge AS (
            SELECT store_code, COALESCE(SUM(recharge_amount), 0) AS recharge_amount
            FROM dwd.dwd_store_recharge_daily
            WHERE biz_date = :query_date
              AND COALESCE(store_code, '') IN {store_in}
            GROUP BY store_code
        )
        SELECT ticket.store_code,
               ticket.net_sales,
               ticket.actual_pay_amount + COALESCE(recharge.recharge_amount, 0) AS actual_pay_amount,
               ticket.order_count,
               ticket.item_count,
               CASE WHEN ticket.order_count = 0 THEN 0
                    ELSE ticket.net_sales / ticket.order_count
               END AS avg_order_value,
               CASE WHEN ticket.order_count = 0 THEN 0
                    ELSE ticket.item_count::numeric / ticket.order_count
               END AS items_per_order
        FROM ticket
        LEFT JOIN recharge ON recharge.store_code = ticket.store_code
        WHERE ticket.net_sales > 0
        ORDER BY net_sales DESC
        LIMIT :top_n
    """), {"query_date": query_date, "top_n": top_n})
    rows = result.mappings().all()

    rank = [
        {
            "rank": i + 1,
            "store_code": r["store_code"],
            "net_sales": float(r["net_sales"] or 0),
            "actual_pay_amount": float(r["actual_pay_amount"] or 0),
            "order_count": int(r["order_count"] or 0),
            "avg_order_value": float(r["avg_order_value"] or 0),
            "items_per_order": float(r["items_per_order"] or 0),
            "item_count": int(float(r["item_count"] or 0)),
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
