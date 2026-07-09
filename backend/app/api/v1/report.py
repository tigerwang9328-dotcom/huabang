from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
from typing import Optional
from app.core.database import get_db
from app.api.v1.deps import require_permission
from app.models.sys import SysUser
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/report", tags=["老板日报"])

@router.post("/boss-daily/generate", response_model=ApiResponse)
async def generate_boss_daily(
    stat_date: Optional[str] = None,
    force: bool = False,
    current_user: SysUser = Depends(require_permission("dashboard:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """生成老板日报（含AI摘要）。force=true 强制重新生成AI摘要"""
    if not stat_date:
        stat_date = (date.today() - timedelta(days=1)).isoformat()
    from app.services.report_service import ReportService
    svc = ReportService()
    result = await svc.generate_boss_daily(stat_date, db, force=force)
    return ApiResponse.ok(data=result, message="老板日报生成成功")

@router.get("/boss-daily/{report_date}", response_model=ApiResponse)
async def get_boss_daily(
    report_date: str,
    current_user: SysUser = Depends(require_permission("dashboard:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """获取指定日期老板日报"""
    from app.services.report_service import ReportService
    svc = ReportService()
    result = await svc._get_existing_report(report_date, db)
    return ApiResponse.ok(data=result)

@router.get("/boss-daily", response_model=ApiResponse)
async def list_boss_daily(
    days: int = 7,
    current_user: SysUser = Depends(require_permission("dashboard:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """获取最近N天日报列表"""
    from sqlalchemy import text
    from datetime import datetime
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)
    r = await db.execute(text("""
        SELECT report_date, total_sales, order_count, gross_margin,
               is_cost_complete, ai_summary, generated_at
        FROM dm.dm_boss_daily_report
        WHERE report_date BETWEEN :start AND :end
        ORDER BY report_date DESC
    """), {"start": start_date, "end": end_date})
    items = [{
        "report_date": str(row[0]),
        "total_sales": float(row[1] or 0),
        "order_count": int(row[2] or 0),
        "gross_margin": float(row[3] or 0),
        "is_cost_complete": bool(row[4]),
        "has_ai_summary": bool(row[5]),
        "generated_at": str(row[6]) if row[6] else None,
    } for row in r.fetchall()]
    return ApiResponse.ok(data={"items": items, "total": len(items)})
