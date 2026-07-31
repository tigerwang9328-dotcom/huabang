"""release_stage_configurations: per-account A/B/C/D stage switch (Task 14).

Revision ID: b1c2d3e4f5a6
Revises: f4b5e6c7d901
Create Date: 2026-07-31

Creates ``douyin.release_stage_configurations``, the per-account release-stage
switch for the v3.1 staged rollout:

  Stage A -> collectors + base storage
  Stage B -> annotation + metric computation
  Stage C -> reports + ranking
  Stage D -> full release (including ``bounce_report_enabled``)

Two CHECK constraints enforce the contract at the database level:
  * ``ck_release_stage_current``: current_stage IN ('A','B','C','D')
  * ``ck_release_stage_bounce_gating``: bounce_report_enabled = false OR
    bounce_semantics_status IN ('verified_lower_is_better',
    'verified_higher_is_better')

Stage forward-only progression and bounce gating are additionally enforced in
``app.services.douyin_color_release_service`` so that no constraint-violating
config can be produced through the service layer.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "f4b5e6c7d901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_UPGRADE_DDL = r"""
SET ROLE huabang_app_role;

CREATE TABLE IF NOT EXISTS douyin.release_stage_configurations (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL,
    current_stage VARCHAR(1) NOT NULL DEFAULT 'A',
    bounce_report_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    bounce_semantics_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_release_stage_current CHECK (current_stage IN ('A','B','C','D')),
    CONSTRAINT ck_release_stage_bounce_gating CHECK (
        bounce_report_enabled = false
        OR bounce_semantics_status IN ('verified_lower_is_better','verified_higher_is_better')
    )
);

COMMENT ON TABLE douyin.release_stage_configurations IS
    'Per-account A/B/C/D release stage switch for Douyin color analytics v3.1.';
"""

_DOWNGRADE_DDL = r"""
SET ROLE huabang_app_role;

DROP TABLE IF EXISTS douyin.release_stage_configurations;
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
