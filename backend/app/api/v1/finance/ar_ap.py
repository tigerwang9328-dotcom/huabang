"""
应收/应付单据 API + 账龄分析
============================
对标虎狼 routes.py 中 receivable_headers/payable_headers 及 ar_aging 相关路由。
新增5张表：fin_recv_orders / fin_recv_order_lines / fin_payable_orders / fin_payable_order_lines
账龄分析：30/60/90/120/120+ 天分组，支持客户/供应商维度。
"""
from typing import Optional, List
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from pydantic import BaseModel

from app.api.v1.deps import get_db, get_current_user
from app.models.sys import SysUser as User
from app.models.finance.business import (
    FinRecvOrder, FinRecvOrderLine,
    FinPayableOrder, FinPayableOrderLine,
    FinCustomer, FinSupplier,
)

router = APIRouter(prefix="/finance")


# ══════════════════════════════════════════════════════════════
# Schemas
# ══════════════════════════════════════════════════════════════

class RecvOrderLineIn(BaseModel):
    line_no: int = 1
    item_name: str
    spec: str = ""
    quantity: float = 1
    unit_price: float = 0
    amount: float = 0
    tax_rate: float = 0
    tax_amount: float = 0
    remark: str = ""


class RecvOrderIn(BaseModel):
    order_no: str
    order_date: date
    period: Optional[str] = None
    customer_id: Optional[int] = None
    customer_name: str = ""
    contact: str = ""
    total_amount: float = 0
    remark: str = ""
    lines: List[RecvOrderLineIn] = []


class PayableOrderIn(BaseModel):
    order_no: str
    order_date: date
    period: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_name: str = ""
    contact: str = ""
    total_amount: float = 0
    remark: str = ""
    lines: List[RecvOrderLineIn] = []


class CollectIn(BaseModel):
    collect_amount: float
    remark: str = ""


# ══════════════════════════════════════════════════════════════
# 应收单据
# ══════════════════════════════════════════════════════════════

def _recv_row(o: FinRecvOrder) -> dict:
    balance = float(o.total_amount or 0) - float(o.received_amount or 0)
    return {
        "id": o.id, "order_no": o.order_no, "period": o.period,
        "order_date": str(o.order_date) if o.order_date else "",
        "customer_id": o.customer_id, "customer_name": o.customer_name,
        "contact": o.contact,
        "total_amount": float(o.total_amount or 0),
        "received_amount": float(o.received_amount or 0),
        "balance": round(balance, 2),
        "status": o.status, "remark": o.remark,
        "created_by": o.created_by,
        "created_at": str(o.created_at) if o.created_at else "",
    }


