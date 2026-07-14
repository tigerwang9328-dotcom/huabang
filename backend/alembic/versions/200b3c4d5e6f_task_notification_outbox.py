"""durable task notification outbox

Revision ID: 200b3c4d5e6f
Revises: 1f0a2b3c4d5e
"""
from alembic import op


revision = "200b3c4d5e6f"
down_revision = "1f0a2b3c4d5e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE app.app_action_task ADD COLUMN IF NOT EXISTS notification_kind varchar(16)")
    op.execute("ALTER TABLE app.app_action_task ADD COLUMN IF NOT EXISTS notification_pending_recipients jsonb")
    op.execute(
        "ALTER TABLE app.app_action_task ADD COLUMN IF NOT EXISTS "
        "notification_attempt_count integer NOT NULL DEFAULT 0"
    )
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_action_task_notification_outbox
        ON app.app_action_task(notification_kind, notification_status, notification_updated_at)
        WHERE is_deleted=false
          AND notification_status IN ('queued','sending','partial','failed')
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS app.idx_action_task_notification_outbox")
    op.execute("ALTER TABLE app.app_action_task DROP COLUMN IF EXISTS notification_attempt_count")
    op.execute("ALTER TABLE app.app_action_task DROP COLUMN IF EXISTS notification_pending_recipients")
    op.execute("ALTER TABLE app.app_action_task DROP COLUMN IF EXISTS notification_kind")
