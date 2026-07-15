"""Shared business rules for Baison standard purchase price."""

from decimal import Decimal


WENZHOU_XU_SUPPLIER_CODE = "GY1229"
WENZHOU_XU_SENTINEL_STANDARD_PRICE = Decimal("1")
WENZHOU_XU_SALES_COST_RATE = Decimal("0.60")


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
