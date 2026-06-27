"""extend dim.dim_store to standard multi-source schema

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None

_ADD_COLS = [
    ("region_code", sa.String(32)),
    ("region_name", sa.String(64)),
    ("province", sa.String(64)),
    ("county", sa.String(64)),
    ("channel_code", sa.String(32)),
    ("channel_name", sa.String(64)),
    ("business_type", sa.String(32)),
    ("category_code", sa.String(32)),
    ("category_name", sa.String(64)),
    ("source_store_id", sa.String(64)),
    ("source_last_changed", sa.String(32)),
    ("synced_at", sa.DateTime(timezone=True)),
]


def upgrade():
    for name, typ in _ADD_COLS:
        op.add_column("dim_store", sa.Column(name, typ), schema="dim")
    op.add_column("dim_store", sa.Column("source_system", sa.String(32), nullable=False, server_default="manual",
                                         comment="数据来源 baison/kingdee/manual"), schema="dim")
    op.add_column("dim_store", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")), schema="dim")
    # 唯一键: store_code -> (store_code, source_system)
    op.drop_constraint("dim_store_store_code_key", "dim_store", schema="dim", type_="unique")
    op.create_unique_constraint("uq_dim_store_code_source", "dim_store", ["store_code", "source_system"], schema="dim")


def downgrade():
    op.drop_constraint("uq_dim_store_code_source", "dim_store", schema="dim", type_="unique")
    op.create_unique_constraint("dim_store_store_code_key", "dim_store", ["store_code"], schema="dim")
    for name, _ in _ADD_COLS:
        op.drop_column("dim_store", name, schema="dim")
    op.drop_column("dim_store", "source_system", schema="dim")
    op.drop_column("dim_store", "created_at", schema="dim")
