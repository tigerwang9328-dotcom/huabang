"""persist structured AI command conclusion

Revision ID: 344f7a8192a3
Revises: 233e6f708192
"""
from alembic import op


revision = "344f7a8192a3"
down_revision = "233e6f708192"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE dm.dm_boss_daily_report "
        "ADD COLUMN IF NOT EXISTS ai_command_conclusion jsonb"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE dm.dm_boss_daily_report "
        "DROP COLUMN IF EXISTS ai_command_conclusion"
    )
