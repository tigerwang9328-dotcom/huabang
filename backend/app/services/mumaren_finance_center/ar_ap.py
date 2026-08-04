"""牧马人财务中心独立应收应付计算与写入服务。

写入路径只持久化到 ``finance_center_mumaren`` schema 的往来表,绝不创建
凭证或分录,也不调用华邦旧财务服务。固定流程为"草稿 → 财务审核 →
人工结算",且结算前强制校验同一账簿与防超额。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mumaren_finance_center_domains import (
    FinanceCenterMumarenArApSettlement,
    FinanceCenterMumarenCounterparty,
    FinanceCenterMumarenPayableOrder,
    FinanceCenterMumarenPayableOrderLine,
    FinanceCenterMumarenReceivableOrder,
    FinanceCenterMumarenReceivableOrderLine,
)


ZERO = Decimal("0")
BUCKETS = ("0-30天", "31-60天", "61-90天", "91-120天", "120天以上")


class InvalidOrderTransition(ValueError):
    """AR/AP 单据状态转换不符合"草稿 → 审核 → 结算"规则。"""


class CrossBookViolationError(ValueError):
    """关联的 counterparty 属于其他账簿,禁止跨账簿写入。"""


_ORDER_MODELS = {
    "receivable": FinanceCenterMumarenReceivableOrder,
    "payable": FinanceCenterMumarenPayableOrder,
}

_ORDER_LINE_MODELS = {
    "receivable": FinanceCenterMumarenReceivableOrderLine,
    "payable": FinanceCenterMumarenPayableOrderLine,
}


def _amount(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _period_from_date(order_date: date) -> str:
    return f"{order_date.year:04d}-{order_date.month:02d}"


def validate_ar_ap_detail_total(lines: Iterable[Mapping[str, Any]], total_amount: Any) -> list[Mapping[str, Any]]:
    """Materialize editable detail lines and require their amount total to equal the order."""
    line_rows = list(lines)
    if line_rows and sum((_amount(line.get("amount")) for line in line_rows), ZERO) != _amount(total_amount):
        raise ValueError("明细金额合计必须等于单据总金额")
    return line_rows


def aging_bucket(days: int) -> str:
    if days <= 30:
        return BUCKETS[0]
    if days <= 60:
        return BUCKETS[1]
    if days <= 90:
        return BUCKETS[2]
    if days <= 120:
        return BUCKETS[3]
    return BUCKETS[4]


def apply_settlement(total_amount: Any, settled_amount: Any, payment_amount: Any) -> dict:
    total, settled, payment = _amount(total_amount), _amount(settled_amount), _amount(payment_amount)
    if total < ZERO or settled < ZERO or payment <= ZERO:
        raise ValueError("结算金额必须为正且单据金额不能为负")
    if settled > total or payment > total - settled:
        raise ValueError("结算金额超过未结余额")
    new_settled = settled + payment
    return {
        "settled_amount": new_settled,
        "balance": total - new_settled,
        "status": "settled" if new_settled == total else "partial",
    }


def build_aging(documents: Iterable[Mapping[str, Any]], *, as_of: date) -> dict:
    buckets = {name: ZERO for name in BUCKETS}
    by_counterparty: dict[str, dict] = {}
    for document in documents:
        total = _amount(document.get("total_amount"))
        settled = _amount(document.get("settled_amount"))
        balance = total - settled
        if balance <= ZERO:
            continue
        order_date = document.get("order_date")
        if not isinstance(order_date, date):
            raise ValueError("单据日期必须为 date")
        if order_date > as_of:
            continue
        days = max((as_of - order_date).days, 0)
        bucket = aging_bucket(days)
        name = str(document.get("counterparty_name") or "未命名往来单位")
        counterparty = by_counterparty.setdefault(name, {"counterparty_name": name, "total_balance": ZERO, **{key: ZERO for key in BUCKETS}, "orders": []})
        counterparty[bucket] += balance
        counterparty["total_balance"] += balance
        counterparty["orders"].append({"order_no": document.get("order_no"), "order_date": order_date, "days": days, "bucket": bucket, "balance": balance})
        buckets[bucket] += balance
    rows = sorted(by_counterparty.values(), key=lambda item: item["total_balance"], reverse=True)
    return {"as_of": as_of, "total_balance": sum(buckets.values(), ZERO), "buckets": buckets, "counterparties": rows}


async def _load_counterparty(db: AsyncSession, *, counterparty_id: int, book_id: int) -> FinanceCenterMumarenCounterparty:
    """加载 counterparty 并强制校验同一账簿,禁止跨账簿关联。"""
    counterparty = (await db.execute(
        select(FinanceCenterMumarenCounterparty).where(
            FinanceCenterMumarenCounterparty.id == counterparty_id,
        )
    )).scalar_one_or_none()
    if counterparty is None:
        raise CrossBookViolationError(f"往来单位 {counterparty_id} 不存在")
    if counterparty.book_id != book_id:
        raise CrossBookViolationError(
            f"往来单位属于账簿 {counterparty.book_id},与目标账簿 {book_id} 不一致"
        )
    if not counterparty.is_active:
        raise CrossBookViolationError(f"往来单位 {counterparty_id} 已停用")
    return counterparty


async def create_ar_ap_order(
    db: AsyncSession,
    *,
    book_id: int,
    order_type: str,
    order_no: str,
    order_date: date,
    counterparty_name: str,
    total_amount: Any,
    operator_id: int,
    counterparty_id: int | None = None,
    contact: str | None = None,
    remark: str | None = None,
    lines: Iterable[Mapping[str, Any]] | None = None,
) -> FinanceCenterMumarenReceivableOrder | FinanceCenterMumarenPayableOrder:
    """创建 AR/AP 草稿单据;强制同账簿校验,且不产生任何凭证分录。"""
    if order_type not in _ORDER_MODELS:
        raise ValueError(f"未知的往来单据类型: {order_type}")
    amount = _amount(total_amount)
    line_rows = list(lines or ())
    if amount < ZERO:
        raise ValueError("单据金额不能为负数")
    if line_rows:
        validate_ar_ap_detail_total(line_rows, amount)
    if counterparty_id is not None:
        await _load_counterparty(db, counterparty_id=counterparty_id, book_id=book_id)

    model = _ORDER_MODELS[order_type]
    order = model(
        book_id=book_id,
        order_no=order_no,
        order_date=order_date,
        period=_period_from_date(order_date),
        counterparty_id=counterparty_id,
        counterparty_name=counterparty_name,
        contact=contact,
        total_amount=amount,
        settled_amount=ZERO,
        settlement_status="open",
        workflow_status="draft",
        remark=remark,
        created_by=operator_id,
    )
    db.add(order)
    await db.flush()
    line_model = _ORDER_LINE_MODELS[order_type]
    for line_no, line in enumerate(line_rows, start=1):
        db.add(line_model(
            order_id=order.id,
            line_no=line_no,
            item_name=str(line["item_name"]),
            spec=line.get("spec"),
            quantity=_amount(line.get("quantity") or 1),
            unit_price=_amount(line.get("unit_price")),
            amount=_amount(line.get("amount")),
            tax_rate=_amount(line.get("tax_rate")),
            tax_amount=_amount(line.get("tax_amount")),
            remark=line.get("remark"),
        ))
    return order


async def replace_ar_ap_order_lines(
    db: AsyncSession,
    *,
    order_type: str,
    order_id: int,
    total_amount: Any,
    lines: Iterable[Mapping[str, Any]],
) -> None:
    """Replace all draft order lines only after validating the complete new set."""
    if order_type not in _ORDER_LINE_MODELS:
        raise ValueError(f"未知的往来单据类型: {order_type}")
    line_rows = validate_ar_ap_detail_total(lines, total_amount)
    line_model = _ORDER_LINE_MODELS[order_type]
    existing_lines = list((await db.execute(
        select(line_model).where(line_model.order_id == order_id)
    )).scalars())
    for line in existing_lines:
        await db.delete(line)
    for line_no, line in enumerate(line_rows, start=1):
        db.add(line_model(
            order_id=order_id,
            line_no=line_no,
            item_name=str(line["item_name"]),
            spec=line.get("spec"),
            quantity=_amount(line.get("quantity") or 1),
            unit_price=_amount(line.get("unit_price")),
            amount=_amount(line.get("amount")),
            tax_rate=_amount(line.get("tax_rate")),
            tax_amount=_amount(line.get("tax_amount")),
            remark=line.get("remark"),
        ))


async def review_ar_ap_order(
    db: AsyncSession,
    *,
    order_id: int,
    order_type: str,
    operator_id: int,
) -> FinanceCenterMumarenReceivableOrder | FinanceCenterMumarenPayableOrder:
    """财务审核:仅允许 draft 进入 reviewed,不产生凭证分录。"""
    if order_type not in _ORDER_MODELS:
        raise ValueError(f"未知的往来单据类型: {order_type}")
    model = _ORDER_MODELS[order_type]
    order = await db.get(model, order_id)
    if order is None:
        raise LookupError(f"{order_type} 单据 {order_id} 不存在")
    if order.workflow_status != "draft":
        raise InvalidOrderTransition(f"当前状态 {order.workflow_status},无法审核")
    order.workflow_status = "reviewed"
    order.reviewed_by = operator_id
    return order


async def settle_ar_ap_order(
    db: AsyncSession,
    *,
    order_id: int,
    order_type: str,
    settlement_date: date,
    amount: Any,
    operator_id: int,
    remark: str | None = None,
) -> FinanceCenterMumarenReceivableOrder | FinanceCenterMumarenPayableOrder:
    """人工结算:防超额,写入独立结算记录,不产生凭证分录。"""
    if order_type not in _ORDER_MODELS:
        raise ValueError(f"未知的往来单据类型: {order_type}")
    model = _ORDER_MODELS[order_type]
    order = await db.get(model, order_id)
    if order is None:
        raise LookupError(f"{order_type} 单据 {order_id} 不存在")
    if order.workflow_status not in ("reviewed", "posted"):
        raise InvalidOrderTransition(f"当前状态 {order.workflow_status},需先审核再结算")

    payment = _amount(amount)
    if payment <= ZERO:
        raise ValueError("结算金额必须为正数")
    total = _amount(order.total_amount)
    settled = _amount(order.settled_amount)
    if payment > total - settled:
        raise ValueError(f"结算金额超过未结余额: 未结 {total - settled}, 本次 {payment}")

    settlement = FinanceCenterMumarenArApSettlement(
        book_id=order.book_id,
        settlement_type=order_type,
        order_id=order_id,
        settlement_date=settlement_date,
        amount=payment,
        workflow_status="draft",
        voucher_id=None,
        remark=remark,
        created_by=operator_id,
    )
    db.add(settlement)

    new_settled = settled + payment
    order.settled_amount = new_settled
    order.settlement_status = "settled" if new_settled == total else "partial"
    return order
