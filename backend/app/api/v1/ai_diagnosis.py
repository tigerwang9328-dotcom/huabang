from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.database import get_db
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.ai_diagnosis_service import AIDiagnosisService


router = APIRouter(prefix="/ai-diagnosis", tags=["AI经营诊断"])


class GenerateTasksRequest(BaseModel):
    stat_date: Optional[str] = None
    store_code: Optional[str] = None
    module: str = "overview"


async def _service(db: AsyncSession) -> AIDiagnosisService:
    return AIDiagnosisService(db)


@router.get("/overview", response_model=ApiResponse)
async def overview(
    stat_date: Optional[str] = Query(None),
    store_code: Optional[str] = Query(None),
    current_user: SysUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = await _service(db)
    return ApiResponse.ok(data=await service.overview(stat_date, store_code))


@router.get("/{module}", response_model=ApiResponse)
async def diagnosis_module(
    module: str,
    stat_date: Optional[str] = Query(None),
    store_code: Optional[str] = Query(None),
    current_user: SysUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = await _service(db)
    return ApiResponse.ok(data=await service.module(module, stat_date, store_code))


@router.post("/action-tasks/generate", response_model=ApiResponse)
async def generate_action_tasks(
    body: GenerateTasksRequest,
    current_user: SysUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = await _service(db)
    data = await service.module(body.module, body.stat_date, body.store_code)
    # 第一阶段只返回建议任务，不直接写入正式任务表，避免 AI 自动派发带来管理风险。
    return ApiResponse.ok(data={"tasks": data.get("action_suggestions", []), "mode": "suggestion_only"}, message="已生成建议任务，需人工确认后派发")
