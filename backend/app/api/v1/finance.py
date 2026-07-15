"""财务利润中心API（手工补录 + 预估/核准区分）"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from pydantic import BaseModel
from app.core.database import get_db
from app.api.v1.deps import require_permission
from app.models.sys import SysUser
from app.models.dwd import DwdFinanceExpense, DwdFinanceCash
from app.models.dm import DmFinanceProfitDaily
from app.schemas.common import ApiResponse
from app.core.store_whitelist import ALLOWED_STORE_CODES, ALLOWED_INVENTORY_CODES
from app.services.profit_service import ExpenseAllocation, REQUIRED_EXPENSE_TYPES, calculate_profit

router = APIRouter(prefix="/finance", tags=["财务利润中心"])

EXPENSE_TYPES = [
    "rent", "wages", "social_security", "platform_fee",
    "utilities", "logistics", "marketing", "other",
]

EXPENSE_LABELS = {
    "rent": "租金", "wages": "工资", "social_security": "社保",
    "platform_fee": "平台费", "utilities": "水电", "logistics": "物流",
    "marketing": "营销", "other": "其他",
}


def _money(value):
    return float(value) if value is not None else None


def _profit_payload(result):
    return {
        "net_sales": _money(result.net_sales),
        "cost_of_goods": _money(result.cost_of_goods),
        "gross_profit": _money(result.gross_profit),
        "gross_margin": _money(result.gross_margin),
        "gross_profit_status": result.gross_profit_status,
        "total_expense": _money(result.total_expense),
        "expense_coverage_rate": _money(result.expense_coverage_rate),
        "operating_profit": _money(result.operating_profit),
        "operating_margin": _money(result.operating_margin),
        "operating_profit_status": result.operating_profit_status,
        "finance_approved": result.finance_approved,
        "reasons": list(result.reasons),
    }


class ExpenseCreateRequest(BaseModel):
    expense_date: str
    store_code: Optional[str] = None
    expense_type: str
    expense_amount: float
    description: Optional[str] = None
    month_year: Optional[str] = None
    allocation_start: Optional[str] = None
    allocation_end: Optional[str] = None
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
    if body.expense_amount < 0:
        return ApiResponse.fail("费用金额不能小于0")
    if body.data_type != "estimate":
        return ApiResponse.fail("费用录入不能直接标记财务核准，请录入后由财务负责人核准")
    normalized_store = (body.store_code or "").strip().upper()
    if normalized_store and normalized_store != "ALL" and normalized_store not in ALLOWED_STORE_CODES:
        return ApiResponse.fail("门店编码不在7家销售门店范围内")

    expense_date = date.fromisoformat(body.expense_date)
    allocation_start = date.fromisoformat(body.allocation_start) if body.allocation_start else expense_date
    allocation_end = date.fromisoformat(body.allocation_end) if body.allocation_end else allocation_start
    if allocation_end < allocation_start:
        return ApiResponse.fail("费用归属结束日期不能早于开始日期")

    expense = DwdFinanceExpense(
        expense_date=expense_date,
        store_code=None if normalized_store in ("", "ALL") else normalized_store,
        expense_type=body.expense_type,
        expense_amount=body.expense_amount,
        description=body.description,
        data_type="estimate",
        month_year=body.month_year or body.expense_date[:7],
        allocation_start=allocation_start,
        allocation_end=allocation_end,
        source="manual",
        created_by=current_user.id,
    )
    db.add(expense)
    await db.flush()
    return ApiResponse.ok(
        data={"id": expense.id},
        message="费用录入成功（待财务核准）",
    )


@router.post("/expenses/{expense_id}/approve", response_model=ApiResponse)
async def approve_manual_expense(
    expense_id: int,
    current_user: SysUser = Depends(require_permission("finance:expense:approve")),
    db: AsyncSession = Depends(get_db),
):
    """Approve one expense with an independent finance permission and audit trail."""
    expense = await db.get(DwdFinanceExpense, expense_id)
    if expense is None:
        return ApiResponse.fail("费用记录不存在")
    expense.data_type = "actual"
    expense.approved_by = current_user.id
    expense.approved_at = datetime.now(timezone.utc)
    await db.flush()
    return ApiResponse.ok(data={"id": expense.id}, message="费用已财务核准")


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
                "net_sales": float(r.net_sales) if r.net_sales is not None else None,
                "gross_profit": float(r.gross_profit) if r.gross_profit is not None else None,
                "gross_margin": float(r.gross_margin) if r.gross_margin is not None else None,
                "total_expense": float(r.total_expense) if r.total_expense is not None else None,
                "operating_profit": (
                    float(r.operating_profit)
                    if r.operating_profit is not None
                    else None
                ),
                "status": getattr(r, "operating_profit_status", None) or (
                    "ready" if r.is_cost_complete and r.is_expense_complete
                    and getattr(r, "finance_approved", False) else "estimated"
                ),
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


@router.get("/profit-analysis", response_model=ApiResponse)
async def get_profit_analysis(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_code: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("finance:profit:view")),
    db: AsyncSession = Depends(get_db),
):
    """Traceable gross-profit analysis with a hard gate for operating profit."""
    query_end = date.fromisoformat(end_date) if end_date else date.today() - timedelta(days=1)
    query_start = date.fromisoformat(start_date) if start_date else query_end
    if query_end < query_start:
        return ApiResponse.fail("结束日期不能早于开始日期")
    if store_code and store_code.upper() not in ALLOWED_STORE_CODES:
        return ApiResponse.fail("门店编码不在7家销售门店范围内")
    selected_codes = [store_code.upper()] if store_code else sorted(ALLOWED_STORE_CODES)

    store_rows = (await db.execute(text("""
        SELECT s.store_code, COALESCE(MAX(ds.store_name), s.store_code) store_name,
               COALESCE(SUM(net_sales_amount),0) net_sales,
               COALESCE(SUM(cost_amount),0) cost_of_goods,
               COALESCE(SUM(gross_profit),0) gross_profit,
               COALESCE(SUM(tag_amount),0) tag_amount,
               COALESCE(SUM(sales_amount),0) sales_amount,
               COALESCE(SUM(return_amount),0) return_amount,
               BOOL_AND(COALESCE(is_cost_complete,false)) is_cost_complete,
               MAX(etl_at) source_updated_at
        FROM dws.dws_store_daily s
        LEFT JOIN dim.dim_store ds ON ds.store_code=s.store_code AND ds.source_system='baison'
        WHERE stat_date BETWEEN :start_date AND :end_date
          AND s.store_code=ANY(:store_codes)
        GROUP BY s.store_code ORDER BY net_sales DESC
    """), {"start_date": query_start, "end_date": query_end, "store_codes": selected_codes})).mappings().all()

    expense_rows = (await db.execute(text("""
        SELECT expense_type, expense_amount, data_type, store_code,
               COALESCE(allocation_start, expense_date) allocation_start,
               COALESCE(allocation_end, expense_date) allocation_end,
               updated_at
        FROM dwd.dwd_finance_expense
        WHERE COALESCE(allocation_start, expense_date) <= :end_date
          AND COALESCE(allocation_end, expense_date) >= :start_date
          AND (store_code IS NULL OR UPPER(store_code)='ALL' OR UPPER(store_code)=ANY(:store_codes))
    """), {"start_date": query_start, "end_date": query_end, "store_codes": selected_codes})).mappings().all()

    def allocations(rows):
        return [ExpenseAllocation(
            expense_type=str(row["expense_type"]), amount=row["expense_amount"],
            allocation_start=row["allocation_start"], allocation_end=row["allocation_end"],
            data_type=str(row["data_type"] or "estimate"),
            store_code=row["store_code"],
        ) for row in rows]

    total_sales = sum((row["net_sales"] for row in store_rows), 0)
    total_cost = sum((row["cost_of_goods"] for row in store_rows), 0)
    cost_complete = bool(store_rows) and all(bool(row["is_cost_complete"]) for row in store_rows)
    coverage_row = (await db.execute(text("""
        SELECT COALESCE(
                   SUM(ABS(sales_quantity)) FILTER (
                       WHERE COALESCE(is_cost_complete, false)
                   )::numeric / NULLIF(SUM(ABS(sales_quantity)), 0),
                   0
               ) AS coverage_rate
        FROM dws.dws_product_daily
        WHERE stat_date BETWEEN :start_date AND :end_date
          AND store_code=ANY(:store_codes)
    """), {
        "start_date": query_start,
        "end_date": query_end,
        "store_codes": selected_codes,
    })).mappings().one()
    standard_purchase_price_coverage_rate = float(
        coverage_row["coverage_rate"] or 0
    )
    company_profit = calculate_profit(
        period_start=query_start, period_end=query_end,
        net_sales=total_sales, cost_of_goods=total_cost,
        is_cost_complete=cost_complete, expenses=allocations(expense_rows),
    )
    stores = []
    for row in store_rows:
        direct_expenses = [e for e in expense_rows if str(e["store_code"] or "").upper() == row["store_code"].upper()]
        profit = calculate_profit(
            period_start=query_start, period_end=query_end,
            net_sales=row["net_sales"], cost_of_goods=row["cost_of_goods"],
            is_cost_complete=bool(row["is_cost_complete"]), expenses=allocations(direct_expenses),
            expense_scope=row["store_code"],
        )
        store_payload = _profit_payload(profit)
        # Headquarters expenses have no accepted store-allocation policy yet.
        store_payload.update({"operating_profit": None, "operating_margin": None,
                              "operating_profit_status": "pending_data"})
        stores.append({
            "store_code": row["store_code"], "store_name": row["store_name"],
            **store_payload,
        })

    products = (await db.execute(text("""
        SELECT p.product_code, COALESCE(MAX(dp.product_name), p.product_code) product_name,
               COALESCE(SUM(p.net_sales_amount),0) net_sales,
               COALESCE(SUM(p.cost_amount),0) cost_of_goods,
               COALESCE(SUM(p.gross_profit),0) gross_profit,
               CASE WHEN SUM(p.net_sales_amount)>0 THEN SUM(p.gross_profit)/SUM(p.net_sales_amount) END gross_margin,
               BOOL_AND(COALESCE(p.is_cost_complete,false)) is_cost_complete
        FROM dws.dws_product_daily p
        LEFT JOIN dim.dim_product dp ON dp.product_code=p.product_code AND dp.source_system='baison'
        WHERE p.stat_date BETWEEN :start_date AND :end_date AND p.store_code=ANY(:store_codes)
        GROUP BY p.product_code ORDER BY net_sales DESC LIMIT 100
    """), {"start_date": query_start, "end_date": query_end, "store_codes": selected_codes})).mappings().all()
    product_items = [{
        "product_code": row["product_code"], "product_name": row["product_name"],
        "net_sales": _money(row["net_sales"]), "cost_of_goods": _money(row["cost_of_goods"]),
        "gross_profit": _money(row["gross_profit"]), "gross_margin": _money(row["gross_margin"]),
        "gross_profit_status": "ready" if row["is_cost_complete"] else "estimated",
        "operating_profit": None, "operating_profit_status": "pending_data",
    } for row in products]

    inventory_amount = (await db.execute(text("""
        SELECT COALESCE(SUM(total_cost_amount),0) FROM dws.dws_inventory_daily
        WHERE stat_date=(SELECT MAX(stat_date) FROM dws.dws_inventory_daily WHERE stat_date<=:end_date)
          AND UPPER(store_code)=ANY(:inventory_codes)
    """), {"end_date": query_end, "inventory_codes": sorted(ALLOWED_INVENTORY_CODES)})).scalar()
    tag_amount = sum((row["tag_amount"] for row in store_rows), 0)
    sales_amount = sum((row["sales_amount"] for row in store_rows), 0)
    expense_by_type = company_profit.expense_by_type
    summary_payload = _profit_payload(company_profit)
    if store_code:
        summary_payload.update({
            "operating_profit": None,
            "operating_margin": None,
            "operating_profit_status": "pending_data",
            "finance_approved": False,
            "reasons": [*summary_payload["reasons"], "headquarters_allocation_pending"],
        })
    source_updated_at = max((row["source_updated_at"] for row in store_rows if row["source_updated_at"]), default=None)
    return ApiResponse.ok(data={
        "period": {"start_date": str(query_start), "end_date": str(query_end)},
        "status": summary_payload["operating_profit_status"],
        "status_label": (
            "已核准"
            if summary_payload["operating_profit_status"] == "ready"
            else "估算值，费用尚未完整接入"
            if summary_payload["operating_profit_status"] == "estimated"
            else "待接入"
        ),
        "summary": {
            **summary_payload,
            "standard_purchase_price_coverage_rate": standard_purchase_price_coverage_rate,
            # Deprecated compatibility alias; new clients use standard_purchase_price_coverage_rate.
            "cost_coverage_rate": standard_purchase_price_coverage_rate,
            "inventory_amount": _money(inventory_amount),
            "discount_loss": _money(max(tag_amount - sales_amount, 0)),
            "return_loss": None,
            "clearance_loss": None,
        },
        "expense_coverage": [{
            "expense_type": expense_type, "label": EXPENSE_LABELS[expense_type],
            "amount": _money(expense_by_type[expense_type]),
            "status": "ready" if expense_type not in company_profit.missing_expense_types else "pending_data",
            "approved": company_profit.finance_approved and expense_type not in company_profit.missing_expense_types,
        } for expense_type in REQUIRED_EXPENSE_TYPES],
        "missing_expense_types": list(company_profit.missing_expense_types),
        "stores": stores,
        "products": product_items,
        "salespersons": {"status": "pending_data", "items": [], "reason": "业绩归属来源待接入"},
        "vip_profit": {"status": "pending_data", "items": [], "reason": "会员级销售成本与费用归属待接入"},
        "data_quality": {
            "warnings": [
                "退货损失缺少可靠退货明细，暂不计算",
                "清仓损失缺少清仓标识，暂不计算",
                "门店经营利润等待总部费用分摊规则",
            ] + (["费用或标准进价覆盖不完整，经营利润仅为估算值"]
                 if company_profit.operating_profit_status == "estimated" else []),
            "source_updated_at": source_updated_at.isoformat() if source_updated_at else None,
        },
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