@router.get("/recv-orders")
async def list_recv_orders(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    customer_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    q = select(FinRecvOrder).where(FinRecvOrder.book_id == book_id)
    if period:
        q = q.where(FinRecvOrder.period == period)
    if status:
        q = q.where(FinRecvOrder.status == status)
    if customer_id:
        q = q.where(FinRecvOrder.customer_id == customer_id)
    q = q.order_by(FinRecvOrder.order_date.desc(), FinRecvOrder.id.desc())
    result = await db.execute(q)
    rows = result.scalars().all()

    # KPI
    total_amount = sum(float(r.total_amount or 0) for r in rows)
    received_amount = sum(float(r.received_amount or 0) for r in rows)
    return {
        "rows": [_recv_row(r) for r in rows],
        "total": len(rows),
        "kpi": {
            "total_amount": round(total_amount, 2),
            "received_amount": round(received_amount, 2),
            "balance": round(total_amount - received_amount, 2),
            "open_count": sum(1 for r in rows if r.status in ("open", "partial")),
        },
    }


@router.get("/recv-orders/{order_id}")
async def get_recv_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    o = await db.get(FinRecvOrder, order_id)
    if not o:
        raise HTTPException(404, "应收单据不存在")
    lines_res = await db.execute(
        select(FinRecvOrderLine).where(FinRecvOrderLine.order_id == order_id)
        .order_by(FinRecvOrderLine.line_no)
    )
    lines = [
        {
            "id": l.id, "line_no": l.line_no, "item_name": l.item_name, "spec": l.spec,
            "quantity": float(l.quantity or 1), "unit_price": float(l.unit_price or 0),
            "amount": float(l.amount or 0), "tax_rate": float(l.tax_rate or 0),
            "tax_amount": float(l.tax_amount or 0), "remark": l.remark,
        }
        for l in lines_res.scalars()
    ]
    return {**_recv_row(o), "lines": lines}


@router.post("/recv-orders", status_code=201)
async def create_recv_order(
    body: RecvOrderIn,
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    # auto-fill period from order_date
    period = body.period or body.order_date.strftime("%Y-%m")
    # auto-fill customer_name from customer_id if missing
    customer_name = body.customer_name
    if body.customer_id and not customer_name:
        c = await db.get(FinCustomer, body.customer_id)
        if c:
            customer_name = c.name

    # compute total from lines if lines provided and total_amount == 0
    total_amount = body.total_amount
    if total_amount == 0 and body.lines:
        total_amount = sum(l.amount for l in body.lines)

    o = FinRecvOrder(
        book_id=book_id, order_no=body.order_no, order_date=body.order_date,
        period=period, customer_id=body.customer_id, customer_name=customer_name,
        contact=body.contact, total_amount=total_amount,
        received_amount=0, status="open",
        remark=body.remark, created_by=str(current_user.id),
    )
    db.add(o)
    await db.flush()

    for i, line in enumerate(body.lines):
        db.add(FinRecvOrderLine(
            order_id=o.id, line_no=i + 1,
            item_name=line.item_name, spec=line.spec,
            quantity=line.quantity, unit_price=line.unit_price,
            amount=line.amount, tax_rate=line.tax_rate,
            tax_amount=line.tax_amount, remark=line.remark,
        ))
    await db.commit()
    return {"id": o.id, "order_no": o.order_no}


@router.put("/recv-orders/{order_id}")
async def update_recv_order(
    order_id: int,
    body: RecvOrderIn,
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    o = await db.get(FinRecvOrder, order_id)
    if not o:
        raise HTTPException(404, "应收单据不存在")
    if o.status == "settled":
        raise HTTPException(400, "已结清单据不允许修改")
    o.order_no = body.order_no
    o.order_date = body.order_date
    o.period = body.period or body.order_date.strftime("%Y-%m")
    o.customer_id = body.customer_id
    o.customer_name = body.customer_name
    o.contact = body.contact
    o.total_amount = body.total_amount
    o.remark = body.remark

    # refresh lines
    existing = await db.execute(
        select(FinRecvOrderLine).where(FinRecvOrderLine.order_id == order_id)
    )
    for row in existing.scalars():
        await db.delete(row)
    await db.flush()
    for i, line in enumerate(body.lines):
        db.add(FinRecvOrderLine(
            order_id=order_id, line_no=i + 1,
            item_name=line.item_name, spec=line.spec,
            quantity=line.quantity, unit_price=line.unit_price,
            amount=line.amount, tax_rate=line.tax_rate,
            tax_amount=line.tax_amount, remark=line.remark,
        ))
    await db.commit()
    return {"ok": True}


@router.post("/recv-orders/{order_id}/collect")
async def collect_recv_order(
    order_id: int,
    body: CollectIn,
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """登记回款（部分或全额）"""
    o = await db.get(FinRecvOrder, order_id)
    if not o:
        raise HTTPException(404, "应收单据不存在")
    o.received_amount = Decimal(str(o.received_amount or 0)) + Decimal(str(body.collect_amount))
    balance = Decimal(str(o.total_amount or 0)) - o.received_amount
    if balance <= 0:
        o.status = "settled"
    elif o.received_amount > 0:
        o.status = "partial"
    await db.commit()
    return {"ok": True, "received_amount": float(o.received_amount), "balance": float(max(balance, 0))}


@router.delete("/recv-orders/{order_id}", status_code=204)
async def delete_recv_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    o = await db.get(FinRecvOrder, order_id)
    if not o:
        raise HTTPException(404, "应收单据不存在")
    await db.delete(o)
    await db.commit()


# ══════════════════════════════════════════════════════════════
# 应付单据
# ══════════════════════════════════════════════════════════════

def _payable_row(o: FinPayableOrder) -> dict:
    balance = float(o.total_amount or 0) - float(o.paid_amount or 0)
    return {
        "id": o.id, "order_no": o.order_no, "period": o.period,
        "order_date": str(o.order_date) if o.order_date else "",
        "supplier_id": o.supplier_id, "supplier_name": o.supplier_name,
        "contact": o.contact,
        "total_amount": float(o.total_amount or 0),
        "paid_amount": float(o.paid_amount or 0),
        "balance": round(balance, 2),
        "status": o.status, "remark": o.remark,
        "created_by": o.created_by,
        "created_at": str(o.created_at) if o.created_at else "",
    }


@router.get("/payable-orders")
async def list_payable_orders(
    book_id: int = Query(1),
    period: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    supplier_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    q = select(FinPayableOrder).where(FinPayableOrder.book_id == book_id)
    if period:
        q = q.where(FinPayableOrder.period == period)
    if status:
        q = q.where(FinPayableOrder.status == status)
    if supplier_id:
        q = q.where(FinPayableOrder.supplier_id == supplier_id)
    q = q.order_by(FinPayableOrder.order_date.desc(), FinPayableOrder.id.desc())
    result = await db.execute(q)
    rows = result.scalars().all()

    total_amount = sum(float(r.total_amount or 0) for r in rows)
    paid_amount = sum(float(r.paid_amount or 0) for r in rows)
    return {
        "rows": [_payable_row(r) for r in rows],
        "total": len(rows),
        "kpi": {
            "total_amount": round(total_amount, 2),
            "paid_amount": round(paid_amount, 2),
            "balance": round(total_amount - paid_amount, 2),
            "open_count": sum(1 for r in rows if r.status in ("open", "partial")),
        },
    }


@router.get("/payable-orders/{order_id}")
async def get_payable_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    o = await db.get(FinPayableOrder, order_id)
    if not o:
        raise HTTPException(404, "应付单据不存在")
    lines_res = await db.execute(
        select(FinPayableOrderLine).where(FinPayableOrderLine.order_id == order_id)
        .order_by(FinPayableOrderLine.line_no)
    )
    lines = [
        {
            "id": l.id, "line_no": l.line_no, "item_name": l.item_name, "spec": l.spec,
            "quantity": float(l.quantity or 1), "unit_price": float(l.unit_price or 0),
            "amount": float(l.amount or 0), "tax_rate": float(l.tax_rate or 0),
            "tax_amount": float(l.tax_amount or 0), "remark": l.remark,
        }
        for l in lines_res.scalars()
    ]
    return {**_payable_row(o), "lines": lines}


@router.post("/payable-orders", status_code=201)
async def create_payable_order(
    body: PayableOrderIn,
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    period = body.period or body.order_date.strftime("%Y-%m")
    supplier_name = body.supplier_name
    if body.supplier_id and not supplier_name:
        s = await db.get(FinSupplier, body.supplier_id)
        if s:
            supplier_name = s.name

    total_amount = body.total_amount
    if total_amount == 0 and body.lines:
        total_amount = sum(l.amount for l in body.lines)

    o = FinPayableOrder(
        book_id=book_id, order_no=body.order_no, order_date=body.order_date,
        period=period, supplier_id=body.supplier_id, supplier_name=supplier_name,
        contact=body.contact, total_amount=total_amount,
        paid_amount=0, status="open",
        remark=body.remark, created_by=str(current_user.id),
    )
    db.add(o)
    await db.flush()

    for i, line in enumerate(body.lines):
        db.add(FinPayableOrderLine(
            order_id=o.id, line_no=i + 1,
            item_name=line.item_name, spec=line.spec,
            quantity=line.quantity, unit_price=line.unit_price,
            amount=line.amount, tax_rate=line.tax_rate,
            tax_amount=line.tax_amount, remark=line.remark,
        ))
    await db.commit()
    return {"id": o.id, "order_no": o.order_no}


@router.put("/payable-orders/{order_id}")
async def update_payable_order(
    order_id: int,
    body: PayableOrderIn,
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    o = await db.get(FinPayableOrder, order_id)
    if not o:
        raise HTTPException(404, "应付单据不存在")
    if o.status == "settled":
        raise HTTPException(400, "已结清单据不允许修改")
    o.order_no = body.order_no
    o.order_date = body.order_date
    o.period = body.period or body.order_date.strftime("%Y-%m")
    o.supplier_id = body.supplier_id
    o.supplier_name = body.supplier_name
    o.contact = body.contact
    o.total_amount = body.total_amount
    o.remark = body.remark

    existing = await db.execute(
        select(FinPayableOrderLine).where(FinPayableOrderLine.order_id == order_id)
    )
    for row in existing.scalars():
        await db.delete(row)
    await db.flush()
    for i, line in enumerate(body.lines):
        db.add(FinPayableOrderLine(
            order_id=order_id, line_no=i + 1,
            item_name=line.item_name, spec=line.spec,
            quantity=line.quantity, unit_price=line.unit_price,
            amount=line.amount, tax_rate=line.tax_rate,
            tax_amount=line.tax_amount, remark=line.remark,
        ))
    await db.commit()
    return {"ok": True}


@router.post("/payable-orders/{order_id}/pay")
async def pay_payable_order(
    order_id: int,
    body: CollectIn,
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """登记付款（部分或全额）"""
    o = await db.get(FinPayableOrder, order_id)
    if not o:
        raise HTTPException(404, "应付单据不存在")
    o.paid_amount = Decimal(str(o.paid_amount or 0)) + Decimal(str(body.collect_amount))
    balance = Decimal(str(o.total_amount or 0)) - o.paid_amount
    if balance <= 0:
        o.status = "settled"
    elif o.paid_amount > 0:
        o.status = "partial"
    await db.commit()
    return {"ok": True, "paid_amount": float(o.paid_amount), "balance": float(max(balance, 0))}


@router.delete("/payable-orders/{order_id}", status_code=204)
async def delete_payable_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    o = await db.get(FinPayableOrder, order_id)
    if not o:
        raise HTTPException(404, "应付单据不存在")
    await db.delete(o)
    await db.commit()


# ══════════════════════════════════════════════════════════════
# 账龄分析（AR + AP）
# ══════════════════════════════════════════════════════════════

def _aging_bucket(days: int) -> str:
    if days <= 30:
        return "0-30天"
    elif days <= 60:
        return "31-60天"
    elif days <= 90:
        return "61-90天"
    elif days <= 120:
        return "91-120天"
    else:
        return "120天以上"


@router.get("/aging/receivable")
async def ar_aging(
    book_id: int = Query(1),
    as_of: Optional[str] = Query(None, description="分析基准日 YYYY-MM-DD，默认今天"),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """
    应收账龄分析（基于 fin_recv_orders，未结清单据）
    按客户 × 账龄分组汇总
    """
    base_date = date.fromisoformat(as_of) if as_of else date.today()
    result = await db.execute(
        select(FinRecvOrder).where(
            FinRecvOrder.book_id == book_id,
            FinRecvOrder.status.in_(["open", "partial"]),
        ).order_by(FinRecvOrder.order_date)
    )
    rows = result.scalars().all()

    # 按客户聚合
    customer_map: dict = {}
    buckets_summary = {"0-30天": 0.0, "31-60天": 0.0, "61-90天": 0.0, "91-120天": 0.0, "120天以上": 0.0}
    total_balance = 0.0

    for r in rows:
        days = (base_date - r.order_date).days if r.order_date else 0
        bucket = _aging_bucket(days)
        balance = float(r.total_amount or 0) - float(r.received_amount or 0)
        if balance <= 0:
            continue

        customer_key = r.customer_name or f"客户{r.customer_id}"
        if customer_key not in customer_map:
            customer_map[customer_key] = {
                "customer_name": customer_key,
                "customer_id": r.customer_id,
                "total_balance": 0.0,
                "0-30天": 0.0, "31-60天": 0.0, "61-90天": 0.0,
                "91-120天": 0.0, "120天以上": 0.0,
                "orders": [],
            }
        customer_map[customer_key][bucket] = round(customer_map[customer_key][bucket] + balance, 2)
        customer_map[customer_key]["total_balance"] = round(customer_map[customer_key]["total_balance"] + balance, 2)
        customer_map[customer_key]["orders"].append({
            "order_no": r.order_no, "order_date": str(r.order_date),
            "balance": round(balance, 2), "days": days, "bucket": bucket,
        })
        buckets_summary[bucket] = round(buckets_summary[bucket] + balance, 2)
        total_balance = round(total_balance + balance, 2)

    return {
        "as_of": str(base_date),
        "total_balance": total_balance,
        "buckets": buckets_summary,
        "customers": sorted(customer_map.values(), key=lambda x: -x["total_balance"]),
    }


@router.get("/aging/payable")
async def ap_aging(
    book_id: int = Query(1),
    as_of: Optional[str] = Query(None, description="分析基准日 YYYY-MM-DD，默认今天"),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """
    应付账龄分析（基于 fin_payable_orders，未结清单据）
    按供应商 × 账龄分组汇总
    """
    base_date = date.fromisoformat(as_of) if as_of else date.today()
    result = await db.execute(
        select(FinPayableOrder).where(
            FinPayableOrder.book_id == book_id,
            FinPayableOrder.status.in_(["open", "partial"]),
        ).order_by(FinPayableOrder.order_date)
    )
    rows = result.scalars().all()

    supplier_map: dict = {}
    buckets_summary = {"0-30天": 0.0, "31-60天": 0.0, "61-90天": 0.0, "91-120天": 0.0, "120天以上": 0.0}
    total_balance = 0.0

    for r in rows:
        days = (base_date - r.order_date).days if r.order_date else 0
        bucket = _aging_bucket(days)
        balance = float(r.total_amount or 0) - float(r.paid_amount or 0)
        if balance <= 0:
            continue

        supplier_key = r.supplier_name or f"供应商{r.supplier_id}"
        if supplier_key not in supplier_map:
            supplier_map[supplier_key] = {
                "supplier_name": supplier_key,
                "supplier_id": r.supplier_id,
                "total_balance": 0.0,
                "0-30天": 0.0, "31-60天": 0.0, "61-90天": 0.0,
                "91-120天": 0.0, "120天以上": 0.0,
                "orders": [],
            }
        supplier_map[supplier_key][bucket] = round(supplier_map[supplier_key][bucket] + balance, 2)
        supplier_map[supplier_key]["total_balance"] = round(supplier_map[supplier_key]["total_balance"] + balance, 2)
        supplier_map[supplier_key]["orders"].append({
            "order_no": r.order_no, "order_date": str(r.order_date),
            "balance": round(balance, 2), "days": days, "bucket": bucket,
        })
        buckets_summary[bucket] = round(buckets_summary[bucket] + balance, 2)
        total_balance = round(total_balance + balance, 2)

    return {
        "as_of": str(base_date),
        "total_balance": total_balance,
        "buckets": buckets_summary,
        "suppliers": sorted(supplier_map.values(), key=lambda x: -x["total_balance"]),
    }
