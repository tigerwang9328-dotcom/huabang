"""add boss command center snapshot and inventory age facts

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
"""

from alembic import op


revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE dim.dim_member ADD COLUMN IF NOT EXISTS current_balance numeric(14,2)")
    op.execute("ALTER TABLE dim.dim_member ADD COLUMN IF NOT EXISTS balance_updated_at timestamptz")
    op.execute("ALTER TABLE ods.ods_baison_member ADD COLUMN IF NOT EXISTS current_balance numeric(14,2)")
    op.execute("""
        UPDATE ods.ods_baison_member
        SET current_balance = CASE
            WHEN NULLIF(BTRIM(raw_json::jsonb ->> 'CZ_DQJE'), '') IS NULL THEN 0
            WHEN BTRIM(raw_json::jsonb ->> 'CZ_DQJE') ~ '^-?[0-9]+(\\.[0-9]+)?$'
                THEN (BTRIM(raw_json::jsonb ->> 'CZ_DQJE'))::numeric
            ELSE 0
        END
        WHERE current_balance IS NULL
    """)
    op.execute("""
        UPDATE dim.dim_member m
        SET current_balance = COALESCE(o.current_balance, 0),
            balance_updated_at = COALESCE(o.imported_at, now())
        FROM (
            SELECT DISTINCT ON (member_no)
                   member_no, current_balance, imported_at
            FROM ods.ods_baison_member
            WHERE member_no IS NOT NULL
            ORDER BY member_no, imported_at DESC NULLS LAST, id DESC
        ) o
        WHERE m.member_no = o.member_no
          AND m.current_balance IS NULL
    """)

    for column_sql in (
        "actual_pay_amount numeric(14,2)",
        "return_amount numeric(14,2)",
        "return_rate numeric(8,4)",
        "inventory_total_qty numeric(16,4)",
        "inventory_age_unknown_qty numeric(16,4)",
        "inventory_age_unknown_amount numeric(16,2)",
        "vip_balance numeric(16,2)",
        "vip_negative_balance_count integer DEFAULT 0",
        "vip_sales_amount numeric(14,2)",
        "vip_sales_ratio numeric(8,4)",
        "major_exception_count integer DEFAULT 0",
        "source_freshness jsonb DEFAULT '{}'::jsonb",
        "metric_status jsonb DEFAULT '{}'::jsonb",
    ):
        op.execute(f"ALTER TABLE dm.dm_boss_daily_report ADD COLUMN IF NOT EXISTS {column_sql}")

    op.execute("""
        CREATE TABLE IF NOT EXISTS dm.dm_inventory_age_daily (
            id bigserial PRIMARY KEY,
            snapshot_date date NOT NULL,
            as_of_at timestamptz,
            warehouse_code varchar(32) NOT NULL,
            product_code varchar(64) NOT NULL,
            current_quantity numeric(16,4) NOT NULL DEFAULT 0,
            cost_unit numeric(14,4),
            qty_0_90 numeric(16,4) NOT NULL DEFAULT 0,
            qty_91_180 numeric(16,4) NOT NULL DEFAULT 0,
            qty_180_plus numeric(16,4) NOT NULL DEFAULT 0,
            qty_unknown numeric(16,4) NOT NULL DEFAULT 0,
            amount_0_90 numeric(16,2),
            amount_91_180 numeric(16,2),
            amount_180_plus numeric(16,2),
            amount_unknown numeric(16,2),
            first_inbound_date date,
            last_inbound_date date,
            data_quality varchar(16) NOT NULL DEFAULT 'ready',
            generated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_inventory_age_daily UNIQUE (snapshot_date, warehouse_code, product_code)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_inventory_age_daily_date ON dm.dm_inventory_age_daily(snapshot_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_inventory_age_daily_product ON dm.dm_inventory_age_daily(product_code)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS app.app_business_rule_config (
            rule_id varchar(16) PRIMARY KEY,
            rule_name varchar(128) NOT NULL,
            enabled boolean NOT NULL DEFAULT true,
            thresholds jsonb NOT NULL DEFAULT '{}'::jsonb,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        INSERT INTO app.app_business_rule_config(rule_id, rule_name, thresholds) VALUES
        ('R001','门店日销售预警',jsonb_build_object('warning',3000,'risk',1000)),
        ('R002','门店毛利率预警',jsonb_build_object('min_margin',0.20)),
        ('R003','全公司日销售骤降',jsonb_build_object('warning_drop',0.30,'risk_drop',0.50)),
        ('R004','退货率异常',jsonb_build_object('max_rate',0.15)),
        ('R005','高折扣预警',jsonb_build_object('max_discount_rate',0.40)),
        ('R006','负库存预警','{}'::jsonb),
        ('R007','90天滞销库存占比',jsonb_build_object('max_ratio',0.30)),
        ('R008','180天以上滞销金额',jsonb_build_object('max_amount',30000)),
        ('R009','SKU断码预警',jsonb_build_object('min_count',10)),
        ('R010','库存周转天数异常',jsonb_build_object('max_days',120)),
        ('R011','现金安全天数预警',jsonb_build_object('warning_days',30,'critical_days',15)),
        ('R012','预估与核准利润差异',jsonb_build_object('max_rate',0.20)),
        ('R013','待处理任务积压',jsonb_build_object('max_count',20)),
        ('R014','任务逾期预警',jsonb_build_object('risk_count',5)),
        ('R015','数据完整性检查','{}'::jsonb)
        ON CONFLICT (rule_id) DO NOTHING
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS app.app_business_rule_config")
    op.execute("DROP TABLE IF EXISTS dm.dm_inventory_age_daily")
    for column in (
        "metric_status", "source_freshness", "major_exception_count",
        "vip_sales_ratio", "vip_sales_amount", "vip_negative_balance_count",
        "vip_balance", "inventory_total_qty", "return_rate", "return_amount",
        "inventory_age_unknown_amount", "inventory_age_unknown_qty",
        "actual_pay_amount",
    ):
        op.execute(f"ALTER TABLE dm.dm_boss_daily_report DROP COLUMN IF EXISTS {column}")
    op.execute("ALTER TABLE ods.ods_baison_member DROP COLUMN IF EXISTS current_balance")
    op.execute("ALTER TABLE dim.dim_member DROP COLUMN IF EXISTS balance_updated_at")
    op.execute("ALTER TABLE dim.dim_member DROP COLUMN IF EXISTS current_balance")
