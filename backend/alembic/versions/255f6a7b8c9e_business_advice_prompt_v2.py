"""update AI business advice prompt default to v2

Revision ID: 255f6a7b8c9e
Revises: 244f6a7b8c9d
"""
from alembic import op


revision = "255f6a7b8c9e"
down_revision = "244f6a7b8c9d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "ai_business_advice_snapshot",
        "prompt_version",
        schema="ai",
        server_default="business-advice-v2",
    )


def downgrade() -> None:
    op.alter_column(
        "ai_business_advice_snapshot",
        "prompt_version",
        schema="ai",
        server_default="business-advice-v1",
    )
