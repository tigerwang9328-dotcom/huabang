"""drop video_color_metrics color_id FK and make nullable

Revision ID: c2d3e4f5a6b8
Revises: b28e4f5a6b7c

Revision ID: c2d3e4f5a6b8
Revises: b28e4f5a6b7c
Create Date: 2026-08-04

v4.0 design distinguishes garments by SKU, not color. The video_color_metrics
table still had a NOT NULL color_id with a FK to garment_colors, causing
compute-metrics to fail when outfit_parts have no color (e.g. outer garments).
This migration drops the FK and makes color_id nullable.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2d3e4f5a6b8"
down_revision: Union[str, None] = "b28e4f5a6b7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SCHEMA = "douyin"
_TABLE = "video_color_metrics"


def upgrade() -> None:
    # 1. Drop the FK constraint
    op.drop_constraint("fk_douyin_metric_account_style_color", _TABLE, schema=_SCHEMA, type_="foreignkey")

    # 2. Drop the old unique constraint (includes color_id)
    op.drop_constraint("uq_douyin_video_color_metric", _TABLE, schema=_SCHEMA, type_="unique")

    # 3. Make color_id nullable
    op.alter_column(
        _TABLE, "color_id",
        existing_type=sa.BigInteger(),
        nullable=True,
        schema=_SCHEMA,
    )

    # 4. Recreate unique constraint without color_id
    op.create_unique_constraint(
        "uq_douyin_video_color_metric",
        _TABLE,
        ["account_id", "video_id", "style_id", "observation_window", "metric_version", "metric_input_hash"],
        schema=_SCHEMA,
    )


def downgrade() -> None:
    # Revert: make color_id NOT NULL, recreate FK and old unique constraint
    op.drop_constraint("uq_douyin_video_color_metric", _TABLE, schema=_SCHEMA, type_="unique")

    op.alter_column(
        _TABLE, "color_id",
        existing_type=sa.BigInteger(),
        nullable=False,
        schema=_SCHEMA,
    )

    op.create_unique_constraint(
        "uq_douyin_video_color_metric",
        _TABLE,
        ["account_id", "video_id", "style_id", "color_id", "observation_window", "metric_version", "metric_input_hash"],
        schema=_SCHEMA,
    )

    op.create_foreign_key(
        "fk_douyin_metric_account_style_color",
        _TABLE, "garment_colors",
        ["account_id", "style_id", "color_id"],
        ["account_id", "style_id", "id"],
        source_schema=_SCHEMA,
        referent_schema=_SCHEMA,
        ondelete="RESTRICT",
    )
