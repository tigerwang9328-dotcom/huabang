"""allow signed ledger balances

Revision ID: 5b8d3f0c9a21
Revises: 4a9c2d1e7b30
Create Date: 2026-07-20 16:45:00.000000
"""

from alembic import op


revision = "5b8d3f0c9a21"
down_revision = "4a9c2d1e7b30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_fin_ledger_nonnegative", "ledger_balance", schema="fin", type_="check")
    op.create_check_constraint(
        "ck_fin_ledger_nonnegative",
        "ledger_balance",
        "period_debit >= 0 AND period_credit >= 0",
        schema="fin",
    )


def downgrade() -> None:
    op.drop_constraint("ck_fin_ledger_nonnegative", "ledger_balance", schema="fin", type_="check")
    op.create_check_constraint(
        "ck_fin_ledger_nonnegative",
        "ledger_balance",
        "opening_amount >= 0 AND period_debit >= 0 AND period_credit >= 0 AND closing_amount >= 0",
        schema="fin",
    )
