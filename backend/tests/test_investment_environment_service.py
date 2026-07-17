"""Evidence and causality guardrails for daily environment summaries."""

import pytest

from app.services import investment_environment_service as environment_service
from app.services.investment_environment_service import (
    EnvironmentSummaryRejected,
    deterministic_insufficient_summary,
    validate_environment_payload,
)


def test_insufficient_history_is_explicit_and_low_confidence():
    result = deterministic_insufficient_summary(sample_size=2, lookback_days=30)

    assert result["confidence"] == "low"
    assert "样本不足" in result["risks"][0]
    assert result["patterns"] == []


@pytest.mark.parametrize("claim", ["加投造成核销增长", "该素材导致成交提升"])
def test_unproven_causal_claims_are_rejected(claim):
    with pytest.raises(EnvironmentSummaryRejected, match="causal"):
        validate_environment_payload(
            {
                "patterns": [claim],
                "risks": [],
                "confidence": "medium",
                "evidence_refs": ["snapshot:1"],
            },
            allowed_evidence={"snapshot:1"},
        )


def test_unknown_evidence_is_rejected():
    with pytest.raises(EnvironmentSummaryRejected, match="evidence"):
        validate_environment_payload(
            {
                "patterns": ["同期观察到周末消耗上升"],
                "risks": [],
                "confidence": "low",
                "evidence_refs": ["snapshot:999"],
            },
            allowed_evidence={"snapshot:1"},
        )


def test_environment_prompt_has_a_bounded_snapshot_input():
    rows = list(range(501))

    assert environment_service.bounded_snapshot_rows(rows, limit=500) == rows[:500]
