from decimal import Decimal

from app.core.cost_policy import effective_sales_cost, effective_sales_cost_sql


def test_wenzhou_xu_one_yuan_cost_uses_sixty_percent_of_sales():
    assert effective_sales_cost("GY1229", 1, 199, 2) == Decimal("119.40")


def test_other_supplier_keeps_quantity_times_unit_cost():
    assert effective_sales_cost("GY1000", 1, 199, 2) == Decimal("2")


def test_wenzhou_xu_non_sentinel_cost_keeps_normal_cost():
    assert effective_sales_cost("GY1229", 80, 199, 2) == Decimal("160")


def test_sql_policy_contains_same_supplier_and_rate():
    sql = effective_sales_cost_sql("p.supplier_code", "p.cost_price", "s.sales_amount", "s.sales_qty")
    assert "GY1229" in sql
    assert "= 1" in sql
    assert "* 0.60" in sql
