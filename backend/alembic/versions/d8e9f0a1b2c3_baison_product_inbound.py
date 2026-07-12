"""add baison product inbound diagnosis tables

Revision ID: d8e9f0a1b2c3
Revises: 9a1b2c3d4e5f
Create Date: 2026-07-12
"""
from alembic import op

revision = "d8e9f0a1b2c3"
down_revision = "9a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE IF NOT EXISTS dwd.dwd_baison_purchase_inbound (
      id bigserial PRIMARY KEY, line_key varchar(64) NOT NULL UNIQUE,
      record_code varchar(128) NOT NULL, record_date date NOT NULL,
      warehouse_code varchar(64) NOT NULL, warehouse_name varchar(255),
      supplier_code varchar(128), supplier_name varchar(255),
      product_code varchar(128) NOT NULL, product_name varchar(255), sku_code varchar(128),
      color_code varchar(128), color_name varchar(128), size_code varchar(128), size_name varchar(128),
      barcode varchar(128), quantity numeric(18,4) NOT NULL DEFAULT 0,
      purchase_price numeric(18,4) NOT NULL DEFAULT 0, purchase_amount numeric(18,2) NOT NULL DEFAULT 0,
      raw_json jsonb, synced_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_baison_inbound_product_date ON dwd.dwd_baison_purchase_inbound(product_code, record_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_baison_inbound_warehouse_date ON dwd.dwd_baison_purchase_inbound(warehouse_code, record_date)")
    op.execute("""CREATE TABLE IF NOT EXISTS dws.dws_product_inbound_summary (
      product_code varchar(128) PRIMARY KEY, first_inbound_date date, last_inbound_date date,
      total_inbound_quantity numeric(18,4) NOT NULL DEFAULT 0,
      total_inbound_amount numeric(18,2) NOT NULL DEFAULT 0,
      last_purchase_price numeric(18,4) NOT NULL DEFAULT 0,
      receipt_count integer NOT NULL DEFAULT 0, history_start_date date NOT NULL,
      updated_at timestamptz NOT NULL DEFAULT now()
    )""")


def downgrade():
    op.execute("DROP TABLE IF EXISTS dws.dws_product_inbound_summary")
    op.execute("DROP TABLE IF EXISTS dwd.dwd_baison_purchase_inbound")
