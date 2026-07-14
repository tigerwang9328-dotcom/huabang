"""add Baison transfer inbound facts for FIFO inventory age

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
"""

from alembic import op


revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS dwd.dwd_baison_transfer_inbound (
            id bigserial PRIMARY KEY,
            line_key varchar(64) NOT NULL UNIQUE,
            record_code varchar(64) NOT NULL,
            record_date date NOT NULL,
            transfer_type integer NOT NULL,
            source_warehouse_code varchar(32),
            warehouse_code varchar(32) NOT NULL,
            warehouse_name varchar(128),
            product_code varchar(64) NOT NULL,
            product_name varchar(255),
            sku_code varchar(128),
            color_code varchar(64),
            size_code varchar(64),
            barcode varchar(128),
            quantity numeric(16,4) NOT NULL DEFAULT 0,
            cost_unit numeric(14,4),
            cost_amount numeric(16,2),
            raw_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            synced_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_transfer_inbound_age ON dwd.dwd_baison_transfer_inbound(warehouse_code, product_code, record_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_transfer_inbound_record ON dwd.dwd_baison_transfer_inbound(record_code)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS dwd.dwd_baison_transfer_inbound")
