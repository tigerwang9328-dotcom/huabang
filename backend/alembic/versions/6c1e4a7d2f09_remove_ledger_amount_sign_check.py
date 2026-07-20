"""remove ledger amount sign check

Revision ID: 6c1e4a7d2f09
Revises: 5b8d3f0c9a21
Create Date: 2026-07-20 16:49:00.000000
"""

from alembic import op


revision = "6c1e4a7d2f09"
down_revision = "5b8d3f0c9a21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_fin_ledger_nonnegative", "ledger_balance", schema="fin", type_="check")


def downgrade() -> None:
    op.create_check_constraint(
        "ck_fin_ledger_nonnegative",
        "ledger_balance",
        "period_debit >= 0 AND period_credit >= 0",
        schema="fin",
    )
