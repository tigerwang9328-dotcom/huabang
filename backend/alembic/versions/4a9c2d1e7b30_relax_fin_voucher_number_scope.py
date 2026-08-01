"""relax finance voucher number scope

Revision ID: 4a9c2d1e7b30
Revises: 3e1f6a7b8c97
Create Date: 2026-07-20 16:40:00.000000
"""

from alembic import op


revision = "4a9c2d1e7b30"
down_revision = "3e1f6a7b8c97"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_fin_voucher_book_no", "voucher", schema="fin", type_="unique")
    op.create_unique_constraint(
        "uq_fin_voucher_book_period_group_no",
        "voucher",
        ["book_id", "period_id", "voucher_group", "voucher_no"],
        schema="fin",
    )


def downgrade() -> None:
    op.drop_constraint("uq_fin_voucher_book_period_group_no", "voucher", schema="fin", type_="unique")
    op.create_unique_constraint(
        "uq_fin_voucher_book_no",
        "voucher",
        ["book_id", "voucher_no"],
        schema="fin",
    )
