from decimal import Decimal
import inspect

from app.integrations.baison.services.pos_sale_goods_service import PosSaleGoodsService
from app.services.business_overview_service import get_overview
from app.core.standard_purchase_price import (
    effective_sales_standard_cost,
    effective_sales_standard_cost_sql,
)


def test_regular_sale_uses_standard_purchase_price():
    assert effective_sales_standard_cost("G1", 80, 399, 2) == Decimal("160")


def test_missing_standard_purchase_price_stays_missing():
    assert effective_sales_standard_cost("G1", None, 399, 2) is None


def test_wenzhou_one_yuan_rule_uses_sixty_percent_of_sales():
    assert effective_sales_standard_cost("GY1229", 1, 500, 2) == Decimal("300.00")


def test_sql_policy_keeps_missing_price_as_null():
    sql = effective_sales_standard_cost_sql(
        "p.supplier_code",
        "sp.standard_purchase_price",
        "s.sales_amount",
        "s.sales_qty",
    )

    assert "GY1229" in sql
    assert "THEN s.sales_amount * 0.60" in sql
    assert "WHEN sp.standard_purchase_price > 0" in sql
    assert "ELSE NULL" in sql
    assert "COALESCE(sp.standard_purchase_price, 0)" not in sql


def test_sales_rebuild_joins_canonical_standard_purchase_price():
    source = inspect.getsource(PosSaleGoodsService.rebuild_dws_summary)

    assert "v_baison_sku_standard_purchase_price" in source
    assert "split_part(s.sku_code, '|', 2)" in source
    assert "split_part(s.sku_code, '|', 3)" in source
    assert "p.cost_price" not in source


def test_business_overview_uses_canonical_standard_purchase_price():
    source = inspect.getsource(get_overview)

    assert "v_baison_sku_standard_purchase_price" in source
    assert "estimated_cost_price" not in source
    assert "category_cost" not in source
