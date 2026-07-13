"""Authenticated read API for LifeData investment optimization."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.config import settings
from app.core.database import get_db
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.life_data_analysis_service import get_investment_overview

router = APIRouter(prefix="/life-data-analysis", tags=["投流优化"])


@router.get("/overview", response_model=ApiResponse)
async def overview(
    _current_user: SysUser = Depends(require_permission("dashboard:overview:view")),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    data = await get_investment_overview(db, settings.LIFE_DATA_ACCOUNT_ID)
    return ApiResponse.ok(data=data)
