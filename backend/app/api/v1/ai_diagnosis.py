from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_permission
from app.core.data_scope import get_data_scope
from app.core.database import get_db
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.ai_diagnosis_service import AIDiagnosisService


router = APIRouter(prefix="/ai-diagnosis", tags=["AI经营诊断"])


class GenerateTasksRequest(BaseModel):
    stat_date: Optional[str] = None
    store_code: Optional[str] = None
    module: str = "overview"


class ConfirmTasksRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    module: str
    diagnosis_ids: list[str] = Field(min_length=1, max_length=50)
    stat_date: Optional[str] = None
    store_code: Optional[str] = None


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


@router.post("/action-tasks/confirm", response_model=ApiResponse)
async def confirm_action_tasks(
    body: ConfirmTasksRequest,
    current_user: SysUser = Depends(require_permission("task:create")),
    db: AsyncSession = Depends(get_db),
):
    scope = await get_data_scope(db, current_user)
    store_code = body.store_code
    if scope.is_limited_store:
        if store_code and store_code not in scope.store_codes:
            raise HTTPException(status_code=403, detail="无权为该门店创建任务")
        if not store_code:
            if len(scope.store_codes) != 1:
                raise HTTPException(status_code=400, detail="请先选择有权限的门店")
            store_code = scope.store_codes[0]
    service = await _service(db)
    try:
        result = await service.confirm_action_tasks(body.module, body.diagnosis_ids, body.stat_date, store_code, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse.ok(data=result, message=f"已创建 {result['created_count']} 个正式任务")
