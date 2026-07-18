"""update AI business advice prompt default to v4

Revision ID: 277f6a7b8c90
Revises: 266f6a7b8c9f
"""
from alembic import op


revision = "277f6a7b8c90"
down_revision = "266f6a7b8c9f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "ai_business_advice_snapshot",
        "prompt_version",
        schema="ai",
        server_default="business-advice-v4",
    )


def downgrade() -> None:
    op.alter_column(
        "ai_business_advice_snapshot",
        "prompt_version",
        schema="ai",
        server_default="business-advice-v3",
    )
