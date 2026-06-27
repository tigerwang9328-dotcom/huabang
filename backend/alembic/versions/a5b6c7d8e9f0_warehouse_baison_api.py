"""create dim.dim_warehouse + ods.ods_baison_warehouse_api

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a5b6c7d8e9f0"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dim_warehouse",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("warehouse_code", sa.String(64), nullable=False),
        sa.Column("warehouse_name", sa.String(128)),
        sa.Column("channel_code", sa.String(32)),
        sa.Column("region_name", sa.String(64)),
        sa.Column("warehouse_nature", sa.String(32)),
        sa.Column("warehouse_category_code", sa.String(32)),
        sa.Column("warehouse_category_name", sa.String(64)),
        sa.Column("default_location_code", sa.String(32)),
        sa.Column("default_location_name", sa.String(64)),
        sa.Column("status", sa.String(16), server_default="active"),
        sa.Column("is_enabled", sa.Boolean()),
        sa.Column("source_system", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("warehouse_code", "source_system", name="uq_dim_warehouse_code_source"),
        schema="dim",
    )
    op.create_table(
        "ods_baison_warehouse_api",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_no", sa.String(64)),
        sa.Column("source_system", sa.String(32), nullable=False, server_default="baison"),
        sa.Column("api_method", sa.String(64)),
        sa.Column("source_warehouse_code", sa.String(64)),
        sa.Column("warehouse_code", sa.String(64), nullable=False),
        sa.Column("warehouse_name", sa.String(128)),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("source_hash", sa.String(64)),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("warehouse_code", "source_system", name="uq_ods_baison_warehouse_api_code_source"),
        schema="ods",
    )


def downgrade():
    op.drop_table("ods_baison_warehouse_api", schema="ods")
    op.drop_table("dim_warehouse", schema="dim")
