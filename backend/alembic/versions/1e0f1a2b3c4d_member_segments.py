"""Add persisted member segments, risks and wake-up candidates.

Revision ID: 1e0f1a2b3c4d
Revises: 1d0e1f2a3b4c
"""

from alembic import op


revision = "1e0f1a2b3c4d"
down_revision = "1d0e1f2a3b4c"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE dm.dm_member_segment_snapshot (
            id BIGSERIAL PRIMARY KEY,
            calc_date DATE NOT NULL,
            member_no VARCHAR(64) NOT NULL REFERENCES dim.dim_member(member_no) ON DELETE CASCADE,
            store_code VARCHAR(32) NOT NULL,
            labels JSONB NOT NULL DEFAULT '[]'::jsonb,
            risks JSONB NOT NULL DEFAULT '[]'::jsonb,
            metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            data_quality JSONB NOT NULL DEFAULT '{}'::jsonb,
            is_wakeup_candidate BOOLEAN NOT NULL DEFAULT false,
            wakeup_priority INTEGER,
            wakeup_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
            preferences JSONB NOT NULL DEFAULT '[]'::jsonb,
            suggested_products JSONB NOT NULL DEFAULT '[]'::jsonb,
            responsibility_status VARCHAR(24) NOT NULL DEFAULT 'unconfirmed',
            responsible_employee_no VARCHAR(64),
            candidate_guide_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            rule_version VARCHAR(32) NOT NULL,
            source_updated_at TIMESTAMPTZ,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_member_segment_snapshot UNIQUE (calc_date, member_no),
            CONSTRAINT ck_member_segment_responsibility CHECK (
                responsibility_status IN ('unconfirmed','confirmed','unassigned')
            )
        )
    """)
    op.execute("CREATE INDEX idx_member_segment_date_store ON dm.dm_member_segment_snapshot(calc_date DESC,store_code)")
    op.execute("CREATE INDEX idx_member_segment_member_date ON dm.dm_member_segment_snapshot(member_no,calc_date DESC)")
    op.execute("CREATE INDEX idx_member_segment_wakeup ON dm.dm_member_segment_snapshot(calc_date DESC,wakeup_priority) WHERE is_wakeup_candidate")
    op.execute("CREATE INDEX idx_member_segment_labels_gin ON dm.dm_member_segment_snapshot USING GIN(labels)")
    op.execute("CREATE INDEX idx_member_segment_risks_gin ON dm.dm_member_segment_snapshot USING GIN(risks)")
    op.execute("""
        INSERT INTO sys.sys_param(param_key,param_value,description,is_system)
        VALUES (
          'member_segment_rules',
          jsonb_build_object(
            'rule_version','2026.07.1','high_value_amount',10000,'high_balance_amount',5000,
            'high_repurchase_count',10,'high_avg_order_value',800,'high_gross_margin',0.65,
            'gross_margin_min_coverage',0.95,'sleeping_days',90,'churn_risk_days',180,
            'frequency_period_days',90,'frequency_decline_ratio',0.5,
            'frequency_baseline_min_orders',3,'excessive_discount_rate',0.6,
            'discount_min_orders',3,'return_rate_threshold',0.2,'return_min_orders',2,
            'return_sales_min_orders',3,'recharge_no_second_consume_days',30,
            'recharge_risk_lookback_days',180
          )::text,
          'VIP分层、风险和唤醒名单规则', true
        )
    """)
    op.execute("""
        INSERT INTO sys.sys_permission(code,name,module,description) VALUES
          ('member:segment:view','会员分层查看','member','查看会员分层、风险与唤醒名单'),
          ('member:segment:rebuild','会员分层重算','member','重算会员分层、风险与唤醒名单'),
          ('member:sensitive:view','会员敏感数据查看','member','查看会员余额、累计消费、消费日期与规则证据'),
          ('member:sensitive:export','会员敏感数据导出','member','导出完整手机号、余额或消费明细')
    """)
    op.execute("""
        INSERT INTO sys.sys_role_permission(role_id,permission_id)
        SELECT r.id,p.id FROM sys.sys_role r CROSS JOIN sys.sys_permission p
        WHERE (
          p.code IN ('member:segment:view','member:sensitive:view') AND r.code IN ('super_admin','boss','ceo','operation_manager','store_manager')
        ) OR (
          p.code IN ('member:segment:rebuild','member:sensitive:export') AND r.code IN ('super_admin','boss','ceo')
        )
        ON CONFLICT (role_id,permission_id) DO NOTHING
    """)


def downgrade():
    op.execute("""
        DELETE FROM sys.sys_role_permission
        WHERE permission_id IN (
          SELECT id FROM sys.sys_permission
          WHERE code IN ('member:segment:view','member:segment:rebuild','member:sensitive:view','member:sensitive:export')
        )
    """)
    op.execute("DELETE FROM sys.sys_permission WHERE code IN ('member:segment:view','member:segment:rebuild','member:sensitive:view','member:sensitive:export')")
    op.execute("DELETE FROM sys.sys_param WHERE param_key='member_segment_rules'")
    op.execute("DROP TABLE IF EXISTS dm.dm_member_segment_snapshot")
