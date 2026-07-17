"""Persistence models for data collected from life-data.cn."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class LifeDataCapture(Base):
    __tablename__ = "life_data_capture"
    __table_args__ = (UniqueConstraint("event_id"), {"schema": "app"})

    id = Column(BigInteger, primary_key=True)
    event_id = Column(String(64), nullable=False)
    account_id = Column(String(32), nullable=False, index=True)
    page_path = Column(String(256), nullable=False)
    endpoint = Column(String(256), nullable=False)
    request_payload = Column(JSON, nullable=False)
    response_payload = Column(JSON, nullable=False)
    response_hash = Column(String(64), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )


class LifeDataVideoSnapshot(Base):
    __tablename__ = "life_data_video_snapshot"
    __table_args__ = (
        UniqueConstraint("account_id", "item_id", "metrics_hash"),
        {"schema": "app"},
    )

    id = Column(BigInteger, primary_key=True)
    account_id = Column(String(32), nullable=False, index=True)
    item_id = Column(String(96), nullable=False, index=True)
    title = Column(Text, nullable=False)
    author_id = Column(String(64))
    author_name = Column(String(128))
    published_at = Column(DateTime(timezone=True))
    stat_start = Column(Date, nullable=False)
    stat_end = Column(Date, nullable=False)
    play_count = Column(BigInteger, nullable=False, default=0)
    pay_gmv_fen = Column(BigInteger, nullable=False, default=0)
    verify_gmv_fen = Column(BigInteger, nullable=False, default=0)
    refund_gmv_fen = Column(BigInteger, nullable=False, default=0)
    metrics_hash = Column(String(64), nullable=False)
    metrics = Column(JSON, nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)


class LifeDataAlertEvent(Base):
    __tablename__ = "life_data_alert_event"
    __table_args__ = (
        UniqueConstraint("account_id", "item_id", "rule_code"),
        {"schema": "app"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(String(32), nullable=False)
    item_id = Column(String(96), nullable=False)
    rule_code = Column(String(64), nullable=False)
    snapshot_id = Column(BigInteger)
    task_id = Column(BigInteger)
    play_count = Column(BigInteger, nullable=False)
    triggered_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LifeDataCollectorState(Base):
    __tablename__ = "life_data_collector_state"
    __table_args__ = {"schema": "app"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(String(32), nullable=False, unique=True)
    status = Column(String(16), nullable=False, default="offline")
    last_seen_at = Column(DateTime(timezone=True))
    last_success_at = Column(DateTime(timezone=True))
    last_error_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    last_event_id = Column(String(64))
    queue_depth = Column(Integer, nullable=False, default=0)
    template_count = Column(Integer, nullable=False, default=0)
    last_full_success_at = Column(DateTime(timezone=True))
    group_health = Column(JSON, nullable=False, default=dict)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class InvestmentMetricSnapshot(Base):
    """Long-lived normalized fact derived from one or more LifeData captures."""

    __tablename__ = "investment_metric_snapshot"
    DIMENSION_TYPES = (
        "account",
        "material",
        "campaign",
        "plan",
        "audience_age_gender",
        "region_province",
        "region_city",
        "hour",
        "store",
    )
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "stat_start",
            "stat_end",
            "dimension_type",
            "dimension_key",
            "input_hash",
            name="uq_investment_metric_snapshot_input",
        ),
        CheckConstraint(
            "dimension_type IN ('account','material','campaign','plan',"
            "'audience_age_gender','region_province','region_city','hour','store')",
            name="ck_investment_metric_dimension_type",
        ),
        CheckConstraint(
            "attribution_quality IN ('exact','period_estimate','missing')",
            name="ck_investment_metric_attribution_quality",
        ),
        Index(
            "ix_investment_metric_account_period",
            "account_id",
            "stat_end",
            "dimension_type",
        ),
        {"schema": "app"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(String(32), nullable=False)
    stat_start = Column(Date, nullable=False)
    stat_end = Column(Date, nullable=False)
    dimension_type = Column(String(32), nullable=False)
    dimension_key = Column(String(160), nullable=False)
    dimension_label = Column(String(256), nullable=False)
    spend_fen = Column(BigInteger)
    ad_orders = Column(BigInteger)
    ad_pay_gmv_fen = Column(BigInteger)
    pay_gmv_fen = Column(BigInteger)
    verified_gmv_fen = Column(BigInteger)
    verified_count = Column(BigInteger)
    refund_gmv_fen = Column(BigInteger)
    plays = Column(BigInteger)
    interactions = Column(BigInteger)
    completion_rate = Column(Float)
    attribution_quality = Column(String(24), nullable=False, default="missing")
    source_capture_ids = Column(JSONB, nullable=False, default=list)
    metrics_extra = Column(JSONB, nullable=False, default=dict)
    input_hash = Column(String(64), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class InvestmentDecisionRun(Base):
    """Auditable generation attempt for one normalized investment input."""

    __tablename__ = "investment_decision_run"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "trigger_type",
            "input_hash",
            name="uq_investment_decision_run_input",
        ),
        CheckConstraint(
            "trigger_type IN ('period_complete','daily_summary','manual_rebuild')",
            name="ck_investment_decision_trigger_type",
        ),
        CheckConstraint(
            "status IN ('generated','fallback','blocked','failed','rate_limited')",
            name="ck_investment_decision_status",
        ),
        CheckConstraint(
            "attribution_quality IN ('exact','period_estimate','missing')",
            name="ck_investment_decision_attribution_quality",
        ),
        Index("ix_investment_decision_account_period", "account_id", "stat_end"),
        {"schema": "app"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(String(32), nullable=False)
    stat_start = Column(Date, nullable=False)
    stat_end = Column(Date, nullable=False)
    trigger_type = Column(String(24), nullable=False)
    input_hash = Column(String(64), nullable=False)
    attribution_quality = Column(String(24), nullable=False)
    data_completeness = Column(JSONB, nullable=False, default=dict)
    rule_version = Column(String(64), nullable=False)
    prompt_version = Column(String(64), nullable=False)
    provider = Column(String(32), nullable=False)
    model_used = Column(String(128))
    status = Column(String(16), nullable=False)
    fallback_reason = Column(Text)
    latency_ms = Column(Integer)
    token_usage = Column(JSONB, nullable=False, default=dict)
    source_snapshot_ids = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True))


class InvestmentRecommendation(Base):
    """One human-confirmed recommendation produced by a decision run."""

    __tablename__ = "investment_recommendation"
    __table_args__ = (
        CheckConstraint(
            "action IN ('collect_more_data','stop','reduce','maintain','small_increase','increase')",
            name="ck_investment_recommendation_action",
        ),
        CheckConstraint(
            "confidence IN ('low','medium','high')",
            name="ck_investment_recommendation_confidence",
        ),
        Index("ix_investment_recommendation_run", "decision_run_id"),
        {"schema": "app"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    decision_run_id = Column(
        BigInteger,
        ForeignKey("app.investment_decision_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    action = Column(String(24), nullable=False)
    target_type = Column(String(32), nullable=False)
    target_key = Column(String(160), nullable=False)
    target_label = Column(String(256), nullable=False)
    title = Column(String(256), nullable=False)
    reasoning = Column(Text, nullable=False)
    budget_min_fen = Column(BigInteger)
    budget_max_fen = Column(BigInteger)
    review_window_hours = Column(Integer, nullable=False, default=24)
    stop_loss = Column(Text, nullable=False)
    confidence = Column(String(16), nullable=False)
    evidence_refs = Column(JSONB, nullable=False, default=list)
    requires_human_confirm = Column(Boolean, nullable=False, default=True)
    executed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class InvestmentExecutionRecord(Base):
    """Human decision and manually recorded platform execution facts."""

    __tablename__ = "investment_execution_record"
    __table_args__ = (
        UniqueConstraint("recommendation_id", name="uq_investment_execution_recommendation"),
        CheckConstraint(
            "decision IN ('accepted','rejected','partially_accepted','expired')",
            name="ck_investment_execution_decision",
        ),
        {"schema": "app"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    recommendation_id = Column(
        BigInteger,
        ForeignKey("app.investment_recommendation.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision = Column(String(24), nullable=False)
    confirmed_by = Column(BigInteger, nullable=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=False)
    actual_budget_fen = Column(BigInteger)
    external_campaign_id = Column(String(128))
    external_plan_id = Column(String(128))
    external_creative_id = Column(String(128))
    executed_at = Column(DateTime(timezone=True))
    execution_note = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class InvestmentOutcomeSnapshot(Base):
    """Observed 24, 72, or 168 hour result after a recorded execution."""

    __tablename__ = "investment_outcome_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "execution_record_id",
            "window_hours",
            name="uq_investment_outcome_window",
        ),
        CheckConstraint("window_hours IN (24,72,168)", name="ck_investment_outcome_window"),
        CheckConstraint(
            "attribution_quality IN ('exact','period_estimate','missing')",
            name="ck_investment_outcome_attribution_quality",
        ),
        {"schema": "app"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    execution_record_id = Column(
        BigInteger,
        ForeignKey("app.investment_execution_record.id", ondelete="CASCADE"),
        nullable=False,
    )
    window_hours = Column(Integer, nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    incremental_spend_fen = Column(BigInteger)
    incremental_ad_pay_gmv_fen = Column(BigInteger)
    incremental_verified_gmv_fen = Column(BigInteger)
    incremental_verified_count = Column(BigInteger)
    incremental_refund_gmv_fen = Column(BigInteger)
    ad_pay_roi = Column(Float)
    verified_roi = Column(Float)
    refund_adjusted_verified_roi = Column(Float)
    attribution_quality = Column(String(24), nullable=False)
    source_snapshot_ids = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class InvestmentEnvironmentSummaryDaily(Base):
    """Evidence-limited DeepSeek or rule summary for one lookback window."""

    __tablename__ = "investment_environment_summary_daily"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "summary_date",
            "lookback_days",
            "input_hash",
            name="uq_investment_environment_summary_input",
        ),
        CheckConstraint("lookback_days IN (7,30,90)", name="ck_investment_summary_lookback"),
        CheckConstraint(
            "confidence IN ('low','medium','high')",
            name="ck_investment_summary_confidence",
        ),
        Index("ix_investment_summary_account_date", "account_id", "summary_date"),
        {"schema": "app"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(String(32), nullable=False)
    summary_date = Column(Date, nullable=False)
    lookback_days = Column(Integer, nullable=False)
    input_hash = Column(String(64), nullable=False)
    provider = Column(String(32), nullable=False)
    model_used = Column(String(128))
    prompt_version = Column(String(64), nullable=False)
    patterns = Column(JSONB, nullable=False, default=list)
    risks = Column(JSONB, nullable=False, default=list)
    sample_size = Column(Integer, nullable=False, default=0)
    confidence = Column(String(16), nullable=False)
    evidence_refs = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
