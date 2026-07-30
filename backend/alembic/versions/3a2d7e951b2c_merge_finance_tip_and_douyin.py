"""merge production finance tip and Douyin analytics head

Revision ID: 3a2d7e951b2c
Revises: e951b2d0a6c4, 2d7c4a9e8b10
Create Date: 2026-07-30

The production database is at the finance branch tip while the v3.1
Douyin migration branches from their shared 1fdf4577d7d8 ancestor.  This
revision is deliberately DDL-free: Alembic applies the Douyin branch to a
production-structure copy, then records the explicit graph merge.
"""

from typing import Sequence, Union


revision: str = "3a2d7e951b2c"
down_revision: Union[str, Sequence[str], None] = ("e951b2d0a6c4", "2d7c4a9e8b10")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass
