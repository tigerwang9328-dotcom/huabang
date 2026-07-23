"""
税务管理 API
GET  /api/v1/finance/tax/types          税种列表
POST /api/v1/finance/tax/types          新建税种
PUT  /api/v1/finance/tax/types/{id}     编辑税种
GET  /api/v1/finance/tax/records        税务台账列表
POST /api/v1/finance/tax/records        新建/更新税务台账
PUT  /api/v1/finance/tax/records/{id}/paid  标记已缴
DELETE /api/v1/finance/tax/records/{id}     删除（仅pending）
GET  /api/v1/finance/tax/summary        本年税务汇总
"""
from typing import Optional
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func
from pydantic import BaseModel

from app.api.v1.deps import get_db, get_current_user
from app.models.sys import SysUser as User
from app.models.finance.tax import FinTaxType, FinTaxRecord
from app.models.finance.settings import FinAuditLog

router = APIRouter(prefix="/finance/tax")


def _d(v) -> float:
    return float(v) if v is not None else 0.0


DEFAULT_TAX_TYPES = [
    ("VAT", "增值税", 0.13, "vat", "month"),
    ("CIT", "企业所得税", 0.25, "income", "quarter"),
    ("IIT", "个人所得税", 0.00, "individual", "month"),
    ("CITY", "城市维护建设税", 0.07, "urban", "month"),
    ("EDU", "教育费附加", 0.03, "other", "month"),
    ("LOCAL_EDU", "地方教育附加", 0.02, "other", "month"),
    ("STAMP", "印花税", 0.0003, "stamp", "month"),
]


async def _ensure_default_tax_types(db: AsyncSession, book_id: int) -> None:
    result = await db.execute(text("SELECT COUNT(*) FROM fin_tax_types WHERE book_id=:bid"), {"bid": book_id})
    if (result.scalar() or 0) > 0:
        return
    for code, name, rate, category, period_type in DEFAULT_TAX_TYPES:
        db.add(FinTaxType(
            book_id=book_id,
            tax_code=code,
            tax_name=name,
            tax_rate=rate,
            tax_category=category,
            period_type=period_type,
            is_active=True,
        ))
    await db.flush()


# ── Schemas ──
class TaxTypeCreate(BaseModel):
    tax_code: str
    tax_name: str
    tax_rate: float = 0
    tax_category: str = "vat"
    period_type: str = "month"

class TaxTypeUpdate(BaseModel):
    tax_name: Optional[str] = None
    tax_rate: Optional[float] = None
    tax_category: Optional[str] = None
    period_type: Optional[str] = None
    is_active: Optional[bool] = None

class TaxRecordCreate(BaseModel):
    tax_type_id: int
    period: str                         # YYYY-MM
    tax_base: float = 0
    tax_amount: float = 0
    due_date: Optional[str] = None
    remark: Optional[str] = None

class TaxRecordPay(BaseModel):
    paid_amount: float
    paid_date: str


# ═══════════════════════════════════════════════════════════
# 税种管理
# ═══════════════════════════════════════════════════════════

