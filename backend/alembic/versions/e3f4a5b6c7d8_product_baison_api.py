"""extend dim_product + create ods.ods_baison_product_api

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None

_DIM_ADD = [
    ("category_code", sa.String(64)), ("category_name", sa.String(128)),
    ("top_category_code", sa.String(32)), ("top_category_name", sa.String(64)),
    ("series_code", sa.String(32)), ("series_name", sa.String(64)),
    ("brand_code", sa.String(32)), ("brand_name", sa.String(64)),
    ("season_code", sa.String(32)),
    ("supplier_code", sa.String(32)), ("supplier_name", sa.String(128)),
    ("market_price", sa.Numeric(12, 2)), ("weight", sa.Numeric(12, 4)),
    ("launch_date", sa.Date()),
    ("source_product_id", sa.String(64)),
    ("source_last_modified", sa.String(32)), ("source_last_changed", sa.String(32)),
    ("synced_at", sa.DateTime(timezone=True)),
]


def upgrade():
    # dim_product 扩展
    for name, typ in _DIM_ADD:
        op.add_column("dim_product", sa.Column(name, typ), schema="dim")
    op.add_column("dim_product", sa.Column("source_system", sa.String(32), nullable=False, server_default="manual"), schema="dim")
    op.add_column("dim_product", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")), schema="dim")
    op.drop_constraint("dim_product_product_code_key", "dim_product", schema="dim", type_="unique")
    op.create_unique_constraint("uq_dim_product_code_source", "dim_product", ["product_code", "source_system"], schema="dim")

    # ods.ods_baison_product_api 新建
    op.create_table(
        "ods_baison_product_api",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_no", sa.String(64)),
        sa.Column("source_system", sa.String(32), nullable=False, server_default="baison"),
        sa.Column("api_method", sa.String(64)),
        sa.Column("source_goods_sn", sa.String(64)),
        sa.Column("source_goods_id", sa.String(64)),
        sa.Column("goods_sn", sa.String(64), nullable=False),
        sa.Column("goods_name", sa.String(256)),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("source_hash", sa.String(64)),
        sa.Column("created_source_at", sa.String(32)),
        sa.Column("modified_source_at", sa.String(32)),
        sa.Column("lastchanged", sa.String(32)),
        sa.Column("is_delete", sa.Integer()),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("goods_sn", "source_system", name="uq_ods_baison_product_api_sn_source"),
        schema="ods",
    )


def downgrade():
    op.drop_table("ods_baison_product_api", schema="ods")
    op.drop_constraint("uq_dim_product_code_source", "dim_product", schema="dim", type_="unique")
    op.create_unique_constraint("dim_product_product_code_key", "dim_product", ["product_code"], schema="dim")
    for name, _ in _DIM_ADD:
        op.drop_column("dim_product", name, schema="dim")
    op.drop_column("dim_product", "source_system", schema="dim")
    op.drop_column("dim_product", "created_at", schema="dim")
