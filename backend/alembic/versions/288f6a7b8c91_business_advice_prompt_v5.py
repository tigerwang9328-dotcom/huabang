"""update AI business advice prompt default to v5

Revision ID: 288f6a7b8c91
Revises: 277f6a7b8c90
"""
from alembic import op


revision = "288f6a7b8c91"
down_revision = "277f6a7b8c90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "ai_business_advice_snapshot",
        "prompt_version",
        schema="ai",
        server_default="business-advice-v5",
    )


def downgrade() -> None:
    op.alter_column(
        "ai_business_advice_snapshot",
        "prompt_version",
        schema="ai",
        server_default="business-advice-v4",
    )
