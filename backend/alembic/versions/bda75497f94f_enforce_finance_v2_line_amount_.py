"""enforce finance v2 line amount invariants

Revision ID: bda75497f94f
Revises: a4e7b1c3d6f8
Create Date: 2026-07-29 11:26:14.744850

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "bda75497f94f"
down_revision = "a4e7b1c3d6f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_fin_current_voucher_line_not_both_positive",
        "voucher_line",
        "NOT (debit_amount > 0 AND credit_amount > 0)",
        schema="fin_current",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_fin_current_voucher_line_not_both_positive",
        "voucher_line",
        schema="fin_current",
        type_="check",
    )
