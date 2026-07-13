"""preserve target snapshots and enforce diagnosis task idempotency

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5
"""
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE dws.dws_store_target_monthly ADD COLUMN IF NOT EXISTS snapshot_date date")
    op.execute("UPDATE dws.dws_store_target_monthly SET snapshot_date=(updated_at AT TIME ZONE 'Asia/Shanghai')::date WHERE snapshot_date IS NULL")
    op.execute("ALTER TABLE dws.dws_store_target_monthly ALTER COLUMN snapshot_date SET NOT NULL")
    op.execute("ALTER TABLE dws.dws_store_target_monthly DROP CONSTRAINT IF EXISTS dws_store_target_monthly_pkey")
    op.execute("ALTER TABLE dws.dws_store_target_monthly ADD PRIMARY KEY(snapshot_date,month_date,store_code)")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_action_task_ai_source
        ON app.app_action_task(source_type,source_id)
        WHERE is_deleted=false AND source_id IS NOT NULL
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS app.uq_action_task_ai_source")
    op.execute("ALTER TABLE dws.dws_store_target_monthly DROP CONSTRAINT IF EXISTS dws_store_target_monthly_pkey")
    op.execute("""
        DELETE FROM dws.dws_store_target_monthly a
        USING dws.dws_store_target_monthly b
        WHERE a.ctid < b.ctid AND a.month_date=b.month_date AND a.store_code=b.store_code
    """)
    op.execute("ALTER TABLE dws.dws_store_target_monthly ADD PRIMARY KEY(month_date,store_code)")
    op.execute("ALTER TABLE dws.dws_store_target_monthly DROP COLUMN IF EXISTS snapshot_date")
