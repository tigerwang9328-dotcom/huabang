from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
from app.core.database import get_db
from app.api.v1.deps import require_permission
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from typing import Optional

router = APIRouter(prefix="/rules", tags=["规则引擎"])

@router.post("/run", response_model=ApiResponse)
async def run_rules(
    stat_date: Optional[str] = None,
    store_code: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """手动运行规则引擎"""
    if not stat_date:
        stat_date = (date.today() - timedelta(days=1)).isoformat()
    from app.services.rule_engine import RuleEngine
    engine = RuleEngine()
    result = await engine.run_all(stat_date, db, store_code)
    return ApiResponse.ok(data=result)

@router.get("/results", response_model=ApiResponse)
async def get_rule_results(
    stat_date: Optional[str] = None,
    store_code: Optional[str] = None,
    triggered_only: bool = False,
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """获取规则结果（实时计算）"""
    if not stat_date:
        stat_date = (date.today() - timedelta(days=1)).isoformat()
    from app.services.rule_engine import RuleEngine
    engine = RuleEngine()
    result = await engine.run_all(stat_date, db, store_code)
    if triggered_only:
        result["results"] = [r for r in result["results"] if r["triggered"]]
    return ApiResponse.ok(data=result)

@router.get("/metrics", response_model=ApiResponse)
async def get_metrics(
    stat_date: Optional[str] = None,
    store_code: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """获取经营指标"""
    if not stat_date:
        stat_date = (date.today() - timedelta(days=1)).isoformat()
    from app.services.metrics import MetricsService
    svc = MetricsService()
    result = await svc.get_daily_metrics(stat_date, db, store_code)
    return ApiResponse.ok(data=result)

@router.get("/store-ranking", response_model=ApiResponse)
async def store_ranking(
    stat_date: Optional[str] = None,
    limit: int = Query(default=10, le=50),
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """门店销售排行"""
    if not stat_date:
        stat_date = (date.today() - timedelta(days=1)).isoformat()
    from app.services.metrics import MetricsService
    svc = MetricsService()
    result = await svc.get_store_ranking(stat_date, db, limit)
    return ApiResponse.ok(data=result)

@router.get("/product-ranking", response_model=ApiResponse)
async def product_ranking(
    stat_date: Optional[str] = None,
    limit: int = Query(default=10, le=50),
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """商品销售排行"""
    if not stat_date:
        stat_date = (date.today() - timedelta(days=1)).isoformat()
    from app.services.metrics import MetricsService
    svc = MetricsService()
    result = await svc.get_product_ranking(stat_date, db, limit)
    return ApiResponse.ok(data=result)
