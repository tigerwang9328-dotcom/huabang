"""Persist LifeData collector API-group health.

Revision ID: a2b3c4d5e6f7
Revises: e5f6a7b8c9d0
"""

from alembic import op
import sqlalchemy as sa


revision = "a2b3c4d5e6f7"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "life_data_collector_state",
        sa.Column("template_count", sa.Integer(), nullable=False, server_default="0"),
        schema="app",
    )
    op.add_column(
        "life_data_collector_state",
        sa.Column("last_full_success_at", sa.DateTime(timezone=True), nullable=True),
        schema="app",
    )
    op.add_column(
        "life_data_collector_state",
        sa.Column("group_health", sa.JSON(), nullable=False, server_default="{}"),
        schema="app",
    )


def downgrade() -> None:
    op.drop_column("life_data_collector_state", "group_health", schema="app")
    op.drop_column("life_data_collector_state", "last_full_success_at", schema="app")
    op.drop_column("life_data_collector_state", "template_count", schema="app")
