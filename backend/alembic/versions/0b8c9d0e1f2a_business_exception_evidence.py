"""Add versioned evidence to business exceptions.

Revision ID: 0b8c9d0e1f2a
Revises: 0a9b0c1d2e3f
"""

from alembic import op


revision = "0b8c9d0e1f2a"
down_revision = "0a9b0c1d2e3f"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS dm.dm_exception_audit (
            id bigserial PRIMARY KEY,
            audit_date date NOT NULL,
            exception_type varchar(32) NOT NULL,
            severity varchar(16),
            store_code varchar(32),
            product_code varchar(64),
            sku_code varchar(64),
            order_no varchar(64),
            description text,
            data_snapshot jsonb,
            is_reviewed boolean NOT NULL DEFAULT false,
            reviewed_by bigint,
            reviewed_at timestamptz,
            review_note text,
            is_converted_to_task boolean NOT NULL DEFAULT false,
            task_id bigint,
            generated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        ALTER TABLE dm.dm_exception_audit
          ADD COLUMN IF NOT EXISTS unique_key varchar(64),
          ADD COLUMN IF NOT EXISTS rule_code varchar(32),
          ADD COLUMN IF NOT EXISTS rule_version varchar(32),
          ADD COLUMN IF NOT EXISTS subject_type varchar(32),
          ADD COLUMN IF NOT EXISTS subject_id varchar(160),
          ADD COLUMN IF NOT EXISTS evidence_hash varchar(64),
          ADD COLUMN IF NOT EXISTS metric_status varchar(16) NOT NULL DEFAULT 'ready',
          ADD COLUMN IF NOT EXISTS source_name varchar(128),
          ADD COLUMN IF NOT EXISTS source_updated_at timestamptz,
          ADD COLUMN IF NOT EXISTS thresholds jsonb NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN IF NOT EXISTS drilldown jsonb NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN IF NOT EXISTS responsibility_status varchar(16) NOT NULL DEFAULT 'pending_data'
    """)
    op.execute("""
        UPDATE dm.dm_exception_audit
        SET rule_code=COALESCE(rule_code, UPPER(exception_type)),
            rule_version=COALESCE(rule_version, 'legacy'),
            subject_type=COALESCE(subject_type,
                CASE WHEN sku_code IS NOT NULL THEN 'sku'
                     WHEN product_code IS NOT NULL THEN 'product'
                     WHEN order_no IS NOT NULL THEN 'transaction'
                     WHEN store_code IS NOT NULL THEN 'store' ELSE 'company' END),
            subject_id=COALESCE(subject_id,
                COALESCE(sku_code, product_code, order_no, store_code, 'ALL')),
            evidence_hash=COALESCE(evidence_hash, md5(COALESCE(data_snapshot::text, '{}'))),
            unique_key=COALESCE(unique_key, md5(
                audit_date::text || '|' || exception_type || '|' ||
                COALESCE(sku_code, product_code, order_no, store_code, 'ALL') || '|' ||
                COALESCE(data_snapshot::text, '{}') || '|' || id::text
            ))
        WHERE unique_key IS NULL
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_dm_exception_audit_unique_key ON dm.dm_exception_audit(unique_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dm_exception_audit_rule_date ON dm.dm_exception_audit(rule_code, audit_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dm_exception_audit_subject ON dm.dm_exception_audit(subject_type, subject_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS dm.dm_exception_rule_version (
            id bigserial PRIMARY KEY,
            rule_code varchar(32) NOT NULL,
            version varchar(32) NOT NULL,
            rule_name varchar(128) NOT NULL,
            thresholds jsonb NOT NULL DEFAULT '{}'::jsonb,
            definition_hash varchar(64) NOT NULL,
            source_status varchar(16) NOT NULL DEFAULT 'ready',
            effective_from timestamptz NOT NULL DEFAULT now(),
            retired_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(rule_code, version)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS dm.dm_exception_evidence (
            id bigserial PRIMARY KEY,
            exception_id bigint NOT NULL REFERENCES dm.dm_exception_audit(id) ON DELETE CASCADE,
            source_table varchar(128) NOT NULL,
            record_key varchar(256) NOT NULL,
            source_record_id varchar(160),
            document_no varchar(128),
            before_value jsonb,
            after_value jsonb,
            source_fields jsonb NOT NULL DEFAULT '{}'::jsonb,
            evidence_hash varchar(64) NOT NULL,
            source_updated_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(exception_id, source_table, record_key, evidence_hash)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_dm_exception_evidence_exception ON dm.dm_exception_evidence(exception_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS dm.dm_exception_evidence")
    op.execute("DROP TABLE IF EXISTS dm.dm_exception_rule_version")
    op.execute("DROP INDEX IF EXISTS dm.ix_dm_exception_audit_subject")
    op.execute("DROP INDEX IF EXISTS dm.ix_dm_exception_audit_rule_date")
    op.execute("DROP INDEX IF EXISTS dm.uq_dm_exception_audit_unique_key")
    for column in (
        "responsibility_status", "drilldown", "thresholds", "source_updated_at",
        "source_name", "metric_status", "evidence_hash", "subject_id",
        "subject_type", "rule_version", "rule_code", "unique_key",
    ):
        op.execute(f"ALTER TABLE dm.dm_exception_audit DROP COLUMN IF EXISTS {column}")