@router.get("/types")
async def list_tax_types(
    book_id: int = Query(1),
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    await _ensure_default_tax_types(db, book_id)
    q = select(FinTaxType).where(FinTaxType.book_id == book_id)
    if active_only:
        q = q.where(FinTaxType.is_active == True)
    q = q.order_by(FinTaxType.id)
    result = await db.execute(q)
    return {"rows": [
        {
            "id": t.id, "tax_code": t.tax_code, "tax_name": t.tax_name,
            "tax_rate": float(t.tax_rate or 0), "tax_rate_pct": f"{float(t.tax_rate or 0)*100:.2f}%",
            "tax_category": t.tax_category, "period_type": t.period_type,
            "is_active": t.is_active,
        }
        for t in result.scalars()
    ]}


@router.post("/types", status_code=201)
async def create_tax_type(
    body: TaxTypeCreate, book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    t = FinTaxType(book_id=book_id, **body.model_dump())
    db.add(t)
    await db.flush()
    db.add(FinAuditLog(book_id=book_id, operator=str(current_user.id),
                        action="create_tax_type", target=f"tax_type:{t.id}"))
    return {"id": t.id, "ok": True}


@router.put("/types/{type_id}")
async def update_tax_type(
    type_id: int, body: TaxTypeUpdate, book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    t = await db.get(FinTaxType, type_id)
    if not t or t.book_id != book_id:
        raise HTTPException(404, "税种不存在")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(t, k, v)
    db.add(FinAuditLog(book_id=book_id, operator=str(current_user.id),
                        action="update_tax_type", target=f"tax_type:{type_id}"))
    return {"ok": True}


# ═══════════════════════════════════════════════════════════
# 税务台账
# ═══════════════════════════════════════════════════════════

@router.get("/records")
async def list_tax_records(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    year: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    where = "WHERE r.book_id = :bid"
    params: dict = {"bid": book_id}
    if period:
        where += " AND r.period = :period"
        params["period"] = period
    if year:
        where += " AND r.period LIKE :year"
        params["year"] = f"{year}-%"
    if status:
        where += " AND r.status = :status"
        params["status"] = status

    cnt = await db.execute(text(f"SELECT COUNT(*) FROM fin_tax_records r {where}"), params)
    total = cnt.scalar() or 0

    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    result = await db.execute(text(f"""
        SELECT r.id, r.tax_type_id, r.period, r.tax_base, r.tax_amount, r.paid_amount,
               r.status, r.due_date, r.paid_date, r.remark, r.voucher_id,
               t.tax_code, t.tax_name, t.tax_category, t.period_type,
               (r.tax_amount - r.paid_amount) AS outstanding
        FROM fin_tax_records r
        LEFT JOIN fin_tax_types t ON t.id = r.tax_type_id
        {where}
        ORDER BY r.period DESC, t.tax_code
        LIMIT :limit OFFSET :offset
    """), params)

    rows = []
    for r in result.mappings():
        rows.append({
            "id": r["id"], "tax_type_id": r["tax_type_id"], "period": r["period"],
            "tax_code": r["tax_code"] or "", "tax_name": r["tax_name"] or "",
            "tax_category": r["tax_category"] or "", "period_type": r["period_type"] or "",
            "tax_base": _d(r["tax_base"]), "tax_amount": _d(r["tax_amount"]),
            "paid_amount": _d(r["paid_amount"]),
            "outstanding": _d(r["outstanding"]),
            "status": r["status"],
            "due_date": str(r["due_date"]) if r["due_date"] else "",
            "paid_date": str(r["paid_date"]) if r["paid_date"] else "",
            "remark": r["remark"] or "",
            "voucher_id": r["voucher_id"],
        })
    return {"total": total, "page": page, "rows": rows}


@router.post("/records", status_code=201)
async def upsert_tax_record(
    body: TaxRecordCreate, book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """新建或更新（同一账套+税种+期间唯一）"""
    # 查是否存在
    exist = await db.execute(text("""
        SELECT id FROM fin_tax_records
        WHERE book_id = :bid AND tax_type_id = :tid AND period = :period
    """), {"bid": book_id, "tid": body.tax_type_id, "period": body.period})
    row = exist.first()

    if row:
        await db.execute(text("""
            UPDATE fin_tax_records
            SET tax_base = :base, tax_amount = :amount,
                due_date = :due, remark = :remark, updated_at = now()
            WHERE id = :id
        """), {
            "base": body.tax_base, "amount": body.tax_amount,
            "due": body.due_date, "remark": body.remark, "id": row[0],
        })
        rec_id = row[0]
    else:
        r = FinTaxRecord(
            book_id=book_id,
            tax_type_id=body.tax_type_id,
            period=body.period,
            tax_base=body.tax_base,
            tax_amount=body.tax_amount,
            due_date=date.fromisoformat(body.due_date) if body.due_date else None,
            remark=body.remark,
            status="pending",
        )
        db.add(r)
        await db.flush()
        rec_id = r.id

    db.add(FinAuditLog(book_id=book_id, operator=str(current_user.id),
                        action="upsert_tax_record", target=f"tax_record:{rec_id}"))
    return {"id": rec_id, "ok": True}


@router.put("/records/{record_id}/paid")
async def mark_tax_paid(
    record_id: int, body: TaxRecordPay, book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    r = await db.get(FinTaxRecord, record_id)
    if not r or r.book_id != book_id:
        raise HTTPException(404, "记录不存在")

    paid_amount = round(float(body.paid_amount or 0), 2)
    if paid_amount <= 0:
        raise HTTPException(400, "缴纳金额必须大于0")

    r.paid_amount = paid_amount
    r.paid_date = date.fromisoformat(body.paid_date)
    r.status = "paid" if paid_amount >= float(r.tax_amount or 0) else "partial"

    voucher_id = r.voucher_id
    voucher_no = None
    if not voucher_id:
        acct_result = await db.execute(text("""
            SELECT account_code, id FROM fin_accounts
            WHERE book_id = :bid AND account_code IN ('2221', '1002') AND is_active = true
        """), {"bid": book_id})
        acct_ids = {row["account_code"]: row["id"] for row in acct_result.mappings()}
        if not acct_ids.get("2221") or not acct_ids.get("1002"):
            raise HTTPException(400, "科目 2221应交税费 或 1002银行存款 不存在，无法生成缴税凭证")

        tax_result = await db.execute(text("""
            SELECT tax_name FROM fin_tax_types WHERE id = :tid AND book_id = :bid
        """), {"tid": r.tax_type_id, "bid": book_id})
        tax_name = tax_result.scalar() or "税款"

        from app.models.finance.accounting import FinVoucher, FinVoucherLine
        from app.api.v1.finance.vouchers import next_voucher_no
        no_data = await next_voucher_no(book_id, db, current_user)
        voucher_no = no_data["next_no"]
        summary = f"缴纳{r.period} {tax_name}"

        v = FinVoucher(
            book_id=book_id, voucher_no=voucher_no, voucher_type="记",
            voucher_date=r.paid_date, source_type="tax_payment", source_ref=f"tax_record:{record_id}",
            summary=summary, status="posted",
            created_by=str(current_user.id), reviewed_by=str(current_user.id), reviewed_at=datetime.now(),
            posted_by=str(current_user.id), posted_at=datetime.now(),
            total_debit=paid_amount, total_credit=paid_amount,
            period=r.paid_date.strftime("%Y-%m"),
        )
        db.add(v)
        await db.flush()
        voucher_id = v.id
        r.voucher_id = voucher_id

        db.add(FinVoucherLine(
            voucher_id=v.id, line_no=1, account_id=acct_ids["2221"], account_code="2221",
            debit_amount=paid_amount, credit_amount=0, summary=summary, biz_date=r.paid_date,
        ))
        db.add(FinVoucherLine(
            voucher_id=v.id, line_no=2, account_id=acct_ids["1002"], account_code="1002",
            debit_amount=0, credit_amount=paid_amount, summary=summary, biz_date=r.paid_date,
        ))

    db.add(FinAuditLog(book_id=book_id, operator=str(current_user.id),
                        action="pay_tax", target=f"tax_record:{record_id}",
                        detail=f"已缴{paid_amount}, voucher_id={voucher_id or ''}"))
    return {"ok": True, "status": r.status, "voucher_id": voucher_id, "voucher_no": voucher_no}


@router.delete("/records/{record_id}")
async def delete_tax_record(
    record_id: int, book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    r = await db.get(FinTaxRecord, record_id)
    if not r or r.book_id != book_id:
        raise HTTPException(404, "记录不存在")
    if r.status != "pending":
        raise HTTPException(400, "已缴税记录不可删除")
    await db.delete(r)
    db.add(FinAuditLog(book_id=book_id, operator=str(current_user.id),
                        action="delete_tax_record", target=f"tax_record:{record_id}"))
    return {"ok": True}


# ═══════════════════════════════════════════════════════════
# 年度税务汇总
# ═══════════════════════════════════════════════════════════

@router.get("/summary")
async def tax_summary(
    book_id: int = Query(1),
    year: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    if not year:
        year = str(date.today().year)
    result = await db.execute(text("""
        SELECT t.tax_code, t.tax_name, t.tax_category,
               COALESCE(SUM(r.tax_amount), 0) AS total_amount,
               COALESCE(SUM(r.paid_amount), 0) AS total_paid,
               COUNT(r.id) AS period_count
        FROM fin_tax_types t
        LEFT JOIN fin_tax_records r ON r.tax_type_id = t.id
              AND r.book_id = :bid AND r.period LIKE :year
        WHERE t.book_id = :bid AND t.is_active = true
        GROUP BY t.tax_code, t.tax_name, t.tax_category
        ORDER BY t.tax_code
    """), {"bid": book_id, "year": f"{year}-%"})

    rows = []
    total_payable = total_paid = 0
    for r in result.mappings():
        amt = _d(r["total_amount"])
        paid = _d(r["total_paid"])
        outstanding = amt - paid
        total_payable += amt
        total_paid += paid
        rows.append({
            "tax_code": r["tax_code"], "tax_name": r["tax_name"],
            "tax_category": r["tax_category"], "period_count": r["period_count"],
            "total_amount": amt, "total_paid": paid, "outstanding": outstanding,
        })

    return {
        "year": year,
        "rows": rows,
        "total_payable": round(total_payable, 2),
        "total_paid": round(total_paid, 2),
        "total_outstanding": round(total_payable - total_paid, 2),
    }


# ═══════════════════════════════════════════════════════════
# 税务风险提示（待申报 / 逾期未缴）
# ═══════════════════════════════════════════════════════════

@router.get("/alerts")
async def tax_alerts(
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    today = date.today()
    result = await db.execute(text("""
        SELECT r.id, r.period, r.tax_amount, r.paid_amount, r.due_date, r.status,
               t.tax_name
        FROM fin_tax_records r
        JOIN fin_tax_types t ON t.id = r.tax_type_id
        WHERE r.book_id = :bid AND r.status IN ('pending', 'partial')
        ORDER BY r.due_date NULLS LAST
    """), {"bid": book_id})

    alerts = []
    for r in result.mappings():
        due = r["due_date"]
        overdue = due and due < today
        due_soon = due and (today <= due <= today + timedelta(days=7))
        if overdue or due_soon:
            alerts.append({
                "id": r["id"], "tax_name": r["tax_name"], "period": r["period"],
                "tax_amount": _d(r["tax_amount"]), "paid_amount": _d(r["paid_amount"]),
                "outstanding": _d(r["tax_amount"]) - _d(r["paid_amount"]),
                "due_date": str(due) if due else "",
                "level": "danger" if overdue else "warning",
                "message": f"{'已逾期' if overdue else '即将到期'} - {r['tax_name']} {r['period']}",
            })
    return {"alerts": alerts, "count": len(alerts)}
