from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_permission
from app.core.data_scope import get_data_scope
from app.core.database import get_db
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.ai_diagnosis_service import AIDiagnosisService
from app.services.ai_business_advice_service import BUSINESS_ADVICE_MODULES, BusinessAdviceService
from app.core.redis import rate_limit_check
from app.core.config import settings
from app.core.store_whitelist import ALLOWED_STORE_CODES


router = APIRouter(prefix="/ai-diagnosis", tags=["AI经营诊断"])


class GenerateTasksRequest(BaseModel):
    stat_date: Optional[str] = None
    store_code: Optional[str] = None
    module: str = "overview"


class ConfirmTasksRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    module: str
    diagnosis_ids: Optional[list[str]] = Field(default=None, min_length=1, max_length=50)
    suggestion_key: Optional[str] = Field(default=None, min_length=8, max_length=128)
    assignee_id: int = Field(gt=0)
    due_date: date
    stat_date: Optional[str] = None
    store_code: Optional[str] = None

    @model_validator(mode="after")
    def validate_source(self):
        if not self.suggestion_key and not self.diagnosis_ids:
            raise ValueError("suggestion_key 与 diagnosis_ids 至少提供一个")
        return self


async def _service(db: AsyncSession) -> AIDiagnosisService:
    return AIDiagnosisService(db)


async def _resolve_store_scope(
    db: AsyncSession, current_user: SysUser, store_code: Optional[str]
) -> tuple[Optional[str], object]:
    if store_code and store_code not in ALLOWED_STORE_CODES:
        raise HTTPException(status_code=400, detail="门店不在七家销售门店白名单内")
    scope = await get_data_scope(db, current_user)
    if not scope.is_limited_store:
        return store_code, scope
    if store_code:
        if store_code not in scope.store_codes:
            raise HTTPException(status_code=403, detail="无权访问该门店经营建议")
        return store_code, scope
    if len(scope.store_codes) == 1:
        return scope.store_codes[0], scope
    if not scope.store_codes:
        raise HTTPException(status_code=403, detail="账号尚未绑定有效销售门店")
    raise HTTPException(status_code=400, detail="请先选择有权限的门店")


def _validate_module(module: str) -> None:
    if module not in BUSINESS_ADVICE_MODULES:
        raise HTTPException(status_code=404, detail="未知经营分析模块")


