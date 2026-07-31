"""牧马人财务中心独立经营核算计算服务。"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


CENT = Decimal("0.01")


def _amount(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def depreciation_for_period(*, original_value: Any, residual_value: Any, useful_life_months: int, already_depreciated: Any) -> Decimal:
    """直线法当期折旧，严格封顶在原值减残值。"""
    original, residual, accumulated = _amount(original_value), _amount(residual_value), _amount(already_depreciated)
    if useful_life_months <= 0 or original < residual or accumulated < 0:
        raise ValueError("固定资产折旧参数无效")
    depreciable = original - residual
    remaining = max(depreciable - accumulated, Decimal("0"))
    periodic = (depreciable / Decimal(useful_life_months)).quantize(CENT, rounding=ROUND_HALF_UP)
    return min(periodic, remaining).quantize(CENT, rounding=ROUND_HALF_UP)


def net_payroll_amount(gross_amount: Any, deduction_amount: Any) -> Decimal:
    gross, deduction = _amount(gross_amount), _amount(deduction_amount)
    if gross < 0 or deduction < 0 or deduction > gross:
        raise ValueError("薪资扣减金额无效")
    return gross - deduction
