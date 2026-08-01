"""complete Mumaren AR/AP order contact snapshots

Revision ID: b28e4f5a6b7c
Revises: b27d3e4f5a6b
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b28e4f5a6b7c"
down_revision: Union[str, None] = "b27d3e4f5a6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SCHEMA = "finance_center_mumaren"


def upgrade() -> None:
    for table_name in (
        "finance_center_mumaren_receivable_orders",
        "finance_center_mumaren_payable_orders",
    ):
        op.add_column(table_name, sa.Column("contact", sa.String(length=128), nullable=True), schema=_SCHEMA)


def downgrade() -> None:
    for table_name in (
        "finance_center_mumaren_payable_orders",
        "finance_center_mumaren_receivable_orders",
    ):
        op.drop_column(table_name, "contact", schema=_SCHEMA)
