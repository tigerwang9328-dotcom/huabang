import inspect

from app.api.v1 import product
from app.api.v1 import inventory
from app.core import standard_purchase_price as standard_price_policy


def test_sku_api_exposes_authorized_standard_purchase_price_and_filter():
    source = inspect.getsource(product)

    assert "DimSku.standard_purchase_price" in source
    assert "standard_purchase_price_status" in source
    assert "get_user_field_rules" in source
    assert '"can_view_standard_purchase_price"' in source
    assert '"has_standard_purchase_price"' in source


def test_product_and_sku_suggestions_use_standard_purchase_price_language():
    source = inspect.getsource(product)

    assert "补标准进价" in source
    assert "补成本" not in source
    assert "不返回 raw_data / 成本价" not in source


def test_unauthorized_user_cannot_read_raw_or_derived_standard_price_values():
    assert hasattr(standard_price_policy, "mask_standard_purchase_price_fields")
    mask_standard_purchase_price_fields = (
        standard_price_policy.mask_standard_purchase_price_fields
    )
    payload = {
        "standard_purchase_price": 80,
        "market_price": 80,
        "inventory_amount": 800,
        "sales_amount": 1000,
        "nested": {"total_cost_amount": 500, "inventory_qty": 10},
    }

    masked = mask_standard_purchase_price_fields(payload, can_view=False)
    assert masked["standard_purchase_price"] is None
    assert masked["market_price"] is None
    assert masked["inventory_amount"] is None
    assert masked["nested"]["total_cost_amount"] is None
    assert masked["sales_amount"] == 1000
    assert masked["nested"]["inventory_qty"] == 10


def test_authorized_user_keeps_standard_price_values():
    assert hasattr(standard_price_policy, "mask_standard_purchase_price_fields")
    mask_standard_purchase_price_fields = (
        standard_price_policy.mask_standard_purchase_price_fields
    )
    payload = {"standard_purchase_price": 80, "inventory_amount": 800}
    assert mask_standard_purchase_price_fields(payload, can_view=True) == payload


def test_product_and_inventory_endpoints_apply_the_same_field_mask():
    product_source = inspect.getsource(product)
    inventory_source = inspect.getsource(inventory)

    assert "mask_standard_purchase_price_fields" in product_source
    assert "mask_standard_purchase_price_fields" in inventory_source
