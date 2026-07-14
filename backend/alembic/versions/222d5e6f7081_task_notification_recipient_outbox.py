"""per-recipient task notification outbox

Revision ID: 222d5e6f7081
Revises: 211c4d5e6f70
"""
from alembic import op


revision = "222d5e6f7081"
down_revision = "211c4d5e6f70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE app.app_action_task ADD COLUMN IF NOT EXISTS notification_event_key varchar(128)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS app.app_task_notification_outbox (
            id bigserial PRIMARY KEY,
            task_id bigint NOT NULL REFERENCES app.app_action_task(id) ON DELETE CASCADE,
            event_key varchar(128) NOT NULL,
            notification_kind varchar(16) NOT NULL,
            recipient_user_id varchar(64) NOT NULL,
            status varchar(16) NOT NULL DEFAULT 'queued',
            attempt_count integer NOT NULL DEFAULT 0,
            manual_retry_count integer NOT NULL DEFAULT 0,
            last_error text,
            claimed_at timestamptz,
            claim_generation bigint NOT NULL DEFAULT 0,
            next_attempt_at timestamptz,
            delivered_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_task_notification_event_recipient UNIQUE(event_key, recipient_user_id),
            CONSTRAINT ck_task_notification_outbox_status
                CHECK (status IN ('queued','sending','success','failed','skipped','uncertain'))
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_task_notification_outbox_pending
        ON app.app_task_notification_outbox(status, next_attempt_at, updated_at, id)
        WHERE status IN ('queued','failed')
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_task_notification_outbox_sending_claimed
        ON app.app_task_notification_outbox(claimed_at, id)
        WHERE status='sending'
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_task_notification_outbox_task_event
        ON app.app_task_notification_outbox(task_id, created_at DESC, id DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_dingtalk_bind_user_active
        ON sys.sys_dingtalk_bind(user_id, id DESC)
        WHERE is_active=true AND COALESCE(push_enabled,true)=true
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_dingtalk_bind_user_any
        ON sys.sys_dingtalk_bind(user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_role_role_user
        ON sys.sys_user_role(role_id, user_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS sys.idx_user_role_role_user")
    op.execute("DROP INDEX IF EXISTS sys.idx_dingtalk_bind_user_any")
    op.execute("DROP INDEX IF EXISTS sys.idx_dingtalk_bind_user_active")
    op.execute("DROP INDEX IF EXISTS app.idx_task_notification_outbox_task_event")
    op.execute("DROP INDEX IF EXISTS app.idx_task_notification_outbox_sending_claimed")
    op.execute("DROP INDEX IF EXISTS app.idx_task_notification_outbox_pending")
    op.execute("DROP TABLE IF EXISTS app.app_task_notification_outbox")
    op.execute("ALTER TABLE app.app_action_task DROP COLUMN IF EXISTS notification_event_key")
