"""add store monthly targets

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
"""
from alembic import op
revision="f0a1b2c3d4e5"; down_revision="e9f0a1b2c3d4"; branch_labels=None; depends_on=None
def upgrade():
    op.execute("""CREATE TABLE IF NOT EXISTS dws.dws_store_target_monthly(
      month_date date NOT NULL,store_code varchar(64) NOT NULL,store_name varchar(255),
      target_amount numeric(18,2) NOT NULL DEFAULT 0,actual_amount numeric(18,2) NOT NULL DEFAULT 0,
      achievement_rate numeric(12,6) NOT NULL DEFAULT 0,raw_json jsonb,updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(month_date,store_code))""")
def downgrade(): op.execute("DROP TABLE IF EXISTS dws.dws_store_target_monthly")
