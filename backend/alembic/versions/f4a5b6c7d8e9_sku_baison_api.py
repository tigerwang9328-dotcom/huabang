"""extend dim_sku + create ods.ods_baison_sku_api

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f4a5b6c7d8e9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None

_DIM_ADD = [
    ("product_name", sa.String(256)), ("short_name", sa.String(256)),
    ("gb_barcode", sa.String(64)), ("six_nine_code", sa.String(64)),
    ("color_code", sa.String(32)), ("color_name", sa.String(64)),
    ("size_code", sa.String(32)), ("size_name", sa.String(32)),
    ("brand_code", sa.String(32)), ("brand_name", sa.String(64)),
    ("category_code", sa.String(64)), ("category_name", sa.String(128)),
    ("season_code", sa.String(32)), ("season_name", sa.String(32)),
    ("series_code", sa.String(32)), ("series_name", sa.String(64)),
    ("market_price", sa.Numeric(12, 2)), ("weight", sa.Numeric(12, 4)),
    ("remark", sa.String(256)),
    ("source_created_at", sa.String(32)), ("source_modified_at", sa.String(32)),
    ("source_last_changed", sa.String(64)),
    ("synced_at", sa.DateTime(timezone=True)),
]


def upgrade():
    # dim_sku 扩展（sku_code 扩到 80 容纳带后缀的 SKU）
    op.alter_column("dim_sku", "sku_code", type_=sa.String(80), schema="dim")
    for name, typ in _DIM_ADD:
        op.add_column("dim_sku", sa.Column(name, typ), schema="dim")
    op.add_column("dim_sku", sa.Column("source_system", sa.String(32), nullable=False, server_default="manual"), schema="dim")
    op.add_column("dim_sku", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")), schema="dim")
    op.drop_constraint("dim_sku_sku_code_key", "dim_sku", schema="dim", type_="unique")
    op.create_unique_constraint("uq_dim_sku_code_source", "dim_sku", ["sku_code", "source_system"], schema="dim")

    op.create_table(
        "ods_baison_sku_api",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_no", sa.String(64)),
        sa.Column("source_system", sa.String(32), nullable=False, server_default="baison"),
        sa.Column("api_method", sa.String(64)),
        sa.Column("source_goods_sn", sa.String(80)),
        sa.Column("source_sku", sa.String(120)),
        sa.Column("goods_sn", sa.String(64)),
        sa.Column("sku_code", sa.String(80), nullable=False),
        sa.Column("barcode", sa.String(64)),
        sa.Column("gb_barcode", sa.String(64)),
        sa.Column("six_nine_code", sa.String(64)),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("source_hash", sa.String(64)),
        sa.Column("created_source_at", sa.String(32)),
        sa.Column("modified_source_at", sa.String(32)),
        sa.Column("lastchanged", sa.String(64)),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku_code", "source_system", name="uq_ods_baison_sku_api_sku_source"),
        schema="ods",
    )


def downgrade():
    op.drop_table("ods_baison_sku_api", schema="ods")
    op.drop_constraint("uq_dim_sku_code_source", "dim_sku", schema="dim", type_="unique")
    op.create_unique_constraint("dim_sku_sku_code_key", "dim_sku", ["sku_code"], schema="dim")
    for name, _ in _DIM_ADD:
        op.drop_column("dim_sku", name, schema="dim")
    op.drop_column("dim_sku", "source_system", schema="dim")
    op.drop_column("dim_sku", "created_at", schema="dim")
    op.alter_column("dim_sku", "sku_code", type_=sa.String(64), schema="dim")
