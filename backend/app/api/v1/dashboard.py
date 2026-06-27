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
    # 默认取最近一天有真实销售数据的日期（无则取昨日），避免当日 ETL 未出数时首页空白
    if stat_date:
        query_date = date.fromisoformat(stat_date)
    else:
        _latest = await db.execute(
            select(func.max(DwsCompanyDaily.stat_date)).where(DwsCompanyDaily.total_sales_amount.isnot(None))
        )
        query_date = _latest.scalar() or (date.today() - timedelta(days=1))

    # 公司日汇总
    company_result = await db.execute(
        select(DwsCompanyDaily).where(DwsCompanyDaily.stat_date == query_date)
    )
    company = company_result.scalar_one_or_none()

    # 任务摘要
    task_result = await db.execute(
        select(
            func.count().filter(AppActionTask.status.in_(["pending", "processing"])).label("pending"),
            func.count().filter(AppActionTask.status == "overdue").label("overdue"),
        ).where(AppActionTask.is_deleted == False)
    )
    task_row = task_result.one()

    # 库存摘要（取最新快照）
    inv_result = await db.execute(
        select(DwsInventoryDaily).where(
            DwsInventoryDaily.stat_date == query_date,
            DwsInventoryDaily.store_code == "ALL"
        )
    )
    inv = inv_result.scalar_one_or_none()

    # null 安全转换：字段为 NULL 时返回 None（前端显示“—”/待接入），不报 500、不造假
    def _f(x):
        return float(x) if x is not None else None

    age_90_plus = None
    if inv is not None:
        age_90_plus = _f((inv.age_91_180_amount or 0) + (inv.age_180_plus_amount or 0))

    data = {
        "stat_date": str(query_date),
        "is_cost_complete": company.is_cost_complete if company else False,
        "data_tip": None if (company and company.is_cost_complete) else "成本数据不完整，毛利/利润为预估值",
        # 销售
        "total_sales": _f(company.total_sales_amount) if company else None,
        "offline_sales": _f(company.offline_sales_amount) if company else None,
        "online_sales": _f(company.online_sales_amount) if company else None,
        "online_ratio": _f(company.online_ratio) if company and company.online_ratio else None,
        "net_sales": _f(company.net_sales_amount) if company else None,
        "order_count": company.total_order_count if company else None,
        "item_count": company.total_item_count if company else None,
        "avg_order_value": _f(company.avg_order_value) if company and company.avg_order_value else None,
        "items_per_order": _f(company.items_per_order) if company and company.items_per_order else None,
        "avg_discount_rate": _f(company.avg_discount_rate) if company and company.avg_discount_rate else None,
        # 财务（仅有权限用户可见）
        "gross_profit": _f(company.gross_profit) if company and company.gross_profit else None,
        "gross_margin": _f(company.gross_margin) if company and company.gross_margin else None,
        # 库存
        "total_inventory_amount": _f(inv.total_cost_amount) if inv else None,
        "age_90_plus_amount": age_90_plus,
        # 任务
        "pending_task_count": task_row.pending,
        "overdue_task_count": task_row.overdue,
        "no_data": company is None,
    }

    # 权限过滤：非财务/老板角色不返回毛利/现金
    roles = getattr(current_user, "_roles", [])
    # TODO: 接入字段权限查询
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

    result = await db.execute(
        select(DwsCompanyDaily)
        .where(
            DwsCompanyDaily.stat_date >= start_date,
            DwsCompanyDaily.stat_date <= end_date,
        )
        .order_by(DwsCompanyDaily.stat_date)
    )
    rows = result.scalars().all()

    trend = [
        {
            "date": str(r.stat_date),
            "total_sales": float(r.total_sales_amount) if r.total_sales_amount else 0,
            "offline_sales": float(r.offline_sales_amount) if r.offline_sales_amount else 0,
            "online_sales": float(r.online_sales_amount) if r.online_sales_amount else 0,
            "order_count": r.total_order_count,
            "net_sales": float(r.net_sales_amount) if r.net_sales_amount else 0,
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
    # 默认取最近一天有真实门店销售的日期（无则取昨日）
    if stat_date:
        query_date = date.fromisoformat(stat_date)
    else:
        _latest = await db.execute(
            select(func.max(DwsStoreDailySales.stat_date)).where(DwsStoreDailySales.net_sales_amount.isnot(None))
        )
        query_date = _latest.scalar() or (date.today() - timedelta(days=1))

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
