"""
凭证管理 API
对标虎狼 routes.py 凭证CRUD + 审核/过账 + services.py 凭证引擎
"""
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func, delete
from pydantic import BaseModel

from app.api.v1.deps import get_db, get_current_user
from app.models.sys import SysUser as User
from app.models.finance.accounting import FinVoucher, FinVoucherLine, FinAccount, FinLedgerBalance
from app.models.finance.settings import FinAuditLog

router = APIRouter(prefix="/finance")


# ── Schemas ──
class VoucherLineIn(BaseModel):
    account_id: int
    account_code: Optional[str] = None
    debit_amount: float = 0
    credit_amount: float = 0
    summary: Optional[str] = None
    biz_date: Optional[str] = None
    customer_id: Optional[int] = None
    supplier_id: Optional[int] = None
    employee_id: Optional[int] = None
    department_id: Optional[int] = None
    project_code: Optional[str] = None
    store_id: Optional[int] = None
    order_no: Optional[str] = None

class VoucherCreate(BaseModel):
    voucher_date: str           # YYYY-MM-DD
    voucher_type: str = "记"
    summary: Optional[str] = None
    source_type: str = "manual"
    source_ref: Optional[str] = None
    status: str = "draft"
    lines: List[VoucherLineIn]


# ═══════════════════════════════════════════════════════════
# 凭证列表
# ═══════════════════════════════════════════════════════════

