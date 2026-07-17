"""Strict API and DeepSeek contracts for investment decisions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


InvestmentAction = Literal[
    "collect_more_data", "stop", "reduce", "maintain", "small_increase", "increase"
]
Confidence = Literal["low", "medium", "high"]


class DeepSeekInvestmentRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: InvestmentAction
    target_type: str = Field(min_length=1, max_length=32)
    target_key: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=256)
    reasoning: str = Field(min_length=1, max_length=2000)
    budget_min_fen: int | None = Field(default=None, ge=0)
    budget_max_fen: int | None = Field(default=None, ge=0)
    review_window_hours: int = Field(ge=1, le=168)
    stop_loss: str = Field(min_length=1, max_length=1000)
    confidence: Confidence
    evidence_refs: list[str] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_budget_range(self):
        if (
            self.budget_min_fen is not None
            and self.budget_max_fen is not None
            and self.budget_min_fen > self.budget_max_fen
        ):
            raise ValueError("budget_min_fen cannot exceed budget_max_fen")
        return self


class DeepSeekInvestmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_summary: str = Field(min_length=1, max_length=2000)
    recommendations: list[DeepSeekInvestmentRecommendation] = Field(min_length=1, max_length=20)
    pattern_observations: list[str] = Field(default_factory=list, max_length=30)
    data_limitations: list[str] = Field(default_factory=list, max_length=30)


class InvestmentDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accepted", "rejected", "partially_accepted", "expired"]
    note: str | None = Field(default=None, max_length=2000)


class InvestmentExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actual_budget_fen: int = Field(gt=0)
    external_campaign_id: str | None = Field(default=None, max_length=128)
    external_plan_id: str | None = Field(default=None, max_length=128)
    external_creative_id: str | None = Field(default=None, max_length=128)
    note: str | None = Field(default=None, max_length=2000)
