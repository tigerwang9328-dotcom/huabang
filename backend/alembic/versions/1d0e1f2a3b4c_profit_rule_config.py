"""Add configurable operating-profit and VIP-discount rules.

Revision ID: 1d0e1f2a3b4c
Revises: 1c9d0e1f2a3b
"""

from alembic import op


revision = "1d0e1f2a3b4c"
down_revision = "1c9d0e1f2a3b"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS ods.ods_baison_pos_ticket_sync_run (
            id BIGSERIAL PRIMARY KEY,
            batch_no VARCHAR(64) NOT NULL UNIQUE,
            biz_start_time TIMESTAMP NOT NULL,
            biz_end_time TIMESTAMP NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'running',
            expected_pages INTEGER,
            completed_pages INTEGER NOT NULL DEFAULT 0,
            total_result INTEGER,
            error_message TEXT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_baison_pos_ticket_sync_run_coverage
        ON ods.ods_baison_pos_ticket_sync_run(status, biz_start_time, biz_end_time)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_baison_pos_ticket_sync_run_latest
        ON ods.ods_baison_pos_ticket_sync_run(biz_start_time, biz_end_time, started_at DESC)
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_baison_pos_ticket_single_running
        ON ods.ods_baison_pos_ticket_sync_run(status)
        WHERE status='running'
    """)
    op.execute("ALTER TABLE dwd.dwd_finance_expense ADD COLUMN IF NOT EXISTS approved_by BIGINT")
    op.execute("ALTER TABLE dwd.dwd_finance_expense ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ")
    op.execute("""
        INSERT INTO sys.sys_permission(code, name, module, description)
        VALUES ('finance:expense:approve', '核准费用', 'finance', '独立核准经营费用')
        ON CONFLICT (code) DO NOTHING
    """)
    op.execute("""
        INSERT INTO sys.sys_role_permission(role_id, permission_id)
        SELECT r.id, p.id
        FROM sys.sys_role r CROSS JOIN sys.sys_permission p
        WHERE r.code IN ('super_admin','finance_manager')
          AND p.code='finance:expense:approve'
        ON CONFLICT (role_id, permission_id) DO NOTHING
    """)
    op.execute("""
        INSERT INTO app.app_business_rule_config(rule_id, rule_name, thresholds)
        VALUES
          ('R022', '高销售低利润预警',
           jsonb_build_object('min_sales', 5000, 'max_operating_margin', 0.05)),
          ('R023', 'VIP折扣过高预警',
           jsonb_build_object('min_vip_sales', 1000, 'min_discount_rate', 0.4))
        ON CONFLICT (rule_id) DO UPDATE SET
          rule_name=EXCLUDED.rule_name,
          thresholds=EXCLUDED.thresholds,
          updated_at=now()
    """)


def downgrade():
    op.execute("DELETE FROM app.app_business_rule_config WHERE rule_id IN ('R022','R023')")
    op.execute("""
        DELETE FROM sys.sys_role_permission
        WHERE permission_id=(SELECT id FROM sys.sys_permission WHERE code='finance:expense:approve')
    """)
    op.execute("DELETE FROM sys.sys_permission WHERE code='finance:expense:approve'")
    op.execute("ALTER TABLE dwd.dwd_finance_expense DROP COLUMN IF EXISTS approved_at")
    op.execute("ALTER TABLE dwd.dwd_finance_expense DROP COLUMN IF EXISTS approved_by")
    op.execute("DROP TABLE IF EXISTS ods.ods_baison_pos_ticket_sync_run")
