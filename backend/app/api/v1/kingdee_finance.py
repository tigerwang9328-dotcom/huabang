"""Read-only API for Kingdee historical accounting data."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.kingdee_finance_service import KingdeeFinanceQueryService

router = APIRouter(prefix="/finance", tags=["金蝶历史财务"])


@router.get("/account-sets", response_model=ApiResponse)
async def list_account_sets(
    _current_user: SysUser = Depends(require_permission("finance:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    return ApiResponse.ok(data=await KingdeeFinanceQueryService(db).account_sets())


@router.get("/periods", response_model=ApiResponse)
async def list_periods(
    account_set_code: str,
    _current_user: SysUser = Depends(require_permission("finance:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    return ApiResponse.ok(data=await KingdeeFinanceQueryService(db).periods(account_set_code))


@router.get("/statements", response_model=ApiResponse)
async def get_statements(
    account_set_code: str,
    period: str,
    statement_type: str = Query(pattern="^(balance_sheet|profit|cashflow)$"),
    _current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await KingdeeFinanceQueryService(db).statements(
        account_set_code=account_set_code, period=period, statement_type=statement_type
    )
    return ApiResponse.ok(data=data)


@router.get("/account-balances", response_model=ApiResponse)
async def get_account_balances(
    account_set_code: str,
    period: str,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    return ApiResponse.ok(data=await KingdeeFinanceQueryService(db).account_balances(
        account_set_code=account_set_code, period=period, keyword=keyword,
        page=page, page_size=page_size,
    ))


@router.get("/vouchers", response_model=ApiResponse)
async def list_vouchers(
    account_set_code: str,
    period: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    return ApiResponse.ok(data=await KingdeeFinanceQueryService(db).vouchers(
        account_set_code=account_set_code, period=period, keyword=keyword,
        page=page, page_size=page_size,
    ))


@router.get("/vouchers/{voucher_id}", response_model=ApiResponse)
async def get_voucher(
    voucher_id: int,
    _current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    data = await KingdeeFinanceQueryService(db).voucher_detail(voucher_id)
    return ApiResponse.ok(data=data) if data else ApiResponse.fail("凭证不存在", code=404)


@router.get("/kingdee/import-batches", response_model=ApiResponse)
async def list_import_batches(
    _current_user: SysUser = Depends(require_permission("finance:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    return ApiResponse.ok(data=await KingdeeFinanceQueryService(db).import_batches())


@router.get("/data-quality", response_model=ApiResponse)
async def get_data_quality(
    account_set_code: str | None = None,
    _current_user: SysUser = Depends(require_permission("finance:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    return ApiResponse.ok(data=await KingdeeFinanceQueryService(db).data_quality(account_set_code))
