"""Add the complete expense and profit calculation foundation.

Revision ID: 1c9d0e1f2a3b
Revises: 0b8c9d0e1f2a
"""

from alembic import op


revision = "1c9d0e1f2a3b"
down_revision = "0b8c9d0e1f2a"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE dwd.dwd_finance_expense
          ADD COLUMN IF NOT EXISTS allocation_start date,
          ADD COLUMN IF NOT EXISTS allocation_end date
    """)
    op.execute("""
        UPDATE dwd.dwd_finance_expense
        SET allocation_start = COALESCE(allocation_start, expense_date),
            allocation_end = COALESCE(allocation_end, expense_date)
    """)

    op.execute("""
        ALTER TABLE dws.dws_finance_daily
          ADD COLUMN IF NOT EXISTS wages_expense numeric(14,2) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS social_security_expense numeric(14,2) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS platform_fee_expense numeric(14,2) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS marketing_expense numeric(14,2) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS operating_profit numeric(14,2),
          ADD COLUMN IF NOT EXISTS operating_margin numeric(6,4),
          ADD COLUMN IF NOT EXISTS expense_coverage_rate numeric(6,4) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS missing_expense_types jsonb NOT NULL DEFAULT '[]'::jsonb,
          ADD COLUMN IF NOT EXISTS finance_approved boolean NOT NULL DEFAULT false,
          ADD COLUMN IF NOT EXISTS gross_profit_status varchar(16) NOT NULL DEFAULT 'estimated',
          ADD COLUMN IF NOT EXISTS operating_profit_status varchar(16) NOT NULL DEFAULT 'pending_data',
          ADD COLUMN IF NOT EXISTS profit_reasons jsonb NOT NULL DEFAULT '[]'::jsonb
    """)

    op.execute("""
        ALTER TABLE dm.dm_finance_profit_daily
          ADD COLUMN IF NOT EXISTS rent_expense numeric(14,2) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS wages_expense numeric(14,2) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS social_security_expense numeric(14,2) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS platform_fee_expense numeric(14,2) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS utilities_expense numeric(14,2) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS logistics_expense numeric(14,2) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS marketing_expense numeric(14,2) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS other_expense numeric(14,2) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS expense_coverage_rate numeric(6,4) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS missing_expense_types jsonb NOT NULL DEFAULT '[]'::jsonb,
          ADD COLUMN IF NOT EXISTS finance_approved boolean NOT NULL DEFAULT false,
          ADD COLUMN IF NOT EXISTS gross_profit_status varchar(16) NOT NULL DEFAULT 'estimated',
          ADD COLUMN IF NOT EXISTS operating_profit_status varchar(16) NOT NULL DEFAULT 'pending_data',
          ADD COLUMN IF NOT EXISTS profit_reasons jsonb NOT NULL DEFAULT '[]'::jsonb
    """)


def downgrade():
    for column in (
        "profit_reasons", "operating_profit_status", "gross_profit_status",
        "finance_approved", "missing_expense_types", "expense_coverage_rate",
        "other_expense", "marketing_expense", "logistics_expense",
        "utilities_expense", "platform_fee_expense", "social_security_expense",
        "wages_expense", "rent_expense",
    ):
        op.execute(f"ALTER TABLE dm.dm_finance_profit_daily DROP COLUMN IF EXISTS {column}")

    for column in (
        "profit_reasons", "operating_profit_status", "gross_profit_status",
        "finance_approved", "missing_expense_types", "expense_coverage_rate",
        "operating_margin", "operating_profit", "marketing_expense",
        "platform_fee_expense", "social_security_expense", "wages_expense",
    ):
        op.execute(f"ALTER TABLE dws.dws_finance_daily DROP COLUMN IF EXISTS {column}")

    op.execute("ALTER TABLE dwd.dwd_finance_expense DROP COLUMN IF EXISTS allocation_end")
    op.execute("ALTER TABLE dwd.dwd_finance_expense DROP COLUMN IF EXISTS allocation_start")
