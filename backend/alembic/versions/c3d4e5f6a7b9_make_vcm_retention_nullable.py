"""make video_color_metrics retention_snapshot_id nullable

Revision ID: c3d4e5f6a7b9
Revises: c2d3e4f5a6b8

When no retention snapshot exists (insufficient_data), the compute function
returns None. The route handler converted None to 0 via `or 0`, violating
the FK constraint. Making the column nullable allows None directly.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b9"
down_revision: Union[str, None] = "c2d3e4f5a6b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SCHEMA = "douyin"
_TABLE = "video_color_metrics"


def upgrade() -> None:
    op.alter_column(
        _TABLE, "retention_snapshot_id",
        existing_type=sa.BigInteger(),
        nullable=True,
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.alter_column(
        _TABLE, "retention_snapshot_id",
        existing_type=sa.BigInteger(),
        nullable=False,
        schema=_SCHEMA,
    )
