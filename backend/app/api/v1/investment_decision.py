"""Read and human-registration APIs for investment decisions."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.config import settings
from app.core.database import get_db
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.schemas.investment_decision import (
    InvestmentDecisionRequest,
    InvestmentExecutionRequest,
)
from app.services.investment_decision_service import InvestmentDecisionService


router = APIRouter(prefix="/investment-decisions", tags=["投流决策历史"])


@router.get("/overview", response_model=ApiResponse)
async def overview(
    _current_user: SysUser = Depends(require_permission("dashboard:overview:view")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    data = await InvestmentDecisionService(db).overview(settings.LIFE_DATA_ACCOUNT_ID)
    return ApiResponse.ok(data=data)


@router.get("/history", response_model=ApiResponse)
async def history(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _current_user: SysUser = Depends(require_permission("dashboard:overview:view")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    data = await InvestmentDecisionService(db).history(
        settings.LIFE_DATA_ACCOUNT_ID, limit=limit, offset=offset
    )
    return ApiResponse.ok(data=data)


@router.get("/patterns/daily", response_model=ApiResponse)
async def daily_patterns(
    limit: int = Query(default=30, ge=1, le=90),
    _current_user: SysUser = Depends(require_permission("dashboard:overview:view")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    data = await InvestmentDecisionService(db).daily_patterns(
        settings.LIFE_DATA_ACCOUNT_ID, limit
    )
    return ApiResponse.ok(data=data)


@router.get("/{run_id}", response_model=ApiResponse)
async def detail(
    run_id: int,
    _current_user: SysUser = Depends(require_permission("dashboard:overview:view")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    data = await InvestmentDecisionService(db).detail(settings.LIFE_DATA_ACCOUNT_ID, run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="投流决策不存在")
    return ApiResponse.ok(data=data)


@router.post("/{recommendation_id}/decision", response_model=ApiResponse)
async def record_decision(
    recommendation_id: int,
    body: InvestmentDecisionRequest,
    current_user: SysUser = Depends(require_permission("task:edit")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    data = await InvestmentDecisionService(db).record_decision(
        recommendation_id, int(current_user.id), body
    )
    return ApiResponse.ok(data=data)


@router.post("/{recommendation_id}/execution", response_model=ApiResponse)
async def record_execution(
    recommendation_id: int,
    body: InvestmentExecutionRequest,
    current_user: SysUser = Depends(require_permission("task:edit")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    data = await InvestmentDecisionService(db).record_execution(
        recommendation_id, int(current_user.id), body
    )
    return ApiResponse.ok(data=data)
