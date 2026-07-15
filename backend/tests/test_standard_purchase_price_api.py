import inspect

from app.api.v1 import product


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
