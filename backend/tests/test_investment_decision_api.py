"""API contract tests for human-confirmed investment decisions."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.v1 import investment_decision
from app.schemas.investment_decision import (
    InvestmentDecisionRequest,
    InvestmentExecutionRequest,
)


@pytest.mark.asyncio
async def test_overview_reads_persisted_data_without_generating(monkeypatch):
    class FakeService:
        def __init__(self, db):
            self.db = db

        async def overview(self, account_id):
            return {
                "recommendation_source": "deepseek",
                "latest_recommendation": {"executed": False},
            }

    monkeypatch.setattr(investment_decision, "InvestmentDecisionService", FakeService)

    response = await investment_decision.overview(
        _current_user=SimpleNamespace(id=7), db=object()
    )

    assert response.data["recommendation_source"] == "deepseek"
    assert response.data["latest_recommendation"]["executed"] is False


@pytest.mark.asyncio
async def test_human_acceptance_does_not_mark_recommendation_executed(monkeypatch):
    class FakeService:
        def __init__(self, db):
            pass

        async def record_decision(self, recommendation_id, user_id, request):
            assert recommendation_id == 12
            assert user_id == 7
            assert request.decision == "accepted"
            return {"recommendation_id": 12, "decision": "accepted", "executed": False}

    monkeypatch.setattr(investment_decision, "InvestmentDecisionService", FakeService)

    response = await investment_decision.record_decision(
        12,
        InvestmentDecisionRequest(decision="accepted"),
        current_user=SimpleNamespace(id=7),
        db=object(),
    )

    assert response.data["executed"] is False


def test_execution_requires_positive_actual_budget():
    with pytest.raises(ValidationError):
        InvestmentExecutionRequest(actual_budget_fen=0)


@pytest.mark.asyncio
async def test_execution_registration_marks_executed_after_service_commit(monkeypatch):
    class FakeService:
        def __init__(self, db):
            pass

        async def record_execution(self, recommendation_id, user_id, request):
            assert request.actual_budget_fen == 8000
            return {"recommendation_id": recommendation_id, "executed": True}

    monkeypatch.setattr(investment_decision, "InvestmentDecisionService", FakeService)

    response = await investment_decision.record_execution(
        12,
        InvestmentExecutionRequest(actual_budget_fen=8000),
        current_user=SimpleNamespace(id=7),
        db=object(),
    )

    assert response.data["executed"] is True


@pytest.mark.asyncio
async def test_daily_patterns_are_read_only(monkeypatch):
    class FakeService:
        def __init__(self, db):
            pass

        async def daily_patterns(self, account_id, limit):
            assert limit == 9
            return [{"lookback_days": 30, "confidence": "medium"}]

    monkeypatch.setattr(investment_decision, "InvestmentDecisionService", FakeService)

    response = await investment_decision.daily_patterns(
        limit=9,
        _current_user=SimpleNamespace(id=7),
        db=object(),
    )

    assert response.data[0]["lookback_days"] == 30
