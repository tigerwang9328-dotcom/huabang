"""update AI business advice prompt default to v3

Revision ID: 266f6a7b8c9f
Revises: 255f6a7b8c9e
"""
from alembic import op


revision = "266f6a7b8c9f"
down_revision = "255f6a7b8c9e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "ai_business_advice_snapshot",
        "prompt_version",
        schema="ai",
        server_default="business-advice-v3",
    )


def downgrade() -> None:
    op.alter_column(
        "ai_business_advice_snapshot",
        "prompt_version",
        schema="ai",
        server_default="business-advice-v2",
    )
