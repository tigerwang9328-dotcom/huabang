"""align sales monthly report contract

Revision ID: b24d0e1f2a3b
Revises: b23c9d0e1f2a
"""
from alembic import op


revision = "b24d0e1f2a3b"
down_revision = "b23c9d0e1f2a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE finance_center_mumaren.finance_center_mumaren_sales_monthly_reports
          ADD COLUMN IF NOT EXISTS return_amount NUMERIC(18, 2) NOT NULL DEFAULT 0;
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_mumaren_finance_sales_monthly_return_amount'
              AND connamespace = 'finance_center_mumaren'::regnamespace
          ) THEN
            ALTER TABLE finance_center_mumaren.finance_center_mumaren_sales_monthly_reports
              ADD CONSTRAINT ck_mumaren_finance_sales_monthly_return_amount CHECK (return_amount >= 0);
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE finance_center_mumaren.finance_center_mumaren_sales_monthly_reports
          DROP CONSTRAINT IF EXISTS ck_mumaren_finance_sales_monthly_return_amount;
        ALTER TABLE finance_center_mumaren.finance_center_mumaren_sales_monthly_reports
          DROP COLUMN IF EXISTS return_amount;
    """)
