"""财务管理 API（数据来自钉钉审批解析的 finance_expense_records / approval_instances）。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.models.sys import SysUser
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/finance", tags=["财务管理"])


def _f(v):
    return float(v) if v is not None else 0.0


def _i(v):
    return int(v) if v is not None else 0


@router.get("/overview", response_model=ApiResponse)
async def finance_overview(
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """财务汇总：今日/本月 报销与付款金额、待审批、已审批未付款、最近记录、部门排行。"""
    amt = (await db.execute(text("""
        SELECT
          coalesce(sum(amount) FILTER (WHERE category='reimbursement' AND expense_date = current_date),0) AS today_reimb,
          coalesce(sum(amount) FILTER (WHERE category='reimbursement' AND expense_date >= date_trunc('month',now())::date),0) AS month_reimb,
          coalesce(sum(amount) FILTER (WHERE category='payment' AND expense_date = current_date),0) AS today_pay,
          coalesce(sum(amount) FILTER (WHERE category='payment' AND expense_date >= date_trunc('month',now())::date),0) AS month_pay,
          count(*) FILTER (WHERE category='payment' AND coalesce(payment_status,'') <> 'paid') AS approved_unpaid
        FROM finance_expense_records
    """))).mappings().first()

    pending = (await db.execute(text("""
        SELECT count(*) FROM dingtalk_approval_instances
        WHERE category IN ('reimbursement','payment') AND status IN ('NEW','RUNNING')
    """))).scalar()

    recent = (await db.execute(text("""
        SELECT applicant_name, department_name, expense_type, amount, category,
               approval_status, payment_status, expense_date, created_at
        FROM finance_expense_records ORDER BY id DESC LIMIT 10
    """))).mappings().all()

    dept_rank = (await db.execute(text("""
        SELECT coalesce(department_name,'未知') AS dept, coalesce(sum(amount),0) AS total
        FROM finance_expense_records
        WHERE expense_date >= date_trunc('month',now())::date
        GROUP BY department_name ORDER BY total DESC LIMIT 10
    """))).mappings().all()

    return ApiResponse.ok(data={
        "today": {"reimbursement_amount": _f(amt["today_reimb"]), "payment_amount": _f(amt["today_pay"])},
        "month": {"reimbursement_amount": _f(amt["month_reimb"]), "payment_amount": _f(amt["month_pay"])},
        "pending_count": _i(pending),
        "approved_unpaid_count": _i(amt["approved_unpaid"]),
        "recent_records": [
            {"applicant_name": r["applicant_name"], "department_name": r["department_name"],
             "expense_type": r["expense_type"], "amount": _f(r["amount"]), "category": r["category"],
             "approval_status": r["approval_status"], "payment_status": r["payment_status"],
             "expense_date": str(r["expense_date"]) if r["expense_date"] else None,
             "created_at": r["created_at"].isoformat() if r["created_at"] else None}
            for r in recent
        ],
        "department_rank": [{"department": r["dept"], "amount": _f(r["total"])} for r in dept_rank],
    })


async def _expense_list(db, category, page, page_size):
    where = "" if not category else "WHERE category = :cat"
    params = {"limit": page_size, "offset": (page - 1) * page_size}
    if category:
        params["cat"] = category
    total = (await db.execute(text(f"SELECT count(*) FROM finance_expense_records {where}"),
                              params)).scalar()
    rows = (await db.execute(text(f"""
        SELECT id, applicant_name, department_name, expense_type, amount, category,
               approval_status, payment_status, expense_date, created_at
        FROM finance_expense_records {where}
        ORDER BY id DESC LIMIT :limit OFFSET :offset
    """), params)).mappings().all()
    items = [{"id": r["id"], "applicant_name": r["applicant_name"], "department_name": r["department_name"],
              "expense_type": r["expense_type"], "amount": _f(r["amount"]), "category": r["category"],
              "approval_status": r["approval_status"], "payment_status": r["payment_status"],
              "expense_date": str(r["expense_date"]) if r["expense_date"] else None,
              "created_at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows]
    return {"items": items, "total": _i(total), "page": page, "page_size": page_size}


@router.get("/expenses", response_model=ApiResponse)
async def finance_expenses(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                           current_user: SysUser = Depends(require_permission("dashboard:view")),
                           db: AsyncSession = Depends(get_db)):
    return ApiResponse.ok(data=await _expense_list(db, None, page, page_size))


@router.get("/reimbursements", response_model=ApiResponse)
async def finance_reimbursements(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                                 current_user: SysUser = Depends(require_permission("dashboard:view")),
                                 db: AsyncSession = Depends(get_db)):
    return ApiResponse.ok(data=await _expense_list(db, "reimbursement", page, page_size))


@router.get("/payments", response_model=ApiResponse)
async def finance_payments(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                           current_user: SysUser = Depends(require_permission("dashboard:view")),
                           db: AsyncSession = Depends(get_db)):
    return ApiResponse.ok(data=await _expense_list(db, "payment", page, page_size))
