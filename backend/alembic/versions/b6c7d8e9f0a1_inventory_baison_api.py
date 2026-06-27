"""create ods.ods_baison_inventory_api + dwd.dwd_inventory_balance

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b6c7d8e9f0a1"
down_revision = "a5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ods_baison_inventory_api",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_no", sa.String(64)),
        sa.Column("source_system", sa.String(32), nullable=False, server_default="baison"),
        sa.Column("api_method", sa.String(64)),
        sa.Column("line_hash", sa.String(32), nullable=False),
        sa.Column("store_code", sa.String(64)),
        sa.Column("goods_code", sa.String(64)),
        sa.Column("sku", sa.String(80)),
        sa.Column("barcode", sa.String(64)),
        sa.Column("color_code", sa.String(32)),
        sa.Column("size_code", sa.String(32)),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("source_hash", sa.String(64)),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("line_hash", "source_system", name="uq_ods_baison_inventory_api_line_source"),
        schema="ods",
    )
    op.create_index("ix_ods_baison_inv_store", "ods_baison_inventory_api", ["store_code"], schema="ods")
    op.create_table(
        "dwd_inventory_balance",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_no", sa.String(64)),
        sa.Column("source_system", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("line_hash", sa.String(32), nullable=False),
        sa.Column("warehouse_code", sa.String(64)),
        sa.Column("warehouse_name", sa.String(128)),
        sa.Column("product_code", sa.String(64)),
        sa.Column("sku_code", sa.String(80)),
        sa.Column("barcode", sa.String(64)),
        sa.Column("goods_name", sa.String(256)),
        sa.Column("color_code", sa.String(32)),
        sa.Column("color_name", sa.String(64)),
        sa.Column("size_code", sa.String(32)),
        sa.Column("size_name", sa.String(32)),
        sa.Column("location_name", sa.String(64)),
        sa.Column("qty", sa.Numeric(16, 4)),
        sa.Column("lock_qty", sa.Numeric(16, 4)),
        sa.Column("road_qty", sa.Numeric(16, 4)),
        sa.Column("available_qty", sa.Numeric(16, 4)),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("line_hash", "source_system", name="uq_dwd_inventory_balance_line_source"),
        schema="dwd",
    )
    op.create_index("ix_dwd_inv_warehouse", "dwd_inventory_balance", ["warehouse_code"], schema="dwd")
    op.create_index("ix_dwd_inv_product", "dwd_inventory_balance", ["product_code"], schema="dwd")


def downgrade():
    op.drop_table("dwd_inventory_balance", schema="dwd")
    op.drop_table("ods_baison_inventory_api", schema="ods")