@router.get("/vouchers")
async def list_vouchers(
    book_id: int = Query(1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
    status: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    voucher_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    where = "WHERE v.book_id = :bid"
    params = {"bid": book_id}
    if status:
        where += " AND v.status = :st"
        params["st"] = status
    if period:
        where += " AND to_char(v.voucher_date, 'YYYY-MM') = :period"
        params["period"] = period
    if voucher_type:
        where += " AND v.voucher_type = :vtype"
        params["vtype"] = voucher_type

    cnt = await db.execute(text(f"SELECT COUNT(*) FROM fin_vouchers v {where}"), params)
    total = cnt.scalar() or 0

    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    result = await db.execute(text(f"""
        SELECT v.id, v.voucher_no, v.voucher_type, v.voucher_date, v.summary,
               v.status, v.source_type, v.created_by, v.total_debit, v.total_credit
        FROM fin_vouchers v {where}
        ORDER BY v.voucher_date DESC, v.id DESC
        LIMIT :limit OFFSET :offset
    """), params)

    return {
        "total": total, "page": page,
        "rows": [
            {
                "id": r["id"], "voucher_no": r["voucher_no"], "voucher_type": r["voucher_type"],
                "voucher_date": str(r["voucher_date"]), "summary": r["summary"] or "",
                "status": r["status"], "source_type": r["source_type"],
                "created_by": r["created_by"] or "", "total_debit": float(r["total_debit"] or 0),
                "total_credit": float(r["total_credit"] or 0),
            }
            for r in result.mappings()
        ],
    }


# ═══════════════════════════════════════════════════════════
# 下一凭证号
# ═══════════════════════════════════════════════════════════

@router.get("/vouchers/next-no")
async def next_voucher_no(
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """生成下一个凭证号（格式：YYYYMM-NNN）"""
    today = date.today()
    prefix = f"{today.year}{today.month:02d}"
    result = await db.execute(text("""
        SELECT voucher_no FROM fin_vouchers
        WHERE book_id = :bid AND voucher_no LIKE :pf
        ORDER BY voucher_no DESC LIMIT 1
    """), {"bid": book_id, "pf": f"{prefix}%"})
    last = result.scalar()
    if last:
        try:
            seq = int(last.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return {"next_no": f"{prefix}-{seq:03d}", "voucher_type": "记", "ok": True}


# ═══════════════════════════════════════════════════════════
# 凭证详情
# ═══════════════════════════════════════════════════════════

@router.get("/vouchers/{voucher_id}")
async def get_voucher(
    voucher_id: int,
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    vr = await db.execute(select(FinVoucher).where(FinVoucher.id == voucher_id))
    v = vr.scalar_one_or_none()
    if not v:
        raise HTTPException(404, "凭证不存在")

    lr = await db.execute(text("""
        SELECT vl.*, a.account_name
        FROM fin_voucher_lines vl
        JOIN fin_accounts a ON a.id = vl.account_id
        WHERE vl.voucher_id = :vid ORDER BY vl.line_no
    """), {"vid": voucher_id})

    return {
        "id": v.id, "voucher_no": v.voucher_no, "voucher_type": v.voucher_type,
        "voucher_date": str(v.voucher_date), "summary": v.summary or "",
        "status": v.status, "source_type": v.source_type,
        "created_by": v.created_by or "", "total_debit": float(v.total_debit or 0),
        "lines": [
            {
                "id": l["id"], "line_no": l["line_no"], "account_id": l["account_id"],
                "account_code": l["account_code"] or "", "account_name": l["account_name"],
                "debit_amount": float(l["debit_amount"] or 0),
                "credit_amount": float(l["credit_amount"] or 0),
                "summary": l["summary"] or "",
                "biz_date": str(l["biz_date"]) if l["biz_date"] else None,
                "customer_id": l["customer_id"], "supplier_id": l["supplier_id"],
                "employee_id": l["employee_id"], "department_id": l["department_id"],
                "project_code": l["project_code"] or "", "store_id": l["store_id"],
                "order_no": l["order_no"] or "",
            }
            for l in lr.mappings()
        ],
    }




# ═══════════════════════════════════════════════════════════
# 创建凭证
# ═══════════════════════════════════════════════════════════

@router.post("/vouchers", status_code=201)
async def create_voucher(
    body: VoucherCreate, book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """创建凭证（含分录，自动校验借贷平衡）"""
    if not body.lines or len(body.lines) < 2:
        raise HTTPException(400, "凭证至少需要2条分录")

    total_debit = sum(l.debit_amount for l in body.lines)
    total_credit = sum(l.credit_amount for l in body.lines)
    if abs(total_debit - total_credit) > 0.01:
        raise HTTPException(400, f"借贷不平衡: 借方={total_debit}, 贷方={total_credit}")
    if body.status not in ("draft", "reviewed"):
        raise HTTPException(400, "新建凭证状态只能为 draft 或 reviewed")
    for line in body.lines:
        if line.debit_amount > 0 and line.credit_amount > 0:
            raise HTTPException(400, "同一分录行不能同时填写借方和贷方金额")

    # 生成凭证号
    no_data = await next_voucher_no(book_id, db, current_user)
    voucher_no = no_data["next_no"]

    v = FinVoucher(
        book_id=book_id, voucher_no=voucher_no,
        voucher_type=body.voucher_type,
        voucher_date=date.fromisoformat(body.voucher_date),
        summary=body.summary, source_type=body.source_type,
        source_ref=body.source_ref,
        status=body.status,
        reviewed_by=str(current_user.id) if body.status == "reviewed" else None,
        reviewed_at=datetime.now() if body.status == "reviewed" else None,
        created_by=current_user.username if hasattr(current_user, 'username') else str(current_user.id),
        total_debit=total_debit, total_credit=total_credit,
    )
    db.add(v)
    await db.flush()

    account_ids = {line.account_id for line in body.lines}
    account_codes = {line.account_code for line in body.lines if line.account_code}
    acct_rows = await db.execute(
        select(FinAccount).where(FinAccount.book_id == book_id, FinAccount.id.in_(account_ids))
    )
    account_by_id = {a.id: a for a in acct_rows.scalars()}
    code_rows = await db.execute(
        select(FinAccount).where(FinAccount.book_id == book_id, FinAccount.account_code.in_(account_codes))
    )
    account_by_code = {a.account_code: a for a in code_rows.scalars()}

    for i, line in enumerate(body.lines, 1):
        acct = account_by_id.get(line.account_id) or account_by_code.get(line.account_code)
        if not acct:
            raise HTTPException(400, f"第{i}行科目不存在或不属于当前账套")
        line_biz_date = date.fromisoformat(line.biz_date) if line.biz_date else None
        db.add(FinVoucherLine(
            voucher_id=v.id, line_no=i, account_id=acct.id,
            account_code=acct.account_code,
            debit_amount=line.debit_amount, credit_amount=line.credit_amount,
            summary=line.summary,
            biz_date=line_biz_date,
            customer_id=line.customer_id, supplier_id=line.supplier_id,
            employee_id=line.employee_id, department_id=line.department_id,
            project_code=line.project_code, store_id=line.store_id,
            order_no=line.order_no,
        ))

    db.add(FinAuditLog(book_id=book_id, operator=str(current_user.id),
                        action="create_voucher", target=f"voucher:{v.id}", detail=voucher_no))

    return {"id": v.id, "voucher_no": voucher_no}


# ═══════════════════════════════════════════════════════════
# 删除凭证
# ═══════════════════════════════════════════════════════════

@router.delete("/vouchers/{voucher_id}")
async def delete_voucher(
    voucher_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    vr = await db.execute(select(FinVoucher).where(FinVoucher.id == voucher_id))
    v = vr.scalar_one_or_none()
    if not v:
        raise HTTPException(404, "凭证不存在")
    if v.status in ("posted", "reviewed"):
        raise HTTPException(400, f"凭证状态为{v.status}，不可删除，请先反审核/反过账")

    await db.execute(delete(FinVoucherLine).where(FinVoucherLine.voucher_id == voucher_id))
    await db.delete(v)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════
# 审核 / 反审核
# ═══════════════════════════════════════════════════════════

@router.post("/vouchers/{voucher_id}/review")
async def review_voucher(
    voucher_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """审核凭证 (draft → reviewed)"""
    vr = await db.execute(select(FinVoucher).where(FinVoucher.id == voucher_id))
    v = vr.scalar_one_or_none()
    if not v:
        raise HTTPException(404)
    if v.status != "draft":
        raise HTTPException(400, f"当前状态 {v.status}，无法审核")

    v.status = "reviewed"
    v.reviewed_by = str(current_user.id)
    from datetime import datetime
    v.reviewed_at = datetime.now()

    db.add(FinAuditLog(book_id=v.book_id, operator=str(current_user.id),
                        action="review_voucher", target=f"voucher:{v.id}", detail=v.voucher_no))
    return {"ok": True, "status": "reviewed"}


@router.post("/vouchers/{voucher_id}/unreview")
async def unreview_voucher(
    voucher_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """反审核 (reviewed → draft)"""
    vr = await db.execute(select(FinVoucher).where(FinVoucher.id == voucher_id))
    v = vr.scalar_one_or_none()
    if not v:
        raise HTTPException(404)
    if v.status != "reviewed":
        raise HTTPException(400, f"当前状态 {v.status}，无法反审核")
    v.status = "draft"
    v.reviewed_by = None
    v.reviewed_at = None
    db.add(FinAuditLog(book_id=v.book_id, operator=str(current_user.id),
                        action="unreview_voucher", target=f"voucher:{v.id}", detail=v.voucher_no))
    return {"ok": True, "status": "draft"}


# ═══════════════════════════════════════════════════════════
# 过账 / 反过账
# ═══════════════════════════════════════════════════════════

@router.post("/vouchers/{voucher_id}/post")
async def post_voucher(
    voucher_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    过账凭证 (reviewed → posted)
    过账时更新 fin_ledger_balances（科目余额表）
    """
    vr = await db.execute(select(FinVoucher).where(FinVoucher.id == voucher_id))
    v = vr.scalar_one_or_none()
    if not v:
        raise HTTPException(404)
    if v.status != "reviewed":
        raise HTTPException(400, f"当前状态 {v.status}，需先审核再过账")

    # 获取分录
    lines = await db.execute(
        select(FinVoucherLine).where(FinVoucherLine.voucher_id == voucher_id)
    )
    period = f"{v.voucher_date.year}-{v.voucher_date.month:02d}"

    for line in lines.scalars():
        # UPSERT 科目余额
        await db.execute(text("""
            INSERT INTO fin_ledger_balances (book_id, account_id, period, period_debit, period_credit)
            VALUES (:bid, :aid, :p, :d, :c)
            ON CONFLICT (book_id, account_id, period) DO UPDATE SET
                period_debit = fin_ledger_balances.period_debit + EXCLUDED.period_debit,
                period_credit = fin_ledger_balances.period_credit + EXCLUDED.period_credit
        """), {
            "bid": v.book_id, "aid": line.account_id, "p": period,
            "d": float(line.debit_amount or 0), "c": float(line.credit_amount or 0),
        })

    from datetime import datetime
    v.status = "posted"
    v.posted_by = str(current_user.id)
    v.posted_at = datetime.now()

    db.add(FinAuditLog(book_id=v.book_id, operator=str(current_user.id),
                        action="post_voucher", target=f"voucher:{v.id}", detail=v.voucher_no))
    return {"ok": True, "status": "posted"}


@router.post("/vouchers/{voucher_id}/unpost")
async def unpost_voucher(
    voucher_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """反过账 (posted → reviewed)，回退科目余额"""
    vr = await db.execute(select(FinVoucher).where(FinVoucher.id == voucher_id))
    v = vr.scalar_one_or_none()
    if not v:
        raise HTTPException(404)
    if v.status != "posted":
        raise HTTPException(400, f"当前状态 {v.status}，无法反过账")

    lines = await db.execute(
        select(FinVoucherLine).where(FinVoucherLine.voucher_id == voucher_id)
    )
    period = f"{v.voucher_date.year}-{v.voucher_date.month:02d}"

    for line in lines.scalars():
        await db.execute(text("""
            UPDATE fin_ledger_balances SET
                period_debit = period_debit - :d,
                period_credit = period_credit - :c
            WHERE book_id = :bid AND account_id = :aid AND period = :p
        """), {
            "bid": v.book_id, "aid": line.account_id, "p": period,
            "d": float(line.debit_amount or 0), "c": float(line.credit_amount or 0),
        })

    v.status = "reviewed"
    v.posted_by = None
    v.posted_at = None

    db.add(FinAuditLog(book_id=v.book_id, operator=str(current_user.id),
                        action="unpost_voucher", target=f"voucher:{v.id}", detail=v.voucher_no))
    return {"ok": True, "status": "reviewed"}
