"""Complete source lineage on Kingdee finance dimensions and marts.

Revision ID: 2d1f6a7b8c96
Revises: 2c1f6a7b8c95
"""

import sqlalchemy as sa
from alembic import op


revision = "2d1f6a7b8c96"
down_revision = "2c1f6a7b8c95"
branch_labels = None
depends_on = None


LINEAGE_COLUMNS = {
    ("dim", "dim_legal_entity"): (
        sa.Column("source_database", sa.String(128), nullable=False, server_default=""),
        sa.Column("source_pk", sa.String(256), nullable=False, server_default=""),
        sa.Column("import_batch_id", sa.String(64), nullable=False, server_default="manual"),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
    ),
    ("dim", "dim_finance_statement_mapping"): (
        sa.Column("source_system", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("source_database", sa.String(128), nullable=False, server_default=""),
        sa.Column("source_pk", sa.String(256), nullable=False, server_default=""),
        sa.Column("import_batch_id", sa.String(64), nullable=False, server_default="manual"),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
    ),
    ("dim", "dim_source_org_mapping"): (
        sa.Column("source_pk", sa.String(256), nullable=False, server_default=""),
        sa.Column("import_batch_id", sa.String(64), nullable=False, server_default="manual"),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
    ),
    ("dm", "dm_finance_statement_monthly"): (
        sa.Column("source_system", sa.String(32), nullable=False, server_default="kingdee"),
        sa.Column("source_database", sa.String(128), nullable=False, server_default=""),
        sa.Column("source_pk", sa.String(256), nullable=False, server_default=""),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
    ),
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for (schema, table), columns in LINEAGE_COLUMNS.items():
        existing = {column["name"] for column in inspector.get_columns(table, schema=schema)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column, schema=schema)
    indexes = {index["name"] for index in inspector.get_indexes("dim_legal_entity", schema="dim")}
    if "ix_dim_legal_entity_import_batch_id" not in indexes:
        op.create_index("ix_dim_legal_entity_import_batch_id", "dim_legal_entity", ["import_batch_id"], schema="dim")


def downgrade() -> None:
    op.drop_index("ix_dim_legal_entity_import_batch_id", table_name="dim_legal_entity", schema="dim")
    for (schema, table), columns in reversed(tuple(LINEAGE_COLUMNS.items())):
        for column in reversed(columns):
            op.drop_column(table, column.name, schema=schema)
