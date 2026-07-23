"""
报表中心扩展 - 应收明细/应付明细/费用明细/税金明细
====================================================
对标虎狼 /reports/receivable-detail、/reports/payable-detail、
/reports/expense-detail、/reports/tax-detail
"""
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.api.v1.deps import get_db, get_current_user
from app.models.sys import SysUser as User
from app.models.finance.business import FinRecvOrder, FinPayableOrder
from app.models.finance.accounting import FinLedgerBalance, FinAccount
from app.models.finance.tax import FinTaxRecord, FinTaxType

router = APIRouter(prefix="/finance")


# ═══════════════════════════════════════════════════════════
# 1. 应收明细报表
#    来源：fin_recv_orders（按客户/期间过滤，含运行余额）
# ═══════════════════════════════════════════════════════════

@router.get("/reports/receivable-detail")
async def report_receivable_detail(
    book_id: int = Query(1),
    period: Optional[str] = Query(None, description="YYYY-MM，空则查所有未结清"),
    customer_name: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """
    应收明细台账：按客户分组，每行一张应收单，展示
    应收金额、已回款、余额、账龄、状态，尾部附汇总。
    """
    q = select(FinRecvOrder).where(FinRecvOrder.book_id == book_id)
    if period:
        q = q.where(FinRecvOrder.period == period)
    if customer_name:
        q = q.where(FinRecvOrder.customer_name.ilike(f"%{customer_name}%"))
    if status:
        q = q.where(FinRecvOrder.status == status)
    q = q.order_by(FinRecvOrder.customer_name, FinRecvOrder.order_date, FinRecvOrder.id)
    result = await db.execute(q)
    orders = result.scalars().all()

    today = date.today()
    rows = []
    # 按客户计算运行余额
    customer_running: dict[str, float] = {}
    for o in orders:
        balance = float(o.total_amount or 0) - float(o.received_amount or 0)
        cname = o.customer_name or "（无名称）"
        customer_running[cname] = customer_running.get(cname, 0.0) + balance
        days = (today - o.order_date).days if o.order_date else 0
        rows.append({
            "id": o.id,
            "order_no": o.order_no,
            "order_date": str(o.order_date) if o.order_date else "",
            "period": o.period,
            "customer_name": cname,
            "total_amount": float(o.total_amount or 0),
            "received_amount": float(o.received_amount or 0),
            "balance": round(balance, 2),
            "customer_balance": round(customer_running[cname], 2),
            "days_outstanding": days,
            "status": o.status,
            "remark": o.remark or "",
        })

    total_amount   = sum(r["total_amount"]   for r in rows)
    total_received = sum(r["received_amount"] for r in rows)
    total_balance  = sum(r["balance"]         for r in rows)

    return {
        "rows": rows,
        "summary": {
            "total_amount":   round(total_amount,   2),
            "total_received": round(total_received, 2),
            "total_balance":  round(total_balance,  2),
            "order_count":    len(rows),
        },
        "by_customer": [
            {"customer_name": k, "balance": round(v, 2)}
            for k, v in sorted(customer_running.items(), key=lambda x: -abs(x[1]))
        ],
    }


# ═══════════════════════════════════════════════════════════
# 2. 应付明细报表
#    来源：fin_payable_orders（按供应商/期间过滤，含运行余额）
# ═══════════════════════════════════════════════════════════

@router.get("/reports/payable-detail")
async def report_payable_detail(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    supplier_name: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """
    应付明细台账：按供应商分组，每行一张应付单，展示
    应付金额、已付款、余额、账龄、状态。
    """
    q = select(FinPayableOrder).where(FinPayableOrder.book_id == book_id)
    if period:
        q = q.where(FinPayableOrder.period == period)
    if supplier_name:
        q = q.where(FinPayableOrder.supplier_name.ilike(f"%{supplier_name}%"))
    if status:
        q = q.where(FinPayableOrder.status == status)
    q = q.order_by(FinPayableOrder.supplier_name, FinPayableOrder.order_date, FinPayableOrder.id)
    result = await db.execute(q)
    orders = result.scalars().all()

    today = date.today()
    rows = []
    supplier_running: dict[str, float] = {}
    for o in orders:
        balance = float(o.total_amount or 0) - float(o.paid_amount or 0)
        sname = o.supplier_name or "（无名称）"
        supplier_running[sname] = supplier_running.get(sname, 0.0) + balance
        days = (today - o.order_date).days if o.order_date else 0
        rows.append({
            "id": o.id,
            "order_no": o.order_no,
            "order_date": str(o.order_date) if o.order_date else "",
            "period": o.period,
            "supplier_name": sname,
            "total_amount": float(o.total_amount or 0),
            "paid_amount": float(o.paid_amount or 0),
            "balance": round(balance, 2),
            "supplier_balance": round(supplier_running[sname], 2),
            "days_outstanding": days,
            "status": o.status,
            "remark": o.remark or "",
        })

    total_amount = sum(r["total_amount"] for r in rows)
    total_paid   = sum(r["paid_amount"]  for r in rows)
    total_balance = sum(r["balance"]     for r in rows)

    return {
        "rows": rows,
        "summary": {
            "total_amount":  round(total_amount,  2),
            "total_paid":    round(total_paid,    2),
            "total_balance": round(total_balance, 2),
            "order_count":   len(rows),
        },
        "by_supplier": [
            {"supplier_name": k, "balance": round(v, 2)}
            for k, v in sorted(supplier_running.items(), key=lambda x: -abs(x[1]))
        ],
    }


# ═══════════════════════════════════════════════════════════
# 3. 费用明细表
#    来源：fin_ledger_balances WHERE account_type='expense'
#    按期间聚合，展示每个费用科目当月发生额
# ═══════════════════════════════════════════════════════════

@router.get("/reports/expense-detail")
async def report_expense_detail(
    book_id: int = Query(1),
    period: Optional[str] = Query(None, description="YYYY-MM，空则取当月"),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """
    费用明细表：从账簿余额中提取 expense 类科目当期发生额，
    按科目编码排序，对比当月借贷发生额计算净费用。
    """
    if not period:
        period = date.today().strftime("%Y-%m")

    result = await db.execute(
        text("""
            WITH posted AS (
                SELECT vl.account_id,
                       SUM(vl.debit_amount) AS period_debit,
                       SUM(vl.credit_amount) AS period_credit
                FROM fin_voucher_lines vl
                JOIN fin_vouchers v ON v.id = vl.voucher_id
                WHERE v.book_id = :book_id
                  AND v.status = 'posted'
                  AND to_char(v.voucher_date, 'YYYY-MM') = :period
                GROUP BY vl.account_id
            )
            SELECT
                a.account_code,
                a.account_name,
                COALESCE(p.period_debit,  0) AS period_debit,
                COALESCE(p.period_credit, 0) AS period_credit,
                COALESCE(lb.opening_debit, 0) - COALESCE(lb.opening_credit, 0)
                    + COALESCE(p.period_debit, 0) - COALESCE(p.period_credit, 0) AS closing_balance
            FROM fin_accounts a
            LEFT JOIN posted p ON p.account_id = a.id
            LEFT JOIN fin_ledger_balances lb
                ON lb.account_id = a.id AND lb.book_id = :book_id AND lb.period = :period
            WHERE a.book_id = :book_id AND a.account_type = 'expense' AND a.is_active = true
            ORDER BY a.account_code
        """),
        {"book_id": book_id, "period": period},
    )
    rows = []
    total_net = 0.0
    for r in result.mappings():
        debit  = float(r["period_debit"]  or 0)
        credit = float(r["period_credit"] or 0)
        closing = float(r["closing_balance"] or 0)
        net = debit - credit
        rows.append({
            "account_code": r["account_code"],
            "account_name": r["account_name"],
            "period_debit":  round(debit,   2),
            "period_credit": round(credit,  2),
            "net_amount":    round(net,     2),
            "closing_balance": round(closing, 2),
        })
        total_net += net

    # 只返回有发生额的科目（过滤全零行）
    active_rows = [r for r in rows if r["period_debit"] != 0 or r["period_credit"] != 0]
    return {
        "period": period,
        "rows": active_rows,
        "all_rows": rows,   # 含零行，供前端切换显示
        "total_net": round(total_net, 2),
    }


# ═══════════════════════════════════════════════════════════
# 4. 税金明细表
#    双来源：
#    A) fin_ledger_balances WHERE account_code LIKE '2221%'（凭证驱动）
#    B) fin_tax_records（手工税务台账）
# ═══════════════════════════════════════════════════════════

@router.get("/reports/tax-detail")
async def report_tax_detail(
    book_id: int = Query(1),
    period: Optional[str] = Query(None, description="YYYY-MM，空则取当月"),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """
    税金明细表（双视角）：
    - ledger_view：从账簿余额读取 2221 应交税费科目发生额（凭证驱动）
    - tax_records_view：从 fin_tax_records 手工台账汇总（税务模块录入）
    前端可按需展示任一视角。
    """
    if not period:
        period = date.today().strftime("%Y-%m")

    # A. 账簿视角（凭证驱动）
    ledger_result = await db.execute(
        text("""
            WITH posted AS (
                SELECT vl.account_id,
                       SUM(vl.debit_amount) AS period_debit,
                       SUM(vl.credit_amount) AS period_credit
                FROM fin_voucher_lines vl
                JOIN fin_vouchers v ON v.id = vl.voucher_id
                WHERE v.book_id = :book_id
                  AND v.status = 'posted'
                  AND to_char(v.voucher_date, 'YYYY-MM') = :period
                GROUP BY vl.account_id
            )
            SELECT
                a.account_code,
                a.account_name,
                COALESCE(p.period_debit,  0) AS period_debit,
                COALESCE(p.period_credit, 0) AS period_credit,
                COALESCE(lb.opening_credit,0) - COALESCE(lb.opening_debit,0)
                    + COALESCE(p.period_credit,0) - COALESCE(p.period_debit,0) AS balance
            FROM fin_accounts a
            LEFT JOIN posted p ON p.account_id = a.id
            LEFT JOIN fin_ledger_balances lb
                ON lb.account_id = a.id AND lb.book_id = :book_id AND lb.period = :period
            WHERE a.book_id = :book_id AND a.account_code LIKE '2221%' AND a.is_active = true
            ORDER BY a.account_code
        """),
        {"book_id": book_id, "period": period},
    )
    ledger_rows = []
    total_ledger_balance = 0.0
    for r in ledger_result.mappings():
        debit  = float(r["period_debit"]  or 0)
        credit = float(r["period_credit"] or 0)
        balance = float(r["balance"] or 0)
        ledger_rows.append({
            "account_code": r["account_code"],
            "account_name": r["account_name"],
            "period_debit":  round(debit,   2),
            "period_credit": round(credit,  2),
            "balance":       round(balance, 2),
        })
        total_ledger_balance += balance

    # B. 税务台账视角（手工录入）
    tax_result = await db.execute(
        text("""
            SELECT
                tt.tax_name,
                tt.tax_type,
                COALESCE(SUM(tr.tax_amount), 0) AS tax_amount,
                COALESCE(SUM(CASE WHEN tr.status='paid' THEN tr.tax_amount ELSE 0 END), 0) AS paid_amount,
                COALESCE(SUM(CASE WHEN tr.status!='paid' THEN tr.tax_amount ELSE 0 END), 0) AS unpaid_amount
            FROM fin_tax_records tr
            JOIN fin_tax_types tt ON tt.id = tr.tax_type_id
            WHERE tr.book_id = :book_id AND tr.period = :period
            GROUP BY tt.id, tt.tax_name, tt.tax_category
            ORDER BY tt.tax_name
        """),
        {"book_id": book_id, "period": period},
    )
    tax_rows = []
    total_tax_amount = 0.0
    total_unpaid = 0.0
    for r in tax_result.mappings():
        tax_rows.append({
            "tax_name":     r["tax_name"],
            "tax_type":     r["tax_type"],
            "tax_amount":   round(float(r["tax_amount"]   or 0), 2),
            "paid_amount":  round(float(r["paid_amount"]  or 0), 2),
            "unpaid_amount": round(float(r["unpaid_amount"] or 0), 2),
        })
        total_tax_amount += float(r["tax_amount"] or 0)
        total_unpaid     += float(r["unpaid_amount"] or 0)

    return {
        "period": period,
        "ledger_view": {
            "rows": ledger_rows,
            "total_balance": round(total_ledger_balance, 2),
        },
        "tax_records_view": {
            "rows": tax_rows,
            "total_tax_amount": round(total_tax_amount,  2),
            "total_unpaid":     round(total_unpaid,      2),
        },
    }
