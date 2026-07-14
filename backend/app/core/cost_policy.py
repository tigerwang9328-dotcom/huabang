"""Shared business rules for effective sales cost."""

from decimal import Decimal


WENZHOU_XU_SUPPLIER_CODE = "GY1229"
WENZHOU_XU_SENTINEL_COST = Decimal("1")
WENZHOU_XU_SALES_COST_RATE = Decimal("0.60")


def effective_sales_cost(
    supplier_code: str | None,
    unit_cost: Decimal | float | int | None,
    sales_amount: Decimal | float | int,
    sales_qty: Decimal | float | int,
) -> Decimal:
    cost = Decimal(str(unit_cost or 0))
    if supplier_code == WENZHOU_XU_SUPPLIER_CODE and cost == WENZHOU_XU_SENTINEL_COST:
        return Decimal(str(sales_amount)) * WENZHOU_XU_SALES_COST_RATE
    return Decimal(str(sales_qty)) * cost


def effective_sales_cost_sql(
    supplier_expr: str,
    unit_cost_expr: str,
    sales_amount_expr: str,
    sales_qty_expr: str,
) -> str:
    return f"""
        CASE
          WHEN {supplier_expr} = '{WENZHOU_XU_SUPPLIER_CODE}'
           AND COALESCE({unit_cost_expr}, 0) = 1
          THEN COALESCE({sales_amount_expr}, 0) * 0.60
          ELSE COALESCE({sales_qty_expr}, 0) * COALESCE({unit_cost_expr}, 0)
        END
    """
