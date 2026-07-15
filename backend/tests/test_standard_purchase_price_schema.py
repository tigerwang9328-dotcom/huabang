from pathlib import Path

from app.models.dim import DimSku


MIGRATION_PATH = Path(
    "alembic/versions/233e6f708192_standard_purchase_price.py"
)


def test_dim_sku_exposes_standard_purchase_price():
    column = DimSku.__table__.columns.get("standard_purchase_price")

    assert column is not None
    assert str(column.type) == "NUMERIC(12, 2)"


def test_migration_backfills_market_price_and_defines_canonical_view():
    text = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "NULLIF(market_price, 0)" in text
    assert "dim.v_baison_sku_standard_purchase_price" in text
    assert "'baison_sku.marketPrice'::text AS source_name" in text
    assert "product.standard_purchase_price" in text


def test_migration_owns_standard_purchase_price_permissions_on_rollback():
    text = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "field_name = 'product.standard_purchase_price'" in text
    assert "DROP VIEW IF EXISTS dim.v_baison_sku_standard_purchase_price" in text
    assert "DROP COLUMN IF EXISTS standard_purchase_price" in text
