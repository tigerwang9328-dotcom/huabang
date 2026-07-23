"""
报表 + 账簿 + 结账 API
对标虎狼 report_engine.py (StatementEngine / LedgerEngine) + routes.py 结账相关
"""
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select

from app.api.v1.deps import get_db, get_current_user
from app.models.sys import SysUser as User
from app.models.finance.settings import FinAuditLog

router = APIRouter(prefix="/finance")


def _d(v) -> float:
    return float(v) if v else 0.0


# ═══════════════════════════════════════════════════════════
# 总账
# ═══════════════════════════════════════════════════════════

@router.get("/books/general-ledger")
async def general_ledger(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """总账（按科目汇总期初/本期/期末）"""
    if not period:
        today = date.today()
        period = f"{today.year}-{today.month:02d}"

    result = await db.execute(text("""
        WITH posted AS (
            SELECT vl.account_id,
                   SUM(vl.debit_amount) AS period_debit,
                   SUM(vl.credit_amount) AS period_credit
            FROM fin_voucher_lines vl
            JOIN fin_vouchers v ON v.id = vl.voucher_id
            WHERE v.book_id = :bid
              AND v.status = 'posted'
              AND to_char(v.voucher_date, 'YYYY-MM') = :p
            GROUP BY vl.account_id
        )
        SELECT a.account_code, a.account_name, a.direction, a.level,
               COALESCE(lb.opening_debit, 0) - COALESCE(lb.opening_credit, 0) AS opening,
               COALESCE(p.period_debit, 0) AS period_debit,
               COALESCE(p.period_credit, 0) AS period_credit,
               COALESCE(lb.opening_debit, 0) - COALESCE(lb.opening_credit, 0)
                   + COALESCE(p.period_debit, 0) - COALESCE(p.period_credit, 0) AS closing
        FROM fin_accounts a
        LEFT JOIN fin_ledger_balances lb ON lb.account_id = a.id AND lb.period = :p AND lb.book_id = :bid
        LEFT JOIN posted p ON p.account_id = a.id
        WHERE a.book_id = :bid AND a.is_active = true
        ORDER BY a.account_code
    """), {"bid": book_id, "p": period})

    return {
        "from_period": period,
        "rows": [
            {
                "account_code": r["account_code"], "account_name": r["account_name"],
                "direction": "借" if r["direction"] == "debit" else "贷",
                "level": r.get("level", 1),
                "opening": _d(r["opening"]),
                "period_debit": _d(r["period_debit"]),
                "period_credit": _d(r["period_credit"]),
                "closing": _d(r["closing"]),
            }
            for r in result.mappings()
        ],
    }


# ═══════════════════════════════════════════════════════════
# 科目余额表
# ═══════════════════════════════════════════════════════════

@router.get("/books/account-balance")
async def account_balance(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    if not period:
        today = date.today()
        period = f"{today.year}-{today.month:02d}"

    result = await db.execute(text("""
        WITH posted AS (
            SELECT vl.account_id,
                   SUM(vl.debit_amount) AS period_debit,
                   SUM(vl.credit_amount) AS period_credit
            FROM fin_voucher_lines vl
            JOIN fin_vouchers v ON v.id = vl.voucher_id
            WHERE v.book_id = :bid
              AND v.status = 'posted'
              AND to_char(v.voucher_date, 'YYYY-MM') = :p
            GROUP BY vl.account_id
        ), balance_rows AS (
            SELECT a.account_code, a.account_name, a.account_type, a.direction, a.level,
                   COALESCE(lb.opening_debit, 0) AS opening_debit,
                   COALESCE(lb.opening_credit, 0) AS opening_credit,
                   COALESCE(p.period_debit, 0) AS period_debit,
                   COALESCE(p.period_credit, 0) AS period_credit,
                   COALESCE(lb.opening_debit, 0) - COALESCE(lb.opening_credit, 0)
                       + COALESCE(p.period_debit, 0) - COALESCE(p.period_credit, 0) AS closing_net
            FROM fin_accounts a
            LEFT JOIN fin_ledger_balances lb ON lb.account_id = a.id AND lb.period = :p AND lb.book_id = :bid
            LEFT JOIN posted p ON p.account_id = a.id
            WHERE a.book_id = :bid AND a.is_active = true
        )
        SELECT account_code, account_name, account_type, direction, level,
               opening_debit, opening_credit, period_debit, period_credit,
               CASE WHEN closing_net >= 0 THEN closing_net ELSE 0 END AS closing_debit,
               CASE WHEN closing_net < 0 THEN -closing_net ELSE 0 END AS closing_credit
        FROM balance_rows
        ORDER BY account_code
    """), {"bid": book_id, "p": period})

    return {
        "period": period,
        "rows": [dict(r) for r in result.mappings()],
    }


@router.get("/books/trial-balance")
async def trial_balance(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """兼容旧前端路径，内容同科目余额表。"""
    return await account_balance(book_id=book_id, period=period, db=db, _=_)


# ═══════════════════════════════════════════════════════════
# 明细账
# ═══════════════════════════════════════════════════════════

@router.get("/ledger/detail")
async def ledger_detail(
    account_code: str = Query(...),
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    if not period:
        today = date.today()
        period = f"{today.year}-{today.month:02d}"

    # 期初余额
    opening_r = await db.execute(text("""
        SELECT COALESCE(lb.opening_debit,0) - COALESCE(lb.opening_credit,0) AS opening
        FROM fin_accounts a
        LEFT JOIN fin_ledger_balances lb ON lb.account_id = a.id AND lb.period = :p AND lb.book_id = :bid
        WHERE a.book_id = :bid AND a.account_code = :code
    """), {"bid": book_id, "p": period, "code": account_code})
    opening = _d((opening_r.scalar()))

    # 分录明细
    result = await db.execute(text("""
        SELECT v.voucher_no, v.voucher_date, vl.summary, vl.debit_amount, vl.credit_amount
        FROM fin_voucher_lines vl
        JOIN fin_vouchers v ON v.id = vl.voucher_id
        JOIN fin_accounts a ON a.id = vl.account_id
        WHERE v.book_id = :bid AND a.account_code = :code
              AND v.status = 'posted'
              AND to_char(v.voucher_date, 'YYYY-MM') = :p
        ORDER BY v.voucher_date, v.id
    """), {"bid": book_id, "p": period, "code": account_code})

    rows = []
    balance = opening
    for r in result.mappings():
        d = _d(r["debit_amount"])
        c = _d(r["credit_amount"])
        balance = balance + d - c
        rows.append({
            "voucher_no": r["voucher_no"], "voucher_date": str(r["voucher_date"]),
            "summary": r["summary"] or "", "debit": d, "credit": c, "balance": round(balance, 2),
        })

    return {"opening": opening, "rows": rows}


# ═══════════════════════════════════════════════════════════
# 资产负债表
# ═══════════════════════════════════════════════════════════

@router.get("/reports/balance-sheet")
@router.get("/balance-sheet")
async def balance_sheet(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """资产负债表：按已过账分录动态计算期末余额。"""
    if not period:
        today = date.today()
        period = f"{today.year}-{today.month:02d}"

    result = await db.execute(text("""
        WITH posted AS (
            SELECT vl.account_id,
                   SUM(vl.debit_amount) AS period_debit,
                   SUM(vl.credit_amount) AS period_credit
            FROM fin_voucher_lines vl
            JOIN fin_vouchers v ON v.id = vl.voucher_id
            WHERE v.book_id = :bid
              AND v.status = 'posted'
              AND to_char(v.voucher_date, 'YYYY-MM') = :p
            GROUP BY vl.account_id
        )
        SELECT a.account_type, a.account_name,
               COALESCE(lb.opening_debit, 0) - COALESCE(lb.opening_credit, 0) AS opening_net,
               COALESCE(p.period_debit, 0) AS period_debit,
               COALESCE(p.period_credit, 0) AS period_credit,
               COALESCE(lb.opening_debit, 0) - COALESCE(lb.opening_credit, 0)
                   + COALESCE(p.period_debit, 0) - COALESCE(p.period_credit, 0) AS closing_net
        FROM fin_accounts a
        LEFT JOIN fin_ledger_balances lb ON lb.account_id = a.id AND lb.period = :p AND lb.book_id = :bid
        LEFT JOIN posted p ON p.account_id = a.id
        WHERE a.book_id = :bid AND a.is_active = true AND a.level = 1
        ORDER BY a.account_code
    """), {"bid": book_id, "p": period})

    assets = []
    liabilities = []
    net_profit = 0.0
    for r in result.mappings():
        account_type = r["account_type"]
        opening_net = _d(r["opening_net"])
        closing_net = _d(r["closing_net"])
        period_debit = _d(r["period_debit"])
        period_credit = _d(r["period_credit"])
        if account_type == "asset":
            if opening_net or closing_net:
                assets.append({"item": r["account_name"], "opening": opening_net, "closing": closing_net})
        elif account_type in ("liability", "equity"):
            opening = -opening_net
            closing = -closing_net
            if opening or closing:
                liabilities.append({"item": r["account_name"], "opening": opening, "closing": closing})
        elif account_type == "income":
            net_profit += period_credit - period_debit
        elif account_type in ("expense", "cost"):
            net_profit -= period_debit - period_credit

    if net_profit:
        liabilities.append({"item": "未分配利润", "opening": 0.0, "closing": net_profit})

    total_assets_opening = sum(i["opening"] for i in assets)
    total_assets_closing = sum(i["closing"] for i in assets)
    total_liab_opening = sum(i["opening"] for i in liabilities)
    total_liab_closing = sum(i["closing"] for i in liabilities)

    size = max(len(assets), len(liabilities))
    rows = []
    for idx in range(size):
        asset = assets[idx] if idx < len(assets) else None
        liability = liabilities[idx] if idx < len(liabilities) else None
        rows.append({
            "item": asset["item"] if asset else "",
            "line_no": idx + 1 if asset else "",
            "closing_balance": round(asset["closing"], 2) if asset else None,
            "opening_balance": round(asset["opening"], 2) if asset else None,
            "liability_item": liability["item"] if liability else "",
            "liability_line": idx + 1 if liability else "",
            "liability_closing": round(liability["closing"], 2) if liability else None,
            "liability_opening": round(liability["opening"], 2) if liability else None,
            "is_total": False,
        })

    if rows:
        rows.append({
            "item": "资产合计",
            "line_no": "",
            "closing_balance": round(total_assets_closing, 2),
            "opening_balance": round(total_assets_opening, 2),
            "liability_item": "负债和所有者权益合计",
            "liability_line": "",
            "liability_closing": round(total_liab_closing, 2),
            "liability_opening": round(total_liab_opening, 2),
            "is_total": True,
        })

    return {"period": period, "rows": rows}


# ═══════════════════════════════════════════════════════════
# 利润表
# ═══════════════════════════════════════════════════════════

@router.get("/reports/profit-loss")
@router.get("/reports/profit-statement")
@router.get("/profit-statement")
async def profit_statement(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    if not period:
        today = date.today()
        period = f"{today.year}-{today.month:02d}"
    year = period.split("-")[0]

    result = await db.execute(text("""
        SELECT a.account_code, a.account_name, a.account_type,
               COALESCE(SUM(CASE WHEN to_char(v.voucher_date, 'YYYY-MM') = :p THEN vl.debit_amount ELSE 0 END), 0) AS current_debit,
               COALESCE(SUM(CASE WHEN to_char(v.voucher_date, 'YYYY-MM') = :p THEN vl.credit_amount ELSE 0 END), 0) AS current_credit,
               COALESCE(SUM(CASE WHEN v.id IS NOT NULL THEN vl.debit_amount ELSE 0 END), 0) AS ytd_debit,
               COALESCE(SUM(CASE WHEN v.id IS NOT NULL THEN vl.credit_amount ELSE 0 END), 0) AS ytd_credit
        FROM fin_accounts a
        LEFT JOIN fin_voucher_lines vl ON vl.account_id = a.id
        LEFT JOIN fin_vouchers v ON v.id = vl.voucher_id
             AND v.book_id = :bid
             AND v.status = 'posted'
             AND to_char(v.voucher_date, 'YYYY') = :y
             AND to_char(v.voucher_date, 'YYYY-MM') <= :p
        WHERE a.book_id = :bid
          AND a.is_active = true
          AND a.account_type IN ('income', 'expense', 'cost')
        GROUP BY a.account_code, a.account_name, a.account_type
        ORDER BY a.account_code
    """), {"bid": book_id, "p": period, "y": year})

    income_current = 0.0
    income_ytd = 0.0
    expense_rows = []
    total_expense_current = 0.0
    total_expense_ytd = 0.0
    for r in result.mappings():
        current_debit = _d(r["current_debit"])
        current_credit = _d(r["current_credit"])
        ytd_debit = _d(r["ytd_debit"])
        ytd_credit = _d(r["ytd_credit"])
        if r["account_type"] == "income":
            income_current += current_credit - current_debit
            income_ytd += ytd_credit - ytd_debit
        else:
            current = current_debit - current_credit
            ytd = ytd_debit - ytd_credit
            if current or ytd:
                expense_rows.append({"item": r["account_name"], "current": current, "ytd": ytd})
                total_expense_current += current
                total_expense_ytd += ytd

    net_current = income_current - total_expense_current
    net_ytd = income_ytd - total_expense_ytd

    rows = [
        {"line_no": 1, "item": "一、营业收入", "current_period": round(income_current, 2), "ytd": round(income_ytd, 2), "is_total": False},
    ]
    for er in expense_rows:
        rows.append({
            "line_no": len(rows) + 1,
            "item": f"减：{er['item']}",
            "current_period": round(er["current"], 2),
            "ytd": round(er["ytd"], 2),
            "is_total": False,
        })

    rows.append({"line_no": len(rows) + 1, "item": "二、营业利润", "current_period": round(net_current, 2), "ytd": round(net_ytd, 2), "is_total": True})
    rows.append({"line_no": len(rows) + 1, "item": "三、净利润", "current_period": round(net_current, 2), "ytd": round(net_ytd, 2), "is_total": True})

    return {"period": period, "month": int(period.split("-")[1]), "rows": rows}


# ═══════════════════════════════════════════════════════════
# 现金流量表
# ═══════════════════════════════════════════════════════════

@router.get("/cashflow-statement")
async def cashflow_statement(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    if not period:
        today = date.today()
        period = f"{today.year}-{today.month:02d}"
    # 从已过账凭证分录推导现金流量
    # 找所有现金科目（1001库存现金/1002银行存款/1003支付宝微信）的分录
    raw = await db.execute(text("""
        SELECT
            v.id AS voucher_id,
            v.voucher_date,
            vl.debit_amount,
            vl.credit_amount,
            a.account_code AS cash_code,
            a.account_name AS cash_name,
            vl.summary,
            -- 同一凭证中对方科目（取第一个非现金行）
            (
                SELECT a2.account_code FROM fin_voucher_lines vl2
                JOIN fin_accounts a2 ON a2.id = vl2.account_id
                WHERE vl2.voucher_id = v.id
                  AND a2.account_code NOT LIKE '100%'
                LIMIT 1
            ) AS counter_code
        FROM fin_voucher_lines vl
        JOIN fin_vouchers v ON v.id = vl.voucher_id
        JOIN fin_accounts a ON a.id = vl.account_id
        WHERE v.book_id = :bid
          AND v.status = 'posted'
          AND to_char(v.voucher_date, 'YYYY-MM') = :p
          AND a.account_code LIKE '100%'
    """), {"bid": book_id, "p": period})
    rows = list(raw.mappings())

    operating, investing, financing = [], [], []

    def classify(cc: str, debit, credit, summary, date):
        d = _d(debit); c = _d(credit)
        if not cc:
            return
        # 经营活动
        if cc.startswith(('6', '11')):  # 收入/应收款
            if d > 0:
                operating.append({"item": "销售商品收到的现金", "amount": d,
                    "remark": summary or "", "date": str(date), "sign": "in"})
            if c > 0:
                operating.append({"item": "其他经营支出", "amount": -c,
                    "remark": summary or "", "date": str(date), "sign": "out"})
        elif cc.startswith(('14', '22', '64', '66')):  # 存货/应付/成本/费用
            if c > 0:
                item = "支付给职工的现金" if cc.startswith('2211') else                        "支付税费" if cc.startswith('2221') else                        "购买商品支付的现金"
                operating.append({"item": item, "amount": -c,
                    "remark": summary or "", "date": str(date), "sign": "out"})
            if d > 0:
                operating.append({"item": "收到其他经营款项", "amount": d,
                    "remark": summary or "", "date": str(date), "sign": "in"})
        # 投资活动
        elif cc.startswith('16'):
            if c > 0:
                investing.append({"item": "购置固定资产支付的现金", "amount": -c,
                    "remark": summary or "", "date": str(date), "sign": "out"})
            if d > 0:
                investing.append({"item": "处置固定资产收到的现金", "amount": d,
                    "remark": summary or "", "date": str(date), "sign": "in"})
        # 筹资活动
        elif cc.startswith(('20', '30', '31')):
            if d > 0:
                investing.append({"item": "借款/股东注资收到的现金", "amount": d,
                    "remark": summary or "", "date": str(date), "sign": "in"})
            if c > 0:
                financing.append({"item": "偿还借款支付的现金", "amount": -c,
                    "remark": summary or "", "date": str(date), "sign": "out"})
        # 默认按现金流方向归入经营活动
        else:
            if d > 0:
                operating.append({"item": "收到其他现金", "amount": d,
                    "remark": summary or "", "date": str(date), "sign": "in"})
            if c > 0:
                operating.append({"item": "支付其他现金", "amount": -c,
                    "remark": summary or "", "date": str(date), "sign": "out"})

    for r in rows:
        classify(r["counter_code"], r["debit_amount"], r["credit_amount"],
                 r["summary"], r["voucher_date"])

    # 聚合同类项目
    def aggregate(items):
        agg = {}
        for it in items:
            k = it["item"]
            if k not in agg:
                agg[k] = {"item": k, "amount": 0, "sign": it["sign"]}
            agg[k]["amount"] += it["amount"]
        return [v for v in agg.values() if abs(v["amount"]) > 0.005]

    op = aggregate(operating)
    inv = aggregate(investing)
    fin = aggregate(financing)
    op_total = sum(i["amount"] for i in op)
    inv_total = sum(i["amount"] for i in inv)
    fin_total = sum(i["amount"] for i in fin)

    return {
        "period": period,
        "operating": op, "operating_total": round(op_total, 2),
        "investing": inv, "investing_total": round(inv_total, 2),
        "financing": fin, "financing_total": round(fin_total, 2),
        "net_change": round(op_total + inv_total + fin_total, 2),
    }


# ═══════════════════════════════════════════════════════════
# 费用明细表
# ═══════════════════════════════════════════════════════════

@router.get("/reports/expense-detail")
async def expense_detail(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """费用明细表：汇总销售费用/管理费用/财务费用的分录"""
    if not period:
        today = date.today()
        period = f"{today.year}-{today.month:02d}"
    result = await db.execute(text("""
        WITH posted AS (
            SELECT vl.account_id,
                   SUM(vl.debit_amount) AS period_debit,
                   SUM(vl.credit_amount) AS period_credit
            FROM fin_voucher_lines vl
            JOIN fin_vouchers v ON v.id = vl.voucher_id
            WHERE v.book_id = :bid
              AND v.status = 'posted'
              AND to_char(v.voucher_date, 'YYYY-MM') = :p
            GROUP BY vl.account_id
        )
        SELECT a.account_code, a.account_name,
               COALESCE(p.period_debit, 0) AS period_debit,
               COALESCE(p.period_credit, 0) AS period_credit,
               COALESCE(lb.opening_debit, 0) - COALESCE(lb.opening_credit, 0)
                   + COALESCE(p.period_debit, 0) - COALESCE(p.period_credit, 0) AS closing_balance
        FROM fin_accounts a
        LEFT JOIN posted p ON p.account_id = a.id
        LEFT JOIN fin_ledger_balances lb ON lb.account_id = a.id AND lb.period = :p AND lb.book_id = :bid
        WHERE a.book_id = :bid AND a.account_type = 'expense' AND a.is_active = true
        ORDER BY a.account_code
    """), {"bid": book_id, "p": period})
    rows = []
    all_rows = []
    total_net = 0.0
    for r in result.mappings():
        debit = _d(r["period_debit"])
        credit = _d(r["period_credit"])
        net = debit - credit
        row = {
            "account_code": r["account_code"],
            "account_name": r["account_name"],
            "period_debit": round(debit, 2),
            "period_credit": round(credit, 2),
            "net_amount": round(net, 2),
            "closing_balance": round(_d(r["closing_balance"]), 2),
        }
        all_rows.append(row)
        if debit or credit:
            rows.append(row)
        total_net += net
    return {"period": period, "rows": rows, "all_rows": all_rows, "total_net": round(total_net, 2)}


# ═══════════════════════════════════════════════════════════
# 税金明细表
# ═══════════════════════════════════════════════════════════

@router.get("/reports/tax-detail")
async def tax_detail(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """税金明细表：汇总应交税费(2221)科目下的分录"""
    if not period:
        today = date.today()
        period = f"{today.year}-{today.month:02d}"
    ledger_result = await db.execute(text("""
        WITH posted AS (
            SELECT vl.account_id,
                   SUM(vl.debit_amount) AS period_debit,
                   SUM(vl.credit_amount) AS period_credit
            FROM fin_voucher_lines vl
            JOIN fin_vouchers v ON v.id = vl.voucher_id
            WHERE v.book_id = :bid
              AND v.status = 'posted'
              AND to_char(v.voucher_date, 'YYYY-MM') = :p
            GROUP BY vl.account_id
        )
        SELECT a.account_code, a.account_name,
               COALESCE(p.period_debit, 0) AS period_debit,
               COALESCE(p.period_credit, 0) AS period_credit,
               COALESCE(lb.opening_credit, 0) - COALESCE(lb.opening_debit, 0)
                   + COALESCE(p.period_credit, 0) - COALESCE(p.period_debit, 0) AS balance
        FROM fin_accounts a
        LEFT JOIN posted p ON p.account_id = a.id
        LEFT JOIN fin_ledger_balances lb ON lb.account_id = a.id AND lb.period = :p AND lb.book_id = :bid
        WHERE a.book_id = :bid AND a.account_code LIKE '2221%' AND a.is_active = true
        ORDER BY a.account_code
    """), {"bid": book_id, "p": period})
    ledger_rows = []
    total_balance = 0.0
    for r in ledger_result.mappings():
        debit = _d(r["period_debit"])
        credit = _d(r["period_credit"])
        balance = _d(r["balance"])
        if debit or credit or balance:
            ledger_rows.append({
                "account_code": r["account_code"],
                "account_name": r["account_name"],
                "period_debit": round(debit, 2),
                "period_credit": round(credit, 2),
                "balance": round(balance, 2),
            })
        total_balance += balance

    tax_result = await db.execute(text("""
        SELECT tt.tax_name, tt.tax_category,
               COALESCE(SUM(tr.tax_amount), 0) AS tax_amount,
               COALESCE(SUM(CASE WHEN tr.status='paid' THEN tr.tax_amount ELSE 0 END), 0) AS paid_amount,
               COALESCE(SUM(CASE WHEN tr.status!='paid' THEN tr.tax_amount ELSE 0 END), 0) AS unpaid_amount
        FROM fin_tax_records tr
        JOIN fin_tax_types tt ON tt.id = tr.tax_type_id
        WHERE tr.book_id = :bid AND tr.period = :p
        GROUP BY tt.id, tt.tax_name, tt.tax_category
        ORDER BY tt.tax_name
    """), {"bid": book_id, "p": period})
    tax_rows = []
    total_tax_amount = 0.0
    total_unpaid = 0.0
    for r in tax_result.mappings():
        tax_amount = _d(r["tax_amount"])
        unpaid_amount = _d(r["unpaid_amount"])
        tax_rows.append({
            "tax_name": r["tax_name"],
            "tax_type": r["tax_category"],
            "tax_amount": round(tax_amount, 2),
            "paid_amount": round(_d(r["paid_amount"]), 2),
            "unpaid_amount": round(unpaid_amount, 2),
        })
        total_tax_amount += tax_amount
        total_unpaid += unpaid_amount

    return {
        "period": period,
        "ledger_view": {"rows": ledger_rows, "total_balance": round(total_balance, 2)},
        "tax_records_view": {
            "rows": tax_rows,
            "total_tax_amount": round(total_tax_amount, 2),
            "total_unpaid": round(total_unpaid, 2),
        },
    }


# ═══════════════════════════════════════════════════════════
# 结账
# ═══════════════════════════════════════════════════════════

@router.get("/closing/periods")
async def closing_periods(
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """已结账期间列表"""
    result = await db.execute(text("""
        SELECT * FROM fin_audit_logs
        WHERE book_id = :bid AND action IN ('close_period', 'unclose_period')
        ORDER BY created_at DESC LIMIT 50
    """), {"bid": book_id})
    return {"periods": [dict(r) for r in result.mappings()]}


@router.post("/closing/pre-check")
async def closing_pre_check(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """结账预检：检查结账前必须处理和建议处理的事项"""
    if not period:
        today = date.today()
        period = f"{today.year}-{today.month:02d}"

    async def scalar(sql: str, params: Optional[dict] = None):
        result = await db.execute(text(sql), params or {"bid": book_id, "p": period})
        return result.scalar() or 0

    checks = []

    period_status = await scalar("""
        SELECT status FROM fin_periods
        WHERE book_id = :bid AND period = :p
    """)
    if not period_status:
        checks.append({
            "key": "period_initialized", "title": "会计期间已初始化", "severity": "warning",
            "passed": False, "count": 1, "message": "该期间还没有初始化，建议先点右上角初始化期间。",
        })
    elif period_status in ("closed", "locked"):
        checks.append({
            "key": "period_open", "title": "期间状态可结账", "severity": "error",
            "passed": False, "count": 1, "message": f"{period} 当前状态为{period_status}，不能重复结账。",
        })
    else:
        checks.append({
            "key": "period_open", "title": "期间状态可结账", "severity": "success",
            "passed": True, "count": 0, "message": "期间开放，可以执行结账流程。",
        })

    unposted_count = int(await scalar("""
        SELECT COUNT(*) FROM fin_vouchers
        WHERE book_id = :bid AND to_char(voucher_date, 'YYYY-MM') = :p AND status != 'posted'
    """))
    checks.append({
        "key": "unposted_vouchers", "title": "凭证已全部过账", "severity": "error" if unposted_count else "success",
        "passed": unposted_count == 0, "count": unposted_count,
        "message": "所有凭证均已过账。" if unposted_count == 0 else f"有 {unposted_count} 张凭证未过账，请先审核/过账。",
        "action_label": "查看凭证", "action_path": "/finance/voucher/list",
    })

    unbalanced_count = int(await scalar("""
        SELECT COUNT(*) FROM fin_vouchers
        WHERE book_id = :bid AND to_char(voucher_date, 'YYYY-MM') = :p
          AND ABS(COALESCE(total_debit, 0) - COALESCE(total_credit, 0)) >= 0.01
    """))
    checks.append({
        "key": "balanced_vouchers", "title": "凭证借贷平衡", "severity": "error" if unbalanced_count else "success",
        "passed": unbalanced_count == 0, "count": unbalanced_count,
        "message": "本期凭证借贷均平衡。" if unbalanced_count == 0 else f"有 {unbalanced_count} 张凭证借贷不平，请修正后再结账。",
        "action_label": "查看凭证", "action_path": "/finance/voucher/list",
    })

    carry_forward_voucher_count = int(await scalar("""
        SELECT COUNT(*) FROM fin_vouchers
        WHERE book_id = :bid AND period = :p AND status = 'posted' AND source_type = 'carry_forward'
    """))
    profit_loss_amount = float(await scalar("""
        SELECT ABS(COALESCE(SUM(CASE WHEN a.account_type = 'income' THEN vl.credit_amount - vl.debit_amount
                                     WHEN a.account_type = 'expense' THEN vl.debit_amount - vl.credit_amount
                                     ELSE 0 END), 0))
        FROM fin_voucher_lines vl
        JOIN fin_vouchers v ON v.id = vl.voucher_id
        JOIN fin_accounts a ON a.id = vl.account_id
        WHERE v.book_id = :bid AND v.status = 'posted'
          AND to_char(v.voucher_date, 'YYYY-MM') = :p
          AND a.account_type IN ('income', 'expense')
    """))
    needs_carry_forward = profit_loss_amount >= 0.01 and carry_forward_voucher_count == 0
    checks.append({
        "key": "carry_forward", "title": "损益已结转", "severity": "warning" if needs_carry_forward else "success",
        "passed": not needs_carry_forward, "count": 1 if needs_carry_forward else 0,
        "message": "损益已结转或本期无损益发生。" if not needs_carry_forward else "本期有收入/费用发生，建议先执行结转损益。",
    })

    cash_unmatched_count = int(await scalar("""
        SELECT COUNT(*) FROM fin_cash_flows
        WHERE book_id = :bid AND to_char(flow_date, 'YYYY-MM') = :p AND voucher_id IS NULL
    """))
    checks.append({
        "key": "cash_flows_voucher", "title": "出纳流水已生成凭证", "severity": "warning" if cash_unmatched_count else "success",
        "passed": cash_unmatched_count == 0, "count": cash_unmatched_count,
        "message": "出纳流水均已关联凭证。" if cash_unmatched_count == 0 else f"有 {cash_unmatched_count} 条出纳流水未生成凭证，可能影响银行存款余额。",
        "action_label": "查看出纳", "action_path": "/finance/cashier",
    })

    payroll_pending_count = int(await scalar("""
        SELECT COUNT(*) FROM fin_payroll_records
        WHERE book_id = :bid AND pay_month = :p AND (status != 'paid' OR voucher_id IS NULL)
    """))
    checks.append({
        "key": "payroll_done", "title": "工资已处理", "severity": "warning" if payroll_pending_count else "success",
        "passed": payroll_pending_count == 0, "count": payroll_pending_count,
        "message": "本期工资已处理。" if payroll_pending_count == 0 else f"有 {payroll_pending_count} 条工资未发放或未生成凭证。",
        "action_label": "查看工资", "action_path": "/finance/payroll",
    })

    tax_pending_count = int(await scalar("""
        SELECT COUNT(*) FROM fin_tax_records
        WHERE book_id = :bid AND period = :p
          AND (status != 'paid' OR COALESCE(paid_amount, 0) < COALESCE(tax_amount, 0))
    """))
    checks.append({
        "key": "tax_paid", "title": "税款已处理", "severity": "warning" if tax_pending_count else "success",
        "passed": tax_pending_count == 0, "count": tax_pending_count,
        "message": "本期税款已处理。" if tax_pending_count == 0 else f"有 {tax_pending_count} 条税款未缴清或未处理。",
        "action_label": "查看税务", "action_path": "/finance/tax",
    })

    recv_unvouchered_count = int(await scalar("""
        SELECT COUNT(*) FROM fin_recv_orders
        WHERE book_id = :bid AND COALESCE(period, to_char(order_date, 'YYYY-MM')) = :p AND voucher_id IS NULL
    """))
    payable_unvouchered_count = int(await scalar("""
        SELECT COUNT(*) FROM fin_payable_orders
        WHERE book_id = :bid AND COALESCE(period, to_char(order_date, 'YYYY-MM')) = :p AND voucher_id IS NULL
    """))
    ar_ap_count = recv_unvouchered_count + payable_unvouchered_count
    checks.append({
        "key": "ar_ap_voucher", "title": "应收应付已入账", "severity": "warning" if ar_ap_count else "success",
        "passed": ar_ap_count == 0, "count": ar_ap_count,
        "message": "应收应付单据均已入账。" if ar_ap_count == 0 else f"有 {recv_unvouchered_count} 张应收单、{payable_unvouchered_count} 张应付单未生成凭证。",
        "action_label": "查看应收应付", "action_path": "/finance/ar/recv-orders",
    })

    fixed_asset_count = int(await scalar("""
        SELECT COUNT(*) FROM fin_fixed_assets
        WHERE book_id = :bid AND status = 'in_use'
          AND purchase_date IS NOT NULL AND to_char(purchase_date, 'YYYY-MM') <= :p
          AND COALESCE(monthly_depre, 0) > 0 AND COALESCE(accumulated_depre, 0) = 0
    """))
    checks.append({
        "key": "asset_depreciation", "title": "固定资产折旧已检查", "severity": "warning" if fixed_asset_count else "success",
        "passed": fixed_asset_count == 0, "count": fixed_asset_count,
        "message": "固定资产折旧状态正常。" if fixed_asset_count == 0 else f"有 {fixed_asset_count} 个固定资产可能未计提折旧。",
        "action_label": "查看资产", "action_path": "/finance/assets",
    })

    blocking_count = sum(1 for item in checks if item["severity"] == "error" and not item["passed"])
    warning_count = sum(1 for item in checks if item["severity"] == "warning" and not item["passed"])
    can_close = blocking_count == 0

    return {
        "period": period,
        "can_close": can_close,
        "unposted_count": unposted_count,
        "blocking_count": blocking_count,
        "warning_count": warning_count,
        "checks": checks,
        "message": "可以结账" if can_close else f"有 {blocking_count} 项必须处理后才能结账",
    }


@router.post("/closing/close")
async def close_period(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """执行结账"""
    if not period:
        today = date.today()
        period = f"{today.year}-{today.month:02d}"

    # 预检
    check = await closing_pre_check(book_id, period, db, current_user)
    if not check["can_close"]:
        raise HTTPException(400, check["message"])

    # 结转期末→下期期初（将 closing 写入下期 opening）
    y, m = int(period[:4]), int(period[5:7])
    if m == 12:
        next_period = f"{y+1}-01"
    else:
        next_period = f"{y}-{m+1:02d}"

    await db.execute(text("""
        INSERT INTO fin_ledger_balances (book_id, account_id, period, opening_debit, opening_credit)
        SELECT book_id, account_id, :np,
               closing_debit, closing_credit
        FROM fin_ledger_balances
        WHERE book_id = :bid AND period = :p
        ON CONFLICT (book_id, account_id, period) DO UPDATE SET
            opening_debit = EXCLUDED.opening_debit,
            opening_credit = EXCLUDED.opening_credit
    """), {"bid": book_id, "p": period, "np": next_period})

    # 更新账套当前期间
    await db.execute(text("UPDATE fin_books SET current_period = :np WHERE id = :bid"),
                     {"bid": book_id, "np": next_period})

    db.add(FinAuditLog(book_id=book_id, operator=str(current_user.id),
                        action="close_period", target=f"period:{period}"))
    await _sync_period_status(db, book_id, period, "closed", str(current_user.id))
    await db.commit()
    return {"ok": True, "closed_period": period, "new_period": next_period}


@router.post("/closing/unclose")
async def unclose_period(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """反结账"""
    if not period:
        raise HTTPException(400, "请指定期间")

    await db.execute(text("UPDATE fin_books SET current_period = :p WHERE id = :bid"),
                     {"bid": book_id, "p": period})

    db.add(FinAuditLog(book_id=book_id, operator=str(current_user.id),
                        action="unclose_period", target=f"period:{period}"))
    await _sync_period_status(db, book_id, period, "open", str(current_user.id))
    await db.commit()
    return {"ok": True, "reopened_period": period}



# ═══════════════════════════════════════════════════════════
# 结转损益
# ═══════════════════════════════════════════════════════════

@router.post("/closing/carry-forward")
async def carry_forward(
    book_id: int = Query(1),
    period: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    结转损益：将收入/费用类科目本期发生额结转到"未分配利润"(3101)
    生成一张自动凭证，借：收入科目，贷：费用科目，差额转入3101
    """
    if not period:
        today = date.today()
        period = f"{today.year}-{today.month:02d}"

    # 查找损益类科目（收入+费用）本期发生额
    result = await db.execute(text("""
        WITH posted AS (
            SELECT vl.account_id,
                   SUM(vl.debit_amount) AS pd,
                   SUM(vl.credit_amount) AS pc
            FROM fin_voucher_lines vl
            JOIN fin_vouchers v ON v.id = vl.voucher_id
            WHERE v.book_id = :bid
              AND v.status = 'posted'
              AND to_char(v.voucher_date, 'YYYY-MM') = :p
            GROUP BY vl.account_id
        )
        SELECT a.id, a.account_code, a.account_name, a.account_type, a.direction,
               COALESCE(p.pd, 0) AS pd, COALESCE(p.pc, 0) AS pc
        FROM fin_accounts a
        JOIN posted p ON p.account_id = a.id
        WHERE a.book_id = :bid AND a.account_type IN ('income', 'expense')
              AND (COALESCE(p.pd, 0) != 0 OR COALESCE(p.pc, 0) != 0)
    """), {"bid": book_id, "p": period})

    rows = list(result.mappings())
    if not rows:
        return {"ok": True, "message": "无需结转（损益类科目无发生额）", "voucher_id": None}

    # 查找3101未分配利润科目
    profit_acct = await db.execute(text(
        "SELECT id FROM fin_accounts WHERE book_id = :bid AND account_code = '3101'"
    ), {"bid": book_id})
    profit_id = profit_acct.scalar()
    if not profit_id:
        raise HTTPException(400, "未找到3101未分配利润科目")

    # 生成结转凭证
    from app.api.v1.finance.vouchers import next_voucher_no
    no_data = await next_voucher_no(book_id, db, current_user)

    from app.models.finance.accounting import FinVoucher, FinVoucherLine
    v = FinVoucher(
        book_id=book_id, voucher_no=no_data["next_no"], voucher_type="转",
        voucher_date=date.today(), source_type="carry_forward",
        summary=f"{period} 结转损益", status="draft",
        created_by=str(current_user.id),
    )
    db.add(v)
    await db.flush()

    total_profit = 0  # 净利润
    line_no = 1
    for r in rows:
        pd, pc = _d(r["pd"]), _d(r["pc"])
        if r["account_type"] == "income":
            # 收入类：借收入科目（冲平），差额为利润
            db.add(FinVoucherLine(voucher_id=v.id, line_no=line_no, account_id=r["id"],
                                   account_code=r["account_code"], debit_amount=pc, credit_amount=0,
                                   summary=f"结转{r['account_name']}"))
            total_profit += (pc - pd)  # 收入净额
        else:
            # 费用类：贷费用科目（冲平）
            db.add(FinVoucherLine(voucher_id=v.id, line_no=line_no, account_id=r["id"],
                                   account_code=r["account_code"], debit_amount=0, credit_amount=pd,
                                   summary=f"结转{r['account_name']}"))
            total_profit -= (pd - pc)  # 费用减少利润
        line_no += 1

    # 差额转入未分配利润
    if total_profit >= 0:
        db.add(FinVoucherLine(voucher_id=v.id, line_no=line_no, account_id=profit_id,
                               account_code="3101", debit_amount=0, credit_amount=round(total_profit, 2),
                               summary="本期净利润转入"))
    else:
        db.add(FinVoucherLine(voucher_id=v.id, line_no=line_no, account_id=profit_id,
                               account_code="3101", debit_amount=round(abs(total_profit), 2), credit_amount=0,
                               summary="本期净亏损转入"))

    v.total_debit = round(sum(_d(r["pc"]) for r in rows if r["account_type"] == "income") +
                          (abs(total_profit) if total_profit < 0 else 0), 2)
    v.total_credit = round(sum(_d(r["pd"]) for r in rows if r["account_type"] == "expense") +
                           (total_profit if total_profit >= 0 else 0), 2)

    db.add(FinAuditLog(book_id=book_id, operator=str(current_user.id),
                        action="carry_forward", target=f"voucher:{v.id}", detail=f"{period} 净利润={total_profit:.2f}"))

    return {"ok": True, "voucher_id": v.id, "voucher_no": v.voucher_no, "net_profit": round(total_profit, 2)}



# ═══════════════════════════════════════════════════════════
# 自动入账（JST/DM → 凭证）
# ═══════════════════════════════════════════════════════════

@router.get("/auto-entry/pending")
async def auto_entry_pending(
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """
    获取待入账的日报数据列表。
    数据源：dm_store_daily（按日汇总），检查 fin_vouchers 中是否已有对应凭证。
    """
    result = await db.execute(text("""
        WITH daily AS (
            SELECT biz_date,
                   SUM(sale_amount) AS total_sales,
                   SUM(sale_cogs) AS sales_cost,
                   SUM(refund_amount) AS refund_amount,
                   SUM(refund_amount - refund_cogs) AS refund_loss,
                   SUM(operating_profit) AS total_profit,
                   SUM(shipped_qty) AS quantity
            FROM dm_store_daily
            GROUP BY biz_date
            ORDER BY biz_date DESC
            LIMIT 60
        )
        SELECT d.*,
               CASE WHEN v.id IS NOT NULL THEN true ELSE false END AS entered
        FROM daily d
        LEFT JOIN fin_vouchers v ON v.book_id = :bid
            AND v.source_type = 'jst_daily' AND v.source_ref = to_char(d.biz_date, 'YYYY-MM-DD')
        ORDER BY d.biz_date DESC
    """), {"bid": book_id})
    return {"rows": [
        {
            "date": str(r["biz_date"]),
            "total_sales": _d(r["total_sales"]),
            "sales_cost": _d(r["sales_cost"]),
            "refund_amount": _d(r["refund_amount"]),
            "refund_loss": _d(r["refund_loss"]),
            "total_profit": _d(r["total_profit"]),
            "quantity": int(r["quantity"] or 0),
            "entered": r["entered"],
        }
        for r in result.mappings()
    ]}


@router.post("/auto-entry/enter")
async def auto_entry_enter(
    book_id: int = Query(1),
    target_date: str = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    自动入账指定日期：从 dm_store_daily 汇总生成3张凭证
    规则（对标虎狼 auto_entry.py）：
      1. 销售收入凭证：借 1122平台结算款 / 贷 6001主营业务收入
      2. 销售成本凭证：借 6401主营业务成本 / 贷 1401库存商品
      3. 退货净损失凭证：借 6001主营业务收入 / 贷 1122平台结算款
    """
    # 检查是否已入账
    exists = await db.execute(text(
        "SELECT 1 FROM fin_vouchers WHERE book_id=:bid AND source_type='jst_daily' AND source_ref=:ref"
    ), {"bid": book_id, "ref": target_date})
    if exists.scalar():
        return {"ok": False, "error": f"{target_date} 已入账，不可重复"}

    # 汇总当日数据
    dr = await db.execute(text("""
        SELECT COALESCE(SUM(sale_amount),0) AS sales,
               COALESCE(SUM(sale_cogs),0) AS cogs,
               COALESCE(SUM(refund_amount - refund_cogs),0) AS refund_loss
        FROM dm_store_daily WHERE biz_date = :d
    """), {"d": date.fromisoformat(target_date)})
    d = dr.mappings().first()
    sales, cogs, refund_loss = _d(d["sales"]), _d(d["cogs"]), _d(d["refund_loss"])

    if sales == 0 and cogs == 0:
        return {"ok": False, "error": f"{target_date} 无销售数据"}

    # 获取科目ID
    acct_map = {}
    for code in ["1122", "6001", "6401", "1401"]:
        ar = await db.execute(text(
            "SELECT id FROM fin_accounts WHERE book_id=:bid AND account_code=:code"
        ), {"bid": book_id, "code": code})
        aid = ar.scalar()
        if not aid:
            return {"ok": False, "error": f"科目 {code} 不存在"}
        acct_map[code] = aid

    from app.models.finance.accounting import FinVoucher, FinVoucherLine
    from app.api.v1.finance.vouchers import next_voucher_no
    voucher_ids = []

    async def _make_voucher(summary, lines_data):
        no_data = await next_voucher_no(book_id, db, current_user)
        v = FinVoucher(
            book_id=book_id, voucher_no=no_data["next_no"], voucher_type="记",
            voucher_date=date.fromisoformat(target_date),
            source_type="jst_daily", source_ref=target_date,
            summary=summary, status="draft",
            created_by=str(current_user.id),
            total_debit=sum(l[1] for l in lines_data),
            total_credit=sum(l[2] for l in lines_data),
        )
        db.add(v)
        await db.flush()
        for i, (acct_code, debit, credit, desc) in enumerate(lines_data, 1):
            db.add(FinVoucherLine(
                voucher_id=v.id, line_no=i, account_id=acct_map[acct_code],
                account_code=acct_code, debit_amount=debit, credit_amount=credit, summary=desc,
            ))
        voucher_ids.append(v.id)

    # 凭证1: 销售收入
    if sales > 0:
        await _make_voucher(f"{target_date} 销售收入", [
            ("1122", sales, 0, "平台结算款"),
            ("6001", 0, sales, "主营业务收入"),
        ])

    # 凭证2: 销售成本
    if cogs > 0:
        await _make_voucher(f"{target_date} 销售成本", [
            ("6401", cogs, 0, "主营业务成本"),
            ("1401", 0, cogs, "库存商品减少"),
        ])

    # 凭证3: 退货净损失
    if refund_loss > 0:
        await _make_voucher(f"{target_date} 退货净损失", [
            ("6001", refund_loss, 0, "退货冲减收入"),
            ("1122", 0, refund_loss, "冲减平台结算款"),
        ])

    db.add(FinAuditLog(book_id=book_id, operator=str(current_user.id),
                        action="auto_entry", target=f"date:{target_date}",
                        detail=f"生成{len(voucher_ids)}张凭证,销售={sales},成本={cogs},退损={refund_loss}"))

    return {"ok": True, "voucher_ids": voucher_ids, "count": len(voucher_ids),
            "sales": sales, "cogs": cogs, "refund_loss": refund_loss}



# ═══════════════════════════════════════════════════════════
# 报表导出 Excel
# ═══════════════════════════════════════════════════════════

@router.get("/export/vouchers")
async def export_vouchers(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """导出凭证列表为 Excel"""
    if not period:
        today = date.today()
        period = f"{today.year}-{today.month:02d}"
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    import io

    result = await db.execute(text("""
        SELECT v.voucher_no, v.voucher_date, v.summary, v.status,
               v.total_debit, v.total_credit, v.source_type, v.created_by
        FROM fin_vouchers v
        WHERE v.book_id = :bid AND to_char(v.voucher_date, 'YYYY-MM') = :p
        ORDER BY v.voucher_no
    """), {"bid": book_id, "p": period})

    wb = Workbook()
    ws = wb.active
    ws.title = f"凭证_{period}"
    headers = ["凭证号", "日期", "摘要", "状态", "借方合计", "贷方合计", "来源", "制单人"]
    ws.append(headers)
    hf = Font(bold=True, color="FFFFFF")
    hfill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for i in range(1, len(headers)+1):
        ws.cell(1, i).font = hf
        ws.cell(1, i).fill = hfill

    status_map = {"draft": "草稿", "reviewed": "已审核", "posted": "已过账"}
    for r in result.mappings():
        ws.append([r["voucher_no"], str(r["voucher_date"]), r["summary"] or "",
                   status_map.get(r["status"], r["status"]),
                   float(r["total_debit"] or 0), float(r["total_credit"] or 0),
                   r["source_type"], r["created_by"] or ""])

    for col, w in [("A",14),("B",12),("C",30),("D",10),("E",14),("F",14),("G",12),("H",10)]:
        ws.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    from fastapi.responses import Response
    return Response(content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=vouchers_{period}.xlsx"})


@router.get("/export/balance-sheet")
async def export_balance_sheet(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """导出资产负债表为 Excel"""
    data = await balance_sheet(book_id, period, db, _)
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    import io
    wb = Workbook()
    ws = wb.active
    ws.title = "资产负债表"
    headers = ["项目", "期末余额", "年初余额"]
    ws.append(headers)
    hf = Font(bold=True, color="FFFFFF")
    hfill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for i in range(1,4):
        ws.cell(1,i).font=hf; ws.cell(1,i).fill=hfill
    for r in data["rows"]:
        ws.append([r.get("item", ""), r.get("closing_balance", ""), r.get("opening_balance", "")])
        if r.get("liability_item"):
            ws.append([r.get("liability_item", ""), r.get("liability_closing", ""), r.get("liability_opening", "")])
    for col, w in [("A",25),("B",16),("C",16)]:
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    from fastapi.responses import Response
    return Response(content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=balance_sheet_{data.get('period','')}.xlsx"})


@router.get("/export/profit-statement")
async def export_profit_stmt(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """导出利润表为 Excel"""
    data = await profit_statement(book_id, period, db, _)
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    import io
    wb = Workbook()
    ws = wb.active
    ws.title = "利润表"
    headers = ["项目", "本月金额", "本年累计"]
    ws.append(headers)
    hf = Font(bold=True, color="FFFFFF")
    hfill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for i in range(1,4):
        ws.cell(1,i).font=hf; ws.cell(1,i).fill=hfill
    for r in data["rows"]:
        ws.append([r["item"], r.get("current_period", 0), r.get("ytd", 0)])
    for col, w in [("A",25),("B",16),("C",16)]:
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    from fastapi.responses import Response
    return Response(content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=profit_{data.get('month','')}.xlsx"})


@router.get("/export/account-balance")
async def export_account_bal(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """导出科目余额表为 Excel"""
    data = await account_balance(book_id, period, db, _)
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    import io
    wb = Workbook()
    ws = wb.active
    ws.title = "科目余额表"
    headers = ["科目编码","科目名称","期初借方","期初贷方","本期借方","本期贷方","期末借方","期末贷方"]
    ws.append(headers)
    hf = Font(bold=True, color="FFFFFF")
    hfill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for i in range(1,9):
        ws.cell(1,i).font=hf; ws.cell(1,i).fill=hfill
    for r in data["rows"]:
        ws.append([r.get("account_code",""), r.get("account_name",""),
                   r.get("opening_debit",0), r.get("opening_credit",0),
                   r.get("period_debit",0), r.get("period_credit",0),
                   r.get("closing_debit",0), r.get("closing_credit",0)])
    for col, w in [("A",12),("B",20),("C",14),("D",14),("E",14),("F",14),("G",14),("H",14)]:
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    from fastapi.responses import Response
    return Response(content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=account_balance_{data.get('period','')}.xlsx"})


# ═══════════════════════════════════════════════════════════
# 期间列表（基于 fin_periods 表）
# ═══════════════════════════════════════════════════════════

@router.get("/closing/periods-list")
async def closing_periods_list(
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """从 fin_periods 读取期间列表"""
    from app.models.finance.accounting import FinPeriod
    result = await db.execute(
        select(FinPeriod).where(FinPeriod.book_id == book_id).order_by(FinPeriod.period.desc()).limit(24)
    )
    return {"rows": [
        {
            "id": p.id, "period": p.period, "status": p.status,
            "closed_by": p.closed_by, "closed_at": str(p.closed_at) if p.closed_at else None,
            "locked_by": p.locked_by, "locked_at": str(p.locked_at) if p.locked_at else None,
            "remark": p.remark,
        }
        for p in result.scalars()
    ]}


@router.post("/closing/init-periods")
async def init_periods(
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """为当前账套初始化近12个月的期间记录"""
    from app.models.finance.accounting import FinPeriod
    from datetime import date
    today = date.today()
    created = 0
    for i in range(11, -1, -1):
        y, m = today.year, today.month - i
        while m <= 0:
            m += 12; y -= 1
        period = f"{y}-{m:02d}"
        exist = await db.execute(text(
            "SELECT id FROM fin_periods WHERE book_id=:bid AND period=:p"
        ), {"bid": book_id, "p": period})
        if not exist.first():
            db.add(FinPeriod(book_id=book_id, period=period, status="open"))
            created += 1
    return {"ok": True, "created": created}


@router.post("/closing/lock")
async def lock_period(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """锁定期间（locked后不可反结账）"""
    if not period:
        raise HTTPException(400, "请指定期间")
    from app.models.finance.accounting import FinPeriod
    from datetime import datetime
    result = await db.execute(text(
        "SELECT id, status FROM fin_periods WHERE book_id=:bid AND period=:p"
    ), {"bid": book_id, "p": period})
    row = result.first()
    if not row:
        raise HTTPException(404, "期间不存在")
    if row[1] != "closed":
        raise HTTPException(400, "只有已结账的期间才能锁定")
    await db.execute(text("""
        UPDATE fin_periods SET status='locked', locked_by=:u, locked_at=now()
        WHERE book_id=:bid AND period=:p
    """), {"bid": book_id, "p": period, "u": str(current_user.id)})
    db.add(FinAuditLog(book_id=book_id, operator=str(current_user.id),
                        action="lock_period", target=f"period:{period}"))
    return {"ok": True}


# ═══════════════════════════════════════════════════════════
# 结账时同步 fin_periods 状态的辅助函数
# ═══════════════════════════════════════════════════════════

async def _sync_period_status(db: AsyncSession, book_id: int, period: str, status: str, operator: str = ""):
    """同步期间状态到 fin_periods 表"""
    if status == "closed":
        await db.execute(text("""
            INSERT INTO fin_periods (book_id, period, status, closed_by, closed_at)
            VALUES (:bid, :p, 'closed', :u, now())
            ON CONFLICT (book_id, period) DO UPDATE SET
                status='closed', closed_by=:u, closed_at=now()
        """), {"bid": book_id, "p": period, "u": operator})
    elif status == "open":
        await db.execute(text("""
            UPDATE fin_periods SET status='open', closed_by=NULL, closed_at=NULL
            WHERE book_id=:bid AND period=:p
        """), {"bid": book_id, "p": period})
