"""财务利润中心API（手工补录 + 预估/核准区分）"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from datetime import date, timedelta
from typing import Optional
from pydantic import BaseModel
from app.core.database import get_db
from app.api.v1.deps import require_permission
from app.models.sys import SysUser
from app.models.dwd import DwdFinanceExpense, DwdFinanceCash
from app.models.dm import DmFinanceProfitDaily
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/finance", tags=["财务利润中心"])

EXPENSE_TYPES = ["rent", "labor", "utilities", "logistics", "admin", "other"]


class ExpenseCreateRequest(BaseModel):
    expense_date: str
    store_code: Optional[str] = None
    expense_type: str
    expense_amount: float
    description: Optional[str] = None
    month_year: Optional[str] = None
    data_type: str = "estimate"  # estimate/actual


class CashCreateRequest(BaseModel):
    record_date: str
    account_type: str = "bank"  # cash/bank
    account_name: Optional[str] = None
    balance: float
    data_type: str = "actual"


@router.post("/manual-expense", response_model=ApiResponse)
async def create_manual_expense(
    body: ExpenseCreateRequest,
    current_user: SysUser = Depends(require_permission("finance:expense:create")),
    db: AsyncSession = Depends(get_db),
):
    """手工录入费用（金蝶未接通时使用）"""
    if body.expense_type not in EXPENSE_TYPES:
        return ApiResponse.fail("费用类型无效，支持: " + ", ".join(EXPENSE_TYPES))
    if body.expense_amount <= 0:
        return ApiResponse.fail("费用金额必须大于0")
    if body.data_type not in ["estimate", "actual"]:
        return ApiResponse.fail("data_type只能是 estimate（预估）或 actual（财务核准）")

    expense = DwdFinanceExpense(
        expense_date=date.fromisoformat(body.expense_date),
        store_code=body.store_code,
        expense_type=body.expense_type,
        expense_amount=body.expense_amount,
        description=body.description,
        data_type=body.data_type,
        month_year=body.month_year or body.expense_date[:7],
        source="manual",
        created_by=current_user.id,
    )
    db.add(expense)
    await db.flush()
    return ApiResponse.ok(
        data={"id": expense.id},
        message=f"费用录入成功（{财务核准 if body.data_type == actual else 预估值}）",
    )


@router.post("/manual-cash", response_model=ApiResponse)
async def create_manual_cash(
    body: CashCreateRequest,
    current_user: SysUser = Depends(require_permission("finance:cash:create")),
    db: AsyncSession = Depends(get_db),
):
    """手工录入现金/银行余额"""
    if body.account_type not in ["cash", "bank"]:
        return ApiResponse.fail("account_type只能是 cash 或 bank")

    cash = DwdFinanceCash(
        record_date=date.fromisoformat(body.record_date),
        account_type=body.account_type,
        account_name=body.account_name,
        balance=body.balance,
        data_type=body.data_type,
        source="manual",
        created_by=current_user.id,
    )
    db.add(cash)
    await db.flush()
    return ApiResponse.ok(data={"id": cash.id}, message="现金余额录入成功")


@router.get("/profit-daily", response_model=ApiResponse)
async def get_profit_daily(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_code: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    """预估/核准利润日报（需要财务权限）"""
    query_end = date.fromisoformat(end_date) if end_date else date.today() - timedelta(days=1)
    query_start = date.fromisoformat(start_date) if start_date else query_end - timedelta(days=29)

    stmt = (
        select(DmFinanceProfitDaily)
        .where(
            DmFinanceProfitDaily.stat_date >= query_start,
            DmFinanceProfitDaily.stat_date <= query_end,
        )
        .order_by(DmFinanceProfitDaily.stat_date)
    )
    if store_code:
        stmt = stmt.where(DmFinanceProfitDaily.store_code == store_code)
    else:
        stmt = stmt.where(DmFinanceProfitDaily.store_code == "ALL")

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return ApiResponse.ok(data={
        "items": [
            {
                "stat_date": str(r.stat_date),
                "net_sales": float(r.net_sales) if r.net_sales else None,
                "gross_profit": float(r.gross_profit) if r.gross_profit else None,
                "gross_margin": float(r.gross_margin) if r.gross_margin else None,
                "total_expense": float(r.total_expense) if r.total_expense else None,
                "operating_profit": float(r.operating_profit) if r.operating_profit else None,
                "data_type": r.data_type,
                "is_cost_complete": r.is_cost_complete,
                "is_expense_complete": r.is_expense_complete,
                "completeness_note": r.completeness_note,
                "data_type_label": "财务核准" if r.data_type == "actual" else "预估值（供参考）",
            }
            for r in rows
        ],
        "data_warning": "部分数据为预估值，以财务核准数据为准",
    })


@router.get("/cash-safety", response_model=ApiResponse)
async def get_cash_safety(
    current_user: SysUser = Depends(require_permission("finance:cash:view")),
    db: AsyncSession = Depends(get_db),
):
    """现金安全天数"""
    # 最新现金余额
    cash_result = await db.execute(
        select(func.sum(DwdFinanceCash.balance))
        .where(DwdFinanceCash.record_date == (
            select(func.max(DwdFinanceCash.record_date)).scalar_subquery()
        ))
    )
    total_cash = cash_result.scalar() or 0

    # 近30天日均支出
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=29)
    expense_result = await db.execute(
        select(func.sum(DwdFinanceExpense.expense_amount))
        .where(
            DwdFinanceExpense.expense_date >= start_date,
            DwdFinanceExpense.expense_date <= end_date,
        )
    )
    total_expense_30d = expense_result.scalar() or 0
    daily_avg_expense = total_expense_30d / 30 if total_expense_30d else None

    cash_safety_days = None
    if daily_avg_expense and daily_avg_expense > 0:
        cash_safety_days = int(float(total_cash) / float(daily_avg_expense))

    return ApiResponse.ok(data={
        "total_cash_balance": float(total_cash),
        "daily_avg_expense_30d": float(daily_avg_expense) if daily_avg_expense else None,
        "cash_safety_days": cash_safety_days,
        "risk_level": (
            "critical" if cash_safety_days and cash_safety_days < 15
            else "warning" if cash_safety_days and cash_safety_days < 30
            else "normal"
        ) if cash_safety_days else "unknown",
        "note": "基于手工录入费用计算，仅供参考",
    })
