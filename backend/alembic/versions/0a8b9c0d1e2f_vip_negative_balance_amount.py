"""add VIP negative balance amount to boss snapshot

Revision ID: 0a8b9c0d1e2f
Revises: f7a8b9c0d1e2
"""

from alembic import op


revision = "0a8b9c0d1e2f"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE dm.dm_boss_daily_report
        ADD COLUMN IF NOT EXISTS vip_negative_balance_amount numeric(16,2) NOT NULL DEFAULT 0
    """)


def downgrade():
    op.execute("""
        ALTER TABLE dm.dm_boss_daily_report
        DROP COLUMN IF EXISTS vip_negative_balance_amount
    """)
