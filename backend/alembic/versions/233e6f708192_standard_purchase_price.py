"""add canonical Baison standard purchase price

Revision ID: 233e6f708192
Revises: 222d5e6f7081
"""
from alembic import op


revision = "233e6f708192"
down_revision = "222d5e6f7081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE dim.dim_sku "
        "ADD COLUMN IF NOT EXISTS standard_purchase_price numeric(12, 2)"
    )
    op.execute("""
        UPDATE dim.dim_sku
        SET standard_purchase_price = NULLIF(market_price, 0)
        WHERE source_system = 'baison'
    """)
    op.execute("DROP VIEW IF EXISTS dim.v_baison_sku_standard_purchase_price")
    op.execute("""
        CREATE VIEW dim.v_baison_sku_standard_purchase_price AS
        SELECT
            sku_code,
            product_code,
            COALESCE(BTRIM(color_code::text), '') AS color_code,
            COALESCE(BTRIM(size_code::text), '') AS size_code,
            NULLIF(standard_purchase_price, 0) AS standard_purchase_price,
            'baison_sku.marketPrice'::text AS source_name,
            synced_at
        FROM dim.dim_sku
        WHERE source_system = 'baison'
    """)
    op.execute("""
        INSERT INTO sys.sys_field_permission (
            role_id, module, field_name, can_view, mask_rule
        )
        SELECT
            legacy.role_id,
            'product',
            'product.standard_purchase_price',
            legacy.can_view,
            legacy.mask_rule
        FROM sys.sys_field_permission AS legacy
        WHERE legacy.field_name = 'product.cost_price'
          AND NOT EXISTS (
              SELECT 1
              FROM sys.sys_field_permission AS target
              WHERE target.role_id = legacy.role_id
                AND target.field_name = 'product.standard_purchase_price'
          )
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM sys.sys_field_permission
        WHERE field_name = 'product.standard_purchase_price'
    """)
    op.execute("DROP VIEW IF EXISTS dim.v_baison_sku_standard_purchase_price")
    op.execute(
        "ALTER TABLE dim.dim_sku "
        "DROP COLUMN IF EXISTS standard_purchase_price"
    )
