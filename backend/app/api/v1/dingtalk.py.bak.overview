from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, text
from pydantic import BaseModel
from typing import Optional
from datetime import date, timedelta
from app.core.database import get_db
from app.api.v1.deps import require_permission
from app.models.sys import SysUser, SysDingtalkBind
from app.models.log import LogDingtalkPush
from app.services.dingtalk import DingtalkService
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/dingtalk", tags=["钉钉协同"])


class TestPushRequest(BaseModel):
    dingtalk_user_id: str


class ReportPushRequest(BaseModel):
    stat_date: Optional[str] = None
    user_ids: Optional[list[str]] = None


@router.post("/test-push", response_model=ApiResponse)
async def test_push(
    body: TestPushRequest,
    current_user: SysUser = Depends(require_permission("dingtalk:config")),
    db: AsyncSession = Depends(get_db),
):
    """测试推送（管理员使用）"""
    service = DingtalkService(db)
    result = await service.send_test_message(body.dingtalk_user_id)
    await db.commit()
    return ApiResponse.ok(data=result, message="测试推送已发送，请检查钉钉")


@router.post("/push-daily-report", response_model=ApiResponse)
async def push_daily_report(
    body: ReportPushRequest = ReportPushRequest(),
    current_user: SysUser = Depends(require_permission("dingtalk:config")),
    db: AsyncSession = Depends(get_db),
):
    """手动触发日报推送（stat_date默认昨日，user_ids默认全部启用推送用户）"""
    stat_date = body.stat_date or (date.today() - timedelta(days=1)).isoformat()
    service = DingtalkService(db)

    if body.user_ids:
        user_ids = body.user_ids
    else:
        user_ids = await service.get_push_user_ids()
        if not user_ids:
            return ApiResponse.fail("无启用推送的用户，请先绑定钉钉账号")

    result = await service.send_daily_report(stat_date, user_ids)
    await db.commit()
    return ApiResponse.ok(data=result, message=f"日报推送完成: {result.get('success_count', 0)}/{len(user_ids)}")


@router.get("/scheduler/jobs", response_model=ApiResponse)
async def get_scheduler_jobs(
    current_user: SysUser = Depends(require_permission("system:manage")),
):
    """获取当前调度任务状态（5个时间点）"""
    from app.jobs.scheduler import scheduler
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(next_run) if next_run else None,
            "trigger": str(job.trigger),
        })
    return ApiResponse.ok(data={"jobs": jobs, "total": len(jobs)})


@router.post("/push-log", response_model=ApiResponse)
async def get_push_log(
    page: int = 1,
    page_size: int = 20,
    push_type: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("dingtalk:view")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(LogDingtalkPush).order_by(desc(LogDingtalkPush.pushed_at))
    if push_type:
        stmt = stmt.where(LogDingtalkPush.push_type == push_type)

    result = await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    logs = result.scalars().all()

    return ApiResponse.ok(data={
        "items": [
            {
                "id": l.id,
                "push_type": l.push_type,
                "target_user_id": l.target_user_id,
                "target_user_name": l.target_user_name,
                "message_title": l.message_title,
                "status": l.status,
                "error_message": l.error_message,
                "is_rate_limited": l.is_rate_limited,
                "retry_count": l.retry_count,
                "pushed_at": str(l.pushed_at),
            }
            for l in logs
        ],
        "page": page,
        "page_size": page_size,
    })


@router.get("/push-log", response_model=ApiResponse)
async def get_push_log_get(
    page: int = 1,
    page_size: int = 20,
    push_type: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("dingtalk:view")),
    db: AsyncSession = Depends(get_db),
):
    """推送日志（GET方式）"""
    stmt = select(LogDingtalkPush).order_by(desc(LogDingtalkPush.pushed_at))
    if push_type:
        stmt = stmt.where(LogDingtalkPush.push_type == push_type)

    result = await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    logs = result.scalars().all()

    return ApiResponse.ok(data={
        "items": [
            {
                "id": l.id,
                "push_type": l.push_type,
                "target_user_id": l.target_user_id,
                "message_title": l.message_title,
                "status": l.status,
                "error_message": l.error_message,
                "retry_count": l.retry_count,
                "pushed_at": str(l.pushed_at),
            }
            for l in logs
        ],
        "page": page,
        "page_size": page_size,
    })
