"""add baison pos ticket api tables

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-06-29 17:40:00
"""
from alembic import op


revision = "c7d8e9f0a1b2"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ods.ods_baison_pos_ticket_api (
            id BIGSERIAL PRIMARY KEY,
            batch_no VARCHAR(64) NOT NULL,
            source_system VARCHAR(32) DEFAULT 'baison',
            api_method VARCHAR(64) DEFAULT 'pos.qtlsd.list_get',
            ticket_no VARCHAR(80) NOT NULL,
            store_code VARCHAR(64),
            biz_date DATE,
            raw_data JSONB NOT NULL,
            source_hash VARCHAR(64),
            biz_start_time TIMESTAMP,
            biz_end_time TIMESTAMP,
            page_no INTEGER DEFAULT 1,
            synced_at TIMESTAMP DEFAULT now(),
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ods_baison_pos_ticket_api_ticket
        ON ods.ods_baison_pos_ticket_api(ticket_no, source_system)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS dwd.dwd_pos_ticket (
            id BIGSERIAL PRIMARY KEY,
            source_system VARCHAR(32) DEFAULT 'baison',
            biz_date DATE NOT NULL,
            ticket_no VARCHAR(80) NOT NULL,
            store_code VARCHAR(64),
            store_name VARCHAR(256),
            customer_code VARCHAR(80),
            vip_code VARCHAR(80),
            sales_qty NUMERIC(16,4),
            sales_amount NUMERIC(16,2),
            standard_amount NUMERIC(16,2),
            gross_profit_source_amount NUMERIC(16,2),
            discount_rate NUMERIC(10,4),
            detail_count INTEGER,
            is_void BOOLEAN DEFAULT false,
            is_pending BOOLEAN DEFAULT false,
            batch_no VARCHAR(64),
            raw_ref_id BIGINT,
            raw_data JSONB,
            synced_at TIMESTAMP DEFAULT now(),
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_dwd_pos_ticket_ticket
        ON dwd.dwd_pos_ticket(ticket_no, source_system)
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_dwd_pos_ticket_biz_date ON dwd.dwd_pos_ticket(biz_date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_dwd_pos_ticket_store_date ON dwd.dwd_pos_ticket(store_code, biz_date)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS dwd.idx_dwd_pos_ticket_store_date")
    op.execute("DROP INDEX IF EXISTS dwd.idx_dwd_pos_ticket_biz_date")
    op.execute("DROP INDEX IF EXISTS dwd.uq_dwd_pos_ticket_ticket")
    op.execute("DROP TABLE IF EXISTS dwd.dwd_pos_ticket")
    op.execute("DROP INDEX IF EXISTS ods.uq_ods_baison_pos_ticket_api_ticket")
    op.execute("DROP TABLE IF EXISTS ods.ods_baison_pos_ticket_api")
