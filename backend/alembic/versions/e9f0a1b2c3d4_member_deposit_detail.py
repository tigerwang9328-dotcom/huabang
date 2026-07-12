"""add member deposit detail and daily summary

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-07-12
"""
from alembic import op

revision = "e9f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE IF NOT EXISTS dwd.dwd_baison_member_deposit_log (
      id bigserial PRIMARY KEY, line_key varchar(64) NOT NULL UNIQUE,
      source_log_id varchar(128), member_no varchar(128) NOT NULL,
      customer_code varchar(128), customer_phone varchar(64),
      store_code varchar(64) NOT NULL, store_name varchar(255),
      change_type varchar(32) NOT NULL, business_type varchar(32) NOT NULL,
      money_before numeric(18,2) NOT NULL DEFAULT 0,
      money_change numeric(18,2) NOT NULL DEFAULT 0,
      money_after numeric(18,2) NOT NULL DEFAULT 0,
      record_code varchar(128), occurred_at timestamptz NOT NULL, biz_date date NOT NULL,
      remark text, raw_json jsonb, synced_at timestamptz NOT NULL DEFAULT now(),
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_member_deposit_date_store ON dwd.dwd_baison_member_deposit_log(biz_date, store_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_member_deposit_member_date ON dwd.dwd_baison_member_deposit_log(member_no, biz_date)")
    op.execute("""CREATE TABLE IF NOT EXISTS dws.dws_member_deposit_daily (
      biz_date date NOT NULL, store_code varchar(64) NOT NULL,
      recharge_count integer NOT NULL DEFAULT 0, recharge_member_count integer NOT NULL DEFAULT 0,
      recharge_amount numeric(18,2) NOT NULL DEFAULT 0, avg_recharge_amount numeric(18,2) NOT NULL DEFAULT 0,
      consume_count integer NOT NULL DEFAULT 0, consume_member_count integer NOT NULL DEFAULT 0,
      consume_amount numeric(18,2) NOT NULL DEFAULT 0, adjustment_amount numeric(18,2) NOT NULL DEFAULT 0,
      updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (biz_date, store_code)
    )""")


def downgrade():
    op.execute("DROP TABLE IF EXISTS dws.dws_member_deposit_daily")
    op.execute("DROP TABLE IF EXISTS dwd.dwd_baison_member_deposit_log")
