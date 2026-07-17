"""investment decision history

Revision ID: 2a0f6a7b8c93
Revises: 266f6a7b8c9f
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "2a0f6a7b8c93"
down_revision = "266f6a7b8c9f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investment_metric_snapshot",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.String(32), nullable=False),
        sa.Column("stat_start", sa.Date(), nullable=False),
        sa.Column("stat_end", sa.Date(), nullable=False),
        sa.Column("dimension_type", sa.String(32), nullable=False),
        sa.Column("dimension_key", sa.String(160), nullable=False),
        sa.Column("dimension_label", sa.String(256), nullable=False),
        sa.Column("spend_fen", sa.BigInteger()),
        sa.Column("ad_orders", sa.BigInteger()),
        sa.Column("ad_pay_gmv_fen", sa.BigInteger()),
        sa.Column("pay_gmv_fen", sa.BigInteger()),
        sa.Column("verified_gmv_fen", sa.BigInteger()),
        sa.Column("verified_count", sa.BigInteger()),
        sa.Column("refund_gmv_fen", sa.BigInteger()),
        sa.Column("plays", sa.BigInteger()),
        sa.Column("interactions", sa.BigInteger()),
        sa.Column("completion_rate", sa.Float()),
        sa.Column("attribution_quality", sa.String(24), nullable=False),
        sa.Column("source_capture_ids", postgresql.JSONB(), nullable=False),
        sa.Column("metrics_extra", postgresql.JSONB(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "dimension_type IN ('account','material','campaign','plan','audience_age_gender',"
            "'region_province','region_city','hour','store')",
            name="ck_investment_metric_dimension_type",
        ),
        sa.CheckConstraint(
            "attribution_quality IN ('exact','period_estimate','missing')",
            name="ck_investment_metric_attribution_quality",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id", "stat_start", "stat_end", "dimension_type", "dimension_key",
            "input_hash", name="uq_investment_metric_snapshot_input",
        ),
        schema="app",
    )
    op.create_index(
        "ix_investment_metric_account_period",
        "investment_metric_snapshot",
        ["account_id", "stat_end", "dimension_type"],
        schema="app",
    )

    op.create_table(
        "investment_decision_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.String(32), nullable=False),
        sa.Column("stat_start", sa.Date(), nullable=False),
        sa.Column("stat_end", sa.Date(), nullable=False),
        sa.Column("trigger_type", sa.String(24), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("attribution_quality", sa.String(24), nullable=False),
        sa.Column("data_completeness", postgresql.JSONB(), nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model_used", sa.String(128)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("fallback_reason", sa.Text()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("token_usage", postgresql.JSONB(), nullable=False),
        sa.Column("source_snapshot_ids", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "trigger_type IN ('period_complete','daily_summary','manual_rebuild')",
            name="ck_investment_decision_trigger_type",
        ),
        sa.CheckConstraint(
            "status IN ('generated','fallback','blocked','failed')",
            name="ck_investment_decision_status",
        ),
        sa.CheckConstraint(
            "attribution_quality IN ('exact','period_estimate','missing')",
            name="ck_investment_decision_attribution_quality",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id", "trigger_type", "input_hash",
            name="uq_investment_decision_run_input",
        ),
        schema="app",
    )
    op.create_index(
        "ix_investment_decision_account_period",
        "investment_decision_run",
        ["account_id", "stat_end"],
        schema="app",
    )

    op.create_table(
        "investment_recommendation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("decision_run_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_key", sa.String(160), nullable=False),
        sa.Column("target_label", sa.String(256), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("budget_min_fen", sa.BigInteger()),
        sa.Column("budget_max_fen", sa.BigInteger()),
        sa.Column("review_window_hours", sa.Integer(), nullable=False),
        sa.Column("stop_loss", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False),
        sa.Column("requires_human_confirm", sa.Boolean(), nullable=False),
        sa.Column("executed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "action IN ('collect_more_data','stop','reduce','maintain','small_increase','increase')",
            name="ck_investment_recommendation_action",
        ),
        sa.CheckConstraint("confidence IN ('low','medium','high')", name="ck_investment_recommendation_confidence"),
        sa.ForeignKeyConstraint(
            ["decision_run_id"], ["app.investment_decision_run.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="app",
    )
    op.create_index(
        "ix_investment_recommendation_run",
        "investment_recommendation",
        ["decision_run_id"],
        schema="app",
    )

    op.create_table(
        "investment_execution_record",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("recommendation_id", sa.BigInteger(), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("confirmed_by", sa.BigInteger(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_budget_fen", sa.BigInteger()),
        sa.Column("external_campaign_id", sa.String(128)),
        sa.Column("external_plan_id", sa.String(128)),
        sa.Column("external_creative_id", sa.String(128)),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("execution_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('accepted','rejected','partially_accepted','expired')",
            name="ck_investment_execution_decision",
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"], ["app.investment_recommendation.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recommendation_id", name="uq_investment_execution_recommendation"),
        schema="app",
    )

    op.create_table(
        "investment_outcome_snapshot",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("execution_record_id", sa.BigInteger(), nullable=False),
        sa.Column("window_hours", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("incremental_spend_fen", sa.BigInteger()),
        sa.Column("incremental_ad_pay_gmv_fen", sa.BigInteger()),
        sa.Column("incremental_verified_gmv_fen", sa.BigInteger()),
        sa.Column("incremental_verified_count", sa.BigInteger()),
        sa.Column("incremental_refund_gmv_fen", sa.BigInteger()),
        sa.Column("ad_pay_roi", sa.Float()),
        sa.Column("verified_roi", sa.Float()),
        sa.Column("refund_adjusted_verified_roi", sa.Float()),
        sa.Column("attribution_quality", sa.String(24), nullable=False),
        sa.Column("source_snapshot_ids", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("window_hours IN (24,72,168)", name="ck_investment_outcome_window"),
        sa.CheckConstraint(
            "attribution_quality IN ('exact','period_estimate','missing')",
            name="ck_investment_outcome_attribution_quality",
        ),
        sa.ForeignKeyConstraint(
            ["execution_record_id"], ["app.investment_execution_record.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "execution_record_id", "window_hours", name="uq_investment_outcome_window"
        ),
        schema="app",
    )

    op.create_table(
        "investment_environment_summary_daily",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.String(32), nullable=False),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column("lookback_days", sa.Integer(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model_used", sa.String(128)),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("patterns", postgresql.JSONB(), nullable=False),
        sa.Column("risks", postgresql.JSONB(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("lookback_days IN (7,30,90)", name="ck_investment_summary_lookback"),
        sa.CheckConstraint("confidence IN ('low','medium','high')", name="ck_investment_summary_confidence"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id", "summary_date", "lookback_days", "input_hash",
            name="uq_investment_environment_summary_input",
        ),
        schema="app",
    )
    op.create_index(
        "ix_investment_summary_account_date",
        "investment_environment_summary_daily",
        ["account_id", "summary_date"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_index("ix_investment_summary_account_date", table_name="investment_environment_summary_daily", schema="app")
    op.drop_table("investment_environment_summary_daily", schema="app")
    op.drop_table("investment_outcome_snapshot", schema="app")
    op.drop_table("investment_execution_record", schema="app")
    op.drop_index("ix_investment_recommendation_run", table_name="investment_recommendation", schema="app")
    op.drop_table("investment_recommendation", schema="app")
    op.drop_index("ix_investment_decision_account_period", table_name="investment_decision_run", schema="app")
    op.drop_table("investment_decision_run", schema="app")
    op.drop_index("ix_investment_metric_account_period", table_name="investment_metric_snapshot", schema="app")
    op.drop_table("investment_metric_snapshot", schema="app")
