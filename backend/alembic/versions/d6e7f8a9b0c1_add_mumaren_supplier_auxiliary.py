"""add independent finance supplier auxiliary accounting

Revision ID: d6e7f8a9b0c1
Revises: c3d4e5f6a7b9
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "c3d4e5f6a7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "finance_center_mumaren"


def upgrade() -> None:
    op.create_table(
        "finance_center_mumaren_account_auxiliary_dimensions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("book_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("aux_type", sa.String(length=16), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["book_id"], [f"{SCHEMA}.finance_center_mumaren_books.id"]),
        sa.ForeignKeyConstraint(["account_id"], [f"{SCHEMA}.finance_center_mumaren_accounts.id"], ondelete="CASCADE"),
        sa.CheckConstraint("aux_type IN ('customer', 'supplier', 'employee', 'project', 'department')", name="ck_mumaren_account_auxiliary_type"),
        sa.UniqueConstraint("account_id", "aux_type", name="uq_mumaren_account_auxiliary_dimension"),
        schema=SCHEMA,
    )
    op.create_table(
        "finance_center_mumaren_voucher_line_auxiliaries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("book_id", sa.BigInteger(), nullable=False),
        sa.Column("voucher_line_id", sa.BigInteger(), nullable=False),
        sa.Column("aux_type", sa.String(length=16), nullable=False),
        sa.Column("auxiliary_id", sa.BigInteger(), nullable=False),
        sa.Column("auxiliary_code_snapshot", sa.String(length=64), nullable=False),
        sa.Column("auxiliary_name_snapshot", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], [f"{SCHEMA}.finance_center_mumaren_books.id"]),
        sa.ForeignKeyConstraint(["voucher_line_id"], [f"{SCHEMA}.finance_center_mumaren_voucher_lines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["auxiliary_id"], [f"{SCHEMA}.finance_center_mumaren_auxiliary_accountings.id"]),
        sa.CheckConstraint("aux_type IN ('customer', 'supplier', 'employee', 'project', 'department')", name="ck_mumaren_line_auxiliary_type"),
        sa.UniqueConstraint("voucher_line_id", "aux_type", name="uq_mumaren_line_auxiliary_dimension"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_mumaren_line_auxiliary_book_type",
        "finance_center_mumaren_voucher_line_auxiliaries", ["book_id", "aux_type", "auxiliary_id"], schema=SCHEMA,
    )


def downgrade() -> None:
    raise RuntimeError("供应商辅助核算迁移包含审计凭证关联，禁止破坏性降级；请使用前滚修复。")
