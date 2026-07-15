"""add AI business advice snapshot cache

Revision ID: 244f6a7b8c9d
Revises: 233e6f708192
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "244f6a7b8c9d"
down_revision = "233e6f708192"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_business_advice_snapshot",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("target_code", sa.String(64), server_default="company", nullable=False),
        sa.Column("safe_context", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("conclusion", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("mode", sa.String(16), server_default="template", nullable=False),
        sa.Column("status", sa.String(16), server_default="success", nullable=False),
        sa.Column("data_status", sa.String(16), server_default="pending_data", nullable=False),
        sa.Column("provider", sa.String(32)),
        sa.Column("model_name", sa.String(128)),
        sa.Column("prompt_version", sa.String(32), server_default="business-advice-v1", nullable=False),
        sa.Column("schema_version", sa.String(32), server_default="business-advice-json-v1", nullable=False),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()),
        sa.Column("total_tokens", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("fallback_reason", sa.Text()),
        sa.Column("last_attempt_status", sa.String(16)),
        sa.Column("last_attempt_error_code", sa.String(64)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("scope_type IN ('company', 'store')", name="ck_ai_business_advice_scope"),
        sa.CheckConstraint("mode IN ('model', 'template')", name="ck_ai_business_advice_mode"),
        sa.CheckConstraint(
            "data_status IN ('ready', 'estimated', 'stale', 'pending_data')",
            name="ck_ai_business_advice_data_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stat_date", "module", "scope_type", "target_code",
            name="uq_ai_business_advice_snapshot_unit",
        ),
        schema="ai",
    )
    op.create_index(
        "ix_ai_business_advice_snapshot_date_status",
        "ai_business_advice_snapshot", ["stat_date", "status", "mode"], schema="ai",
    )
    op.create_index(
        "ix_ai_business_advice_snapshot_input_hash",
        "ai_business_advice_snapshot", ["input_hash"], schema="ai",
    )


def downgrade() -> None:
    op.drop_index("ix_ai_business_advice_snapshot_input_hash", table_name="ai_business_advice_snapshot", schema="ai")
    op.drop_index("ix_ai_business_advice_snapshot_date_status", table_name="ai_business_advice_snapshot", schema="ai")
    op.drop_table("ai_business_advice_snapshot", schema="ai")
