"""task notification retry audit

Revision ID: 211c4d5e6f70
Revises: 200b3c4d5e6f
"""
from alembic import op


revision = "211c4d5e6f70"
down_revision = "200b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE app.app_action_task ADD COLUMN IF NOT EXISTS "
        "notification_manual_retry_count integer NOT NULL DEFAULT 0"
    )
    op.execute("ALTER TABLE app.app_action_task ADD COLUMN IF NOT EXISTS notification_last_retry_by bigint")
    op.execute("ALTER TABLE app.app_action_task ADD COLUMN IF NOT EXISTS notification_last_retry_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE app.app_action_task DROP COLUMN IF EXISTS notification_last_retry_at")
    op.execute("ALTER TABLE app.app_action_task DROP COLUMN IF EXISTS notification_last_retry_by")
    op.execute("ALTER TABLE app.app_action_task DROP COLUMN IF EXISTS notification_manual_retry_count")
