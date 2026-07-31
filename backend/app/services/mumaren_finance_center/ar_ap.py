"""牧马人财务中心独立应收应付计算服务。"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Iterable, Mapping


ZERO = Decimal("0")
BUCKETS = ("0-30天", "31-60天", "61-90天", "91-120天", "120天以上")


def _amount(value: Any) -> Decimal:
    return Decimal(str(value or 0))


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
