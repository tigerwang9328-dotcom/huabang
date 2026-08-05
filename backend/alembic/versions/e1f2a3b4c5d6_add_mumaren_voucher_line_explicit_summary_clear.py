"""preserve explicitly cleared Mumaren voucher line summaries

Revision ID: e1f2a3b4c5d6
Revises: d6e7f8a9b0c1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "finance_center_mumaren"
TABLE = "finance_center_mumaren_voucher_lines"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("summary_explicitly_cleared", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )
    op.alter_column(TABLE, "summary_explicitly_cleared", server_default=None, schema=SCHEMA)


def downgrade() -> None:
    op.drop_column(TABLE, "summary_explicitly_cleared", schema=SCHEMA)
