"""牧马人财务中心独立税务台账计算服务。"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable, Mapping


def _amount(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def tax_record_balance(tax_amount: Any, paid_amount: Any) -> Decimal:
    tax, paid = _amount(tax_amount), _amount(paid_amount)
    if tax < 0 or paid < 0 or paid > tax:
        raise ValueError("税务实缴金额无效")
    return tax - paid


def build_tax_alerts(records: Iterable[Mapping[str, Any]], *, today: date) -> list[dict]:
    alerts = []
    for record in records:
        outstanding = tax_record_balance(record.get("tax_amount"), record.get("paid_amount"))
        due_date = record.get("due_date")
        if outstanding <= 0 or not isinstance(due_date, date):
            continue
        if due_date < today:
            level = "danger"
        elif due_date <= today + timedelta(days=7):
            level = "warning"
        else:
            continue
        alerts.append({"tax_name": record.get("tax_name"), "period": record.get("period"), "outstanding": outstanding, "due_date": due_date, "level": level})
    return sorted(alerts, key=lambda item: item["due_date"])
