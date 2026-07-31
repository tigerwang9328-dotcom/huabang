"""v4.0 outfit-parts: whole-outfit clips and sku-coded single-garment metrics.

Revision ID: f4b5e6c7d901
Revises: 8a3f6b2c1d90
Create Date: 2026-07-31

v4.0 revised semantics: one curve (clip) maps to one whole outfit (>=2 garments).
- video_clips.outfit_parts_json: JSONB array of {position, style_id, sku_code}
  describing the garments of the whole outfit visible in the clip.
- ck_douyin_clip_focus_assignment replaced by ck_douyin_clip_outfit_composition:
  clear_primary requires >=2 outfit parts; multi_focus/unclear require 0 parts.
- video_color_metrics.sku_code: nullable SKU code so single-garment metrics are
  distinguished by SKU instead of color (color no longer participates in
  computation).
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f4b5e6c7d901"
down_revision: Union[str, Sequence[str], None] = "8a3f6b2c1d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_UPGRADE_DDL = r"""
SET ROLE huabang_app_role;

ALTER TABLE douyin.video_clips
    ADD COLUMN IF NOT EXISTS outfit_parts_json JSONB NOT NULL DEFAULT '[]';

ALTER TABLE douyin.video_clips
    DROP CONSTRAINT IF EXISTS ck_douyin_clip_focus_assignment;

ALTER TABLE douyin.video_clips
    ADD CONSTRAINT ck_douyin_clip_outfit_composition
    CHECK ((focus_status = 'clear_primary' AND jsonb_array_length(outfit_parts_json) >= 2) OR (focus_status IN ('multi_focus','unclear') AND jsonb_array_length(outfit_parts_json) = 0));

ALTER TABLE douyin.video_color_metrics
    ADD COLUMN IF NOT EXISTS sku_code VARCHAR(64);
"""

_DOWNGRADE_DDL = r"""
SET ROLE huabang_app_role;

ALTER TABLE douyin.video_color_metrics
    DROP COLUMN IF EXISTS sku_code;

ALTER TABLE douyin.video_clips
    DROP CONSTRAINT IF EXISTS ck_douyin_clip_outfit_composition;

ALTER TABLE douyin.video_clips
    ADD CONSTRAINT ck_douyin_clip_focus_assignment
    CHECK ((focus_status = 'clear_primary' AND style_id IS NOT NULL AND color_id IS NOT NULL) OR (focus_status IN ('multi_focus','unclear') AND style_id IS NULL AND color_id IS NULL));

ALTER TABLE douyin.video_clips
    DROP COLUMN IF EXISTS outfit_parts_json;
"""


def upgrade() -> None:
    try:
        op.execute(_UPGRADE_DDL)
    finally:
        op.execute("RESET ROLE")


def downgrade() -> None:
    try:
        op.execute(_DOWNGRADE_DDL)
    finally:
        op.execute("RESET ROLE")
