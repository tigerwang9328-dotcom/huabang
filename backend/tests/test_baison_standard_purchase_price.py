import inspect
from datetime import datetime, timezone
from decimal import Decimal

from app.api.v1.product import product_quality_summary
from app.integrations.baison.services.sku_service import _Q_KEYS, _dim_row


NOW = datetime(2026, 7, 15, tzinfo=timezone.utc)


def test_market_price_populates_standard_purchase_price():
    row = _dim_row(
        {"sku": "A-00M", "goodsSn": "A", "marketPrice": "80"},
        NOW,
    )

    assert row["standard_purchase_price"] == Decimal("80")


def test_zero_market_price_is_missing_standard_purchase_price():
    row = _dim_row(
        {"sku": "A-00M", "goodsSn": "A", "marketPrice": "0"},
        NOW,
    )

    assert row["standard_purchase_price"] is None


def test_quality_counter_uses_standard_purchase_price_terminology():
    assert "standard_purchase_price_empty" in _Q_KEYS
    assert "cost_empty" not in _Q_KEYS


def test_quality_summary_uses_canonical_standard_purchase_price_view():
    source = inspect.getsource(product_quality_summary)

    assert "v_baison_sku_standard_purchase_price" in source
    assert "sku_missing_standard_purchase_price_count" in source
    assert "sku_standard_purchase_price_ready_count" in source
    assert "sku_missing_cost_count" not in source
