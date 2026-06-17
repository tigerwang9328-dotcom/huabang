from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.api.v1.deps import require_permission
from app.models.sys import SysUser, SysDingtalkBind
from app.models.log import LogDingtalkPush
from app.services.dingtalk import DingtalkService
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/dingtalk", tags=["钉钉协同"])


class TestPushRequest(BaseModel):
    dingtalk_user_id: str


@router.post("/test-push", response_model=ApiResponse)
async def test_push(
    body: TestPushRequest,
    current_user: SysUser = Depends(require_permission("dingtalk:config")),
    db: AsyncSession = Depends(get_db),
):
    """测试推送（管理员使用）"""
    service = DingtalkService(db)
    result = await service.send_test_message(body.dingtalk_user_id)
    return ApiResponse.ok(data=result, message="测试推送已发送，请检查钉钉")


@router.get("/push-log", response_model=ApiResponse)
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
                "pushed_at": str(l.pushed_at),
            }
            for l in logs
        ],
        "page": page,
        "page_size": page_size,
    })