@router.get("/overview", response_model=ApiResponse)
async def overview(
    stat_date: Optional[str] = Query(None),
    store_code: Optional[str] = Query(None),
    current_user: SysUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    store_code, _scope = await _resolve_store_scope(db, current_user, store_code)
    service = await _service(db)
    payload = await service.overview(stat_date, store_code)
    advice = BusinessAdviceService(db)
    return ApiResponse.ok(data=await advice.attach_cached(payload, "overview", stat_date, store_code))


@router.get("/advice/status", response_model=ApiResponse)
async def advice_status(
    stat_date: Optional[str] = Query(None),
    current_user: SysUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    advice = BusinessAdviceService(db)
    dt = date.fromisoformat(stat_date) if stat_date else await advice.latest_stat_date()
    scope = await get_data_scope(db, current_user)
    allowed_scopes = None
    if scope.is_limited_store:
        allowed_scopes = tuple(("store", code) for code in scope.store_codes)
    return ApiResponse.ok(data=await advice.status(dt, allowed_scopes=allowed_scopes))


@router.post("/{module}/refresh", response_model=ApiResponse)
async def refresh_advice(
    module: str,
    stat_date: Optional[str] = Query(None),
    store_code: Optional[str] = Query(None),
    current_user: SysUser = Depends(require_permission("task:create")),
    db: AsyncSession = Depends(get_db),
):
    _validate_module(module)
    store_code, _scope = await _resolve_store_scope(db, current_user, store_code)
    advice = BusinessAdviceService(db)
    dt = date.fromisoformat(stat_date) if stat_date else await advice.latest_stat_date()
    scope_type = "store" if store_code else "company"
    target_code = store_code or "company"
    existing = await advice.latest_snapshot(module, dt, scope_type, target_code)
    if existing and existing.generated_at:
        generated_at = existing.generated_at
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - generated_at.astimezone(timezone.utc)).total_seconds()
        if age_seconds < settings.AI_BUSINESS_ADVICE_REFRESH_WINDOW_SECONDS:
            raise HTTPException(status_code=429, detail="十分钟内请勿重复刷新同一经营建议")
    key = f"ai_advice_refresh:{module}:{scope_type}:{target_code}"
    allowed = await rate_limit_check(key, 1, settings.AI_BUSINESS_ADVICE_REFRESH_WINDOW_SECONDS)
    if not allowed:
        raise HTTPException(status_code=429, detail="十分钟内请勿重复刷新同一经营建议")
    result = await advice.generate_unit(
        module, dt, scope_type, target_code, force=True,
    )
    snapshot = result["snapshot"]
    return ApiResponse.ok(data={
        "cached": result["cached"],
        "mode": snapshot.mode,
        "model_name": snapshot.model_name,
        "generated_at": snapshot.generated_at,
    })


@router.get("/assignee-options", response_model=ApiResponse)
async def assignee_options(
    store_code: Optional[str] = Query(None),
    current_user: SysUser = Depends(require_permission("task:create")),
    db: AsyncSession = Depends(get_db),
):
    store_code, _scope = await _resolve_store_scope(db, current_user, store_code)
    rows = (await db.execute(text("""
        select u.id, coalesce(u.real_name,u.username) label,
               coalesce(array_remove(array_agg(distinct coalesce(us.store_code,nullif(u.store_code,''))),null),
                        array[]::varchar[]) store_codes,
               coalesce(array_remove(array_agg(distinct r.code),null),array[]::varchar[]) role_codes
        from sys.sys_user u
        left join sys.sys_user_store us on us.user_id=u.id
        left join sys.sys_user_role ur on ur.user_id=u.id
        left join sys.sys_role r on r.id=ur.role_id and r.status=1
        where u.status=1 and u.is_deleted=false
          and (:store_code='' or u.store_code=:store_code or exists (
              select 1 from sys.sys_user_store scoped
              where scoped.user_id=u.id and scoped.store_code=:store_code
          ))
        group by u.id,u.real_name,u.username
        order by label,u.id
    """), {"store_code": store_code or ""})).mappings().all()
    return ApiResponse.ok(data=[dict(row) for row in rows])


@router.get("/{module}", response_model=ApiResponse)
async def diagnosis_module(
    module: str,
    stat_date: Optional[str] = Query(None),
    store_code: Optional[str] = Query(None),
    current_user: SysUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_module(module)
    store_code, _scope = await _resolve_store_scope(db, current_user, store_code)
    service = await _service(db)
    payload = await service.module(module, stat_date, store_code)
    return ApiResponse.ok(data=await BusinessAdviceService(db).attach_cached(
        payload, module, stat_date, store_code,
    ))


@router.post("/action-tasks/generate", response_model=ApiResponse)
async def generate_action_tasks(
    body: GenerateTasksRequest,
    current_user: SysUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_module(body.module)
    store_code, _scope = await _resolve_store_scope(db, current_user, body.store_code)
    service = await _service(db)
    data = await service.module(body.module, body.stat_date, store_code)
    # 第一阶段只返回建议任务，不直接写入正式任务表，避免 AI 自动派发带来管理风险。
    return ApiResponse.ok(data={"tasks": data.get("action_suggestions", []), "mode": "suggestion_only"}, message="已生成建议任务，需人工确认后派发")


@router.post("/action-tasks/confirm", response_model=ApiResponse)
async def confirm_action_tasks(
    body: ConfirmTasksRequest,
    current_user: SysUser = Depends(require_permission("task:create")),
    db: AsyncSession = Depends(get_db),
):
    _validate_module(body.module)
    store_code, _scope = await _resolve_store_scope(db, current_user, body.store_code)
    service = await _service(db)
    try:
        result = await service.confirm_action_tasks(
            body.module, body.diagnosis_ids or [], body.stat_date, store_code,
            current_user, suggestion_key=body.suggestion_key,
            assignee_id=body.assignee_id, due_date=body.due_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse.ok(data=result, message=f"已创建 {result['created_count']} 个正式任务，已进入待处理")
