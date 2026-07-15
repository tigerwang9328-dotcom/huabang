"""Shared business rules for Baison standard purchase price."""

from decimal import Decimal
from typing import Any


WENZHOU_XU_SUPPLIER_CODE = "GY1229"
WENZHOU_XU_SENTINEL_STANDARD_PRICE = Decimal("1")
WENZHOU_XU_SALES_COST_RATE = Decimal("0.60")

STANDARD_PURCHASE_PRICE_SENSITIVE_FIELDS = frozenset({
    "standard_purchase_price",
    "market_price",
    "inventory_amount",
    "total_inventory_amount",
    "total_cost_amount",
    "current_cost_amount",
    "amount",
    "age_0_30_amount",
    "age_31_60_amount",
    "age_61_90_amount",
    "age_91_180_amount",
    "age_180_plus_amount",
    "age_90_amount",
    "age_180_amount",
})


def mask_standard_purchase_price_fields(data: Any, can_view: bool) -> Any:
    """Mask direct and derived standard-price values while retaining payload shape."""
    if can_view:
        return data
    if isinstance(data, list):
        return [mask_standard_purchase_price_fields(item, False) for item in data]
    if not isinstance(data, dict):
        return data
    masked: dict[str, Any] = {}
    for key, value in data.items():
        if key in STANDARD_PURCHASE_PRICE_SENSITIVE_FIELDS:
            if isinstance(value, dict) and "value" in value:
                masked_value = dict(value)
                masked_value["value"] = None
                masked[key] = masked_value
            else:
                masked[key] = None
        else:
            masked[key] = mask_standard_purchase_price_fields(value, False)
    return masked


def _decimal(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value))


def effective_sales_standard_cost(
    supplier_code: str | None,
    standard_purchase_price: Decimal | float | int | None,
    sales_amount: Decimal | float | int,
    sales_qty: Decimal | float | int,
) -> Decimal | None:
    if standard_purchase_price is None:
        return None
    price = _decimal(standard_purchase_price)
    if price <= 0:
        return None
    if (
        supplier_code == WENZHOU_XU_SUPPLIER_CODE
        and price == WENZHOU_XU_SENTINEL_STANDARD_PRICE
    ):
        return _decimal(sales_amount) * WENZHOU_XU_SALES_COST_RATE
    return _decimal(sales_qty) * price


def effective_sales_standard_cost_sql(
    supplier_expr: str,
    standard_purchase_price_expr: str,
    sales_amount_expr: str,
    sales_qty_expr: str,
) -> str:
    return f"""
        CASE
          WHEN {supplier_expr} = '{WENZHOU_XU_SUPPLIER_CODE}'
           AND {standard_purchase_price_expr} = 1
          THEN {sales_amount_expr} * 0.60
          WHEN {standard_purchase_price_expr} > 0
          THEN {sales_qty_expr} * {standard_purchase_price_expr}
          ELSE NULL
        END
    """
