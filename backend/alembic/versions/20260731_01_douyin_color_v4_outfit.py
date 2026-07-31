"""v4.0 outfit ranking: add garment_position and outfit tables.

Revision ID: 8a3f6b2c1d90
Revises: 3a2d7e951b2c
Create Date: 2026-07-31

Adds:
- garment_styles.garment_position (outer/top/bottom/none, default none)
- video_color_metrics.garment_position (derived for split-ranking, default none)
- douyin.outfit_combinations table
- douyin.outfit_color_metrics table
"""

from typing import Sequence, Union

from alembic import op


revision: str = "8a3f6b2c1d90"
down_revision: Union[str, Sequence[str], None] = "3a2d7e951b2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_UPGRADE_DDL = r"""
SET ROLE huabang_app_role;

ALTER TABLE douyin.garment_styles
    ADD COLUMN IF NOT EXISTS garment_position VARCHAR(16) NOT NULL DEFAULT 'none';

ALTER TABLE douyin.garment_styles
    ADD CONSTRAINT ck_douyin_style_garment_position
    CHECK (garment_position IN ('outer','top','bottom','none'));

ALTER TABLE douyin.garment_styles
    ADD CONSTRAINT ck_douyin_style_status
    CHECK (status IN ('active','disabled'));

ALTER TABLE douyin.video_color_metrics
    ADD COLUMN IF NOT EXISTS garment_position VARCHAR(16) NOT NULL DEFAULT 'none';

CREATE TABLE IF NOT EXISTS douyin.outfit_combinations (
    id BIGSERIAL NOT NULL,
    account_id BIGINT NOT NULL,
    video_id BIGINT NOT NULL,
    observation_window VARCHAR(16) NOT NULL,
    combination_key VARCHAR(512) NOT NULL,
    participant_count INTEGER NOT NULL,
    annotation_set_hash VARCHAR(64) NOT NULL,
    retention_snapshot_id BIGINT NOT NULL,
    bounce_snapshot_id BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_douyin_outfit_observation_window CHECK (observation_window IN ('t2','t7','t30','ad_hoc')),
    CONSTRAINT ck_douyin_outfit_participant_count CHECK (participant_count >= 2),
    CONSTRAINT uq_douyin_outfit_account_id UNIQUE (account_id, id),
    CONSTRAINT uq_douyin_outfit_combination UNIQUE (account_id, video_id, observation_window, combination_key),
    CONSTRAINT fk_douyin_outfit_account_video FOREIGN KEY (account_id, video_id) REFERENCES douyin.videos (account_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_douyin_outfit_retention_snapshot FOREIGN KEY (account_id, retention_snapshot_id) REFERENCES douyin.video_analysis_snapshots (account_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_douyin_outfit_bounce_snapshot FOREIGN KEY (account_id, bounce_snapshot_id) REFERENCES douyin.video_analysis_snapshots (account_id, id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS douyin.outfit_color_metrics (
    id BIGSERIAL NOT NULL,
    account_id BIGINT NOT NULL,
    combination_key VARCHAR(512) NOT NULL,
    observation_window VARCHAR(16) NOT NULL,
    metric_version VARCHAR(32) NOT NULL,
    metric_input_hash VARCHAR(64) NOT NULL,
    average_retention NUMERIC(12, 8),
    retention_drop NUMERIC(12, 8),
    average_platform_bounce_curve_value NUMERIC(12, 8),
    max_platform_bounce_curve_value NUMERIC(12, 8),
    participant_count INTEGER NOT NULL,
    total_clip_duration_ms BIGINT NOT NULL,
    video_duration_ms BIGINT NOT NULL,
    dominant_position_segment VARCHAR(16),
    retention_calculation_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    bounce_calculation_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    calculated_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT ck_douyin_outfit_metric_observation_window CHECK (observation_window IN ('t2','t7','t30','ad_hoc')),
    CONSTRAINT ck_douyin_outfit_metric_retention_status CHECK (retention_calculation_status IN ('pending','computed','insufficient_data','stale','failed')),
    CONSTRAINT ck_douyin_outfit_metric_bounce_status CHECK (bounce_calculation_status IN ('pending','computed','insufficient_data','stale','failed')),
    CONSTRAINT uq_douyin_outfit_metric_account_id UNIQUE (account_id, id),
    CONSTRAINT uq_douyin_outfit_color_metric UNIQUE (account_id, combination_key, observation_window, metric_version, metric_input_hash),
    CONSTRAINT fk_douyin_outfit_metric_account FOREIGN KEY (account_id) REFERENCES douyin.douyin_creator_accounts (id) ON DELETE CASCADE
);
"""

_DOWNGRADE_DDL = r"""
SET ROLE huabang_app_role;

DROP TABLE IF EXISTS douyin.outfit_color_metrics;
DROP TABLE IF EXISTS douyin.outfit_combinations;

ALTER TABLE douyin.video_color_metrics
    DROP COLUMN IF EXISTS garment_position;

ALTER TABLE douyin.garment_styles
    DROP CONSTRAINT IF EXISTS ck_douyin_style_status;

ALTER TABLE douyin.garment_styles
    DROP CONSTRAINT IF EXISTS ck_douyin_style_garment_position;

ALTER TABLE douyin.garment_styles
    DROP COLUMN IF EXISTS garment_position;
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
