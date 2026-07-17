"""Contract tests for the persistent investment decision loop."""

from app.models.life_data import (
    InvestmentDecisionRun,
    InvestmentEnvironmentSummaryDaily,
    InvestmentExecutionRecord,
    InvestmentMetricSnapshot,
    InvestmentOutcomeSnapshot,
    InvestmentRecommendation,
)


def test_investment_history_models_use_app_schema():
    models = (
        InvestmentMetricSnapshot,
        InvestmentDecisionRun,
        InvestmentRecommendation,
        InvestmentExecutionRecord,
        InvestmentOutcomeSnapshot,
        InvestmentEnvironmentSummaryDaily,
    )

    assert all(model.__table__.schema == "app" for model in models)
    assert [model.__tablename__ for model in models] == [
        "investment_metric_snapshot",
        "investment_decision_run",
        "investment_recommendation",
        "investment_execution_record",
        "investment_outcome_snapshot",
        "investment_environment_summary_daily",
    ]


def test_metric_dimension_types_keep_province_and_city_separate():
    assert "region_province" in InvestmentMetricSnapshot.DIMENSION_TYPES
    assert "region_city" in InvestmentMetricSnapshot.DIMENSION_TYPES
    assert "region" not in InvestmentMetricSnapshot.DIMENSION_TYPES


def test_recommendations_are_human_confirmed_and_unexecuted_by_default():
    assert InvestmentRecommendation.requires_human_confirm.default.arg is True
    assert InvestmentRecommendation.executed.default.arg is False


def test_outcome_window_is_an_integer_and_execution_links_to_recommendation():
    assert InvestmentOutcomeSnapshot.window_hours.type.python_type is int
    assert InvestmentExecutionRecord.recommendation_id.nullable is False


def test_idempotency_constraints_are_named_for_operational_use():
    constraint_names = {
        constraint.name
        for model in (
            InvestmentMetricSnapshot,
            InvestmentDecisionRun,
            InvestmentOutcomeSnapshot,
            InvestmentEnvironmentSummaryDaily,
        )
        for constraint in model.__table__.constraints
        if constraint.name
    }

    assert {
        "uq_investment_metric_snapshot_input",
        "uq_investment_decision_run_input",
        "uq_investment_outcome_window",
        "uq_investment_environment_summary_input",
    }.issubset(constraint_names)


def test_decision_status_constraint_accepts_rate_limited_rule_fallback():
    status_constraint = next(
        constraint
        for constraint in InvestmentDecisionRun.__table__.constraints
        if constraint.name == "ck_investment_decision_status"
    )

    assert "rate_limited" in str(status_constraint.sqltext)
