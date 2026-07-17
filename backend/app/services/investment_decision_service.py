"""Persisted, rule-guarded DeepSeek investment recommendations."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.life_data import (
    InvestmentDecisionRun,
    InvestmentEnvironmentSummaryDaily,
    InvestmentExecutionRecord,
    InvestmentMetricSnapshot,
    InvestmentOutcomeSnapshot,
    InvestmentRecommendation,
)
from app.models.log import LogAiCall
from app.schemas.investment_decision import (
    DeepSeekInvestmentPayload,
    InvestmentDecisionRequest,
    InvestmentExecutionRequest,
)
from app.services.ai_engine import AIEngine


RULE_VERSION = "investment-rules-v1"
PROMPT_VERSION = "investment-decision-v1"
SCHEMA_VERSION = "investment-decision-json-v1"

INVESTMENT_SYSTEM_PROMPT = """你是华邦投流决策分析器。只能使用输入中的标准化生意经事实和 evidence_refs。
实际核销是第一结果口径。不得补数、不得升级归因质量、不得声称已执行投放。
严格输出符合约定的 JSON；所有金额使用整数分。"""


class ModelAdviceRejected(ValueError):
    """DeepSeek output violated a deterministic business guardrail."""


@dataclass(frozen=True)
class RuleEnvelope:
    stat_start: date
    stat_end: date
    attribution_quality: str
    verify_roi: float | None
    allowed_actions: frozenset[str]
    max_confidence: str
    evidence_refs: frozenset[str]
    block_model: bool
    block_reason: str | None
    rule_recommendations: tuple[dict[str, Any], ...]
    summary: dict[str, int | float | None]


@dataclass(frozen=True)
class DecisionResult:
    run_id: int
    status: str
    model_used: str
    recommendations: tuple[dict[str, Any], ...]
    cached: bool = False


def _maximum(snapshots: Iterable[Any], field: str) -> int | None:
    values = [getattr(item, field, None) for item in snapshots]
    present = [int(value) for value in values if value is not None]
    return max(present) if present else None


def _rule_recommendation(
    *, action: str, account_id: str, evidence_refs: frozenset[str], reason: str
) -> dict[str, Any]:
    budgets = {
        "collect_more_data": (None, None),
        "stop": (0, 0),
        "reduce": (3000, 8000),
        "maintain": (5000, 15000),
        "small_increase": (10000, 30000),
        "increase": (10000, 30000),
    }
    budget_min, budget_max = budgets[action]
    return {
        "action": action,
        "target_type": "account",
        "target_key": account_id,
        "target_label": "账户整体",
        "title": {
            "collect_more_data": "先补齐消耗与实际核销数据",
            "stop": "停止新增消耗",
            "reduce": "降低无效消耗，只保留小额验证",
            "maintain": "维持预算并观察实际核销滞后",
            "small_increase": "对有效投放小步加投",
            "increase": "在止损约束内增加预算",
        }[action],
        "reasoning": reason,
        "budget_min_fen": budget_min,
        "budget_max_fen": budget_max,
        "review_window_hours": 24,
        "stop_loss": (
            "完整口径形成前不新增预算"
            if action == "collect_more_data"
            else "新增消耗10000分仍无新增实际核销时停止"
        ),
        "confidence": "low" if action == "collect_more_data" else "medium",
        "evidence_refs": sorted(evidence_refs),
    }


def build_rule_envelope(snapshots: Iterable[Any]) -> RuleEnvelope:
    rows = list(snapshots)
    if not rows:
        today = date.today()
        return RuleEnvelope(
            today, today, "missing", None, frozenset({"collect_more_data"}), "low",
            frozenset(), True, "没有标准化投流快照",
            (_rule_recommendation(
                action="collect_more_data", account_id=settings.LIFE_DATA_ACCOUNT_ID,
                evidence_refs=frozenset(), reason="没有标准化投流快照",
            ),), {},
        )

    stat_start = min(item.stat_start for item in rows)
    stat_end = max(item.stat_end for item in rows)
    account_id = str(rows[0].account_id)
    evidence_refs = frozenset(f"snapshot:{int(item.id)}" for item in rows)
    spend = _maximum(rows, "spend_fen")
    verified = _maximum(rows, "verified_gmv_fen")
    summary = {
        "spend_fen": spend,
        "ad_pay_gmv_fen": _maximum(rows, "ad_pay_gmv_fen"),
        "verified_gmv_fen": verified,
        "verified_count": _maximum(rows, "verified_count"),
        "refund_gmv_fen": _maximum(rows, "refund_gmv_fen"),
    }
    if spend is None or verified is None or spend <= 0:
        reason = "缺少同周期投放消耗或实际核销"
        recommendation = _rule_recommendation(
            action="collect_more_data", account_id=account_id,
            evidence_refs=evidence_refs, reason=reason,
        )
        return RuleEnvelope(
            stat_start, stat_end, "missing", None,
            frozenset({"collect_more_data"}), "low", evidence_refs,
            True, reason, (recommendation,), summary,
        )

    quality = (
        "exact"
        if any(item.attribution_quality == "exact" for item in rows)
        else "period_estimate"
    )
    roi = round(verified / spend, 2)
    if roi >= 1.5:
        allowed = frozenset({"maintain", "small_increase", "increase"})
        action = "small_increase"
    elif roi >= 1.0:
        allowed = frozenset({"reduce", "maintain", "small_increase"})
        action = "maintain"
    else:
        allowed = frozenset({"stop", "reduce", "maintain"})
        action = "reduce"
    reason = f"实际核销ROI为{roi:.2f}，归因质量为{quality}"
    return RuleEnvelope(
        stat_start, stat_end, quality, roi, allowed,
        "high" if quality == "exact" else "medium", evidence_refs,
        False, None,
        (_rule_recommendation(
            action=action, account_id=account_id,
            evidence_refs=evidence_refs, reason=reason,
        ),),
        {**summary, "verify_roi": roi},
    )


def investment_input_hash(snapshots: Iterable[Any]) -> str:
    rows = []
    for item in snapshots:
        rows.append({
            "id": int(item.id),
            "account_id": str(item.account_id),
            "stat_start": str(item.stat_start),
            "stat_end": str(item.stat_end),
            "dimension_type": str(item.dimension_type),
            "dimension_key": str(item.dimension_key),
            "input_hash": str(item.input_hash),
        })
    contract = {
        "snapshots": sorted(rows, key=lambda row: row["id"]),
        "provider": "deepseek",
        "model": settings.INVESTMENT_AI_MODEL,
        "rule_version": RULE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
    }
    encoded = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_model_payload(
    payload: DeepSeekInvestmentPayload,
    envelope: RuleEnvelope,
    *,
    max_budget_fen: int,
) -> tuple[dict[str, Any], ...]:
    validated = []
    confidence_rank = {"low": 0, "medium": 1, "high": 2}
    for item in payload.recommendations:
        if item.action not in envelope.allowed_actions:
            raise ModelAdviceRejected("action exceeds rule envelope")
        if confidence_rank[item.confidence] > confidence_rank[envelope.max_confidence]:
            raise ModelAdviceRejected("confidence exceeds attribution quality")
        if item.budget_max_fen is not None and item.budget_max_fen > max_budget_fen:
            raise ModelAdviceRejected("budget exceeds configured maximum")
        if not set(item.evidence_refs).issubset(envelope.evidence_refs):
            raise ModelAdviceRejected("evidence reference does not exist")
        values = item.model_dump()
        values["target_label"] = "账户整体" if item.target_type == "account" else item.target_key
        validated.append(values)
    return tuple(validated)


def _model_context(envelope: RuleEnvelope) -> dict[str, Any]:
    return {
        "summary": envelope.summary,
        "stat_start": envelope.stat_start.isoformat(),
        "stat_end": envelope.stat_end.isoformat(),
        "attribution_quality": envelope.attribution_quality,
        "allowed_actions": sorted(envelope.allowed_actions),
        "max_confidence": envelope.max_confidence,
        "max_budget_fen": settings.INVESTMENT_AI_MAX_BUDGET_FEN,
        "evidence_refs": sorted(envelope.evidence_refs),
        "requires_human_confirm": True,
        "executed": False,
    }


class InvestmentDecisionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _latest_snapshots(self, account_id: str) -> list[InvestmentMetricSnapshot]:
        latest = (
            await self.db.execute(
                select(func.max(InvestmentMetricSnapshot.stat_end)).where(
                    InvestmentMetricSnapshot.account_id == account_id
                )
            )
        ).scalar_one_or_none()
        if latest is None:
            return []
        return list(
            (
                await self.db.execute(
                    select(InvestmentMetricSnapshot).where(
                        InvestmentMetricSnapshot.account_id == account_id,
                        InvestmentMetricSnapshot.stat_end == latest,
                    )
                )
            ).scalars().all()
        )

    async def _cached(self, account_id: str, input_hash: str) -> DecisionResult | None:
        run = (
            await self.db.execute(
                select(InvestmentDecisionRun).where(
                    InvestmentDecisionRun.account_id == account_id,
                    InvestmentDecisionRun.trigger_type == "period_complete",
                    InvestmentDecisionRun.input_hash == input_hash,
                )
            )
        ).scalar_one_or_none()
        if run is None:
            return None
        recommendations = list(
            (
                await self.db.execute(
                    select(InvestmentRecommendation).where(
                        InvestmentRecommendation.decision_run_id == run.id
                    )
                )
            ).scalars().all()
        )
        return DecisionResult(
            int(run.id), run.status, run.model_used or "deterministic_rules",
            tuple(_recommendation_dict(item) for item in recommendations), True,
        )

    async def generate_for_latest_period(self, account_id: str) -> DecisionResult:
        snapshots = await self._latest_snapshots(account_id)
        input_hash = investment_input_hash(snapshots)
        cached = await self._cached(account_id, input_hash)
        if cached:
            return cached

        lock_key = int(hashlib.sha256(f"investment|{account_id}".encode()).hexdigest()[:15], 16)
        await self.db.execute(select(func.pg_advisory_xact_lock(lock_key)))
        cached = await self._cached(account_id, input_hash)
        if cached:
            return cached

        envelope = build_rule_envelope(snapshots)
        started = time.monotonic()
        status = "blocked" if envelope.block_model else "generated"
        model_used = "deterministic_rules"
        fallback_reason = envelope.block_reason
        recommendations = envelope.rule_recommendations
        usage: dict[str, Any] = {}

        if not envelope.block_model and settings.INVESTMENT_AI_ENABLED:
            try:
                model_result = await AIEngine(self.db)._call_business_advice(
                    INVESTMENT_SYSTEM_PROMPT,
                    json.dumps(_model_context(envelope), ensure_ascii=False, sort_keys=True),
                    max_tokens=2500,
                )
                payload = DeepSeekInvestmentPayload.model_validate_json(model_result["content"])
                recommendations = validate_model_payload(
                    payload, envelope,
                    max_budget_fen=settings.INVESTMENT_AI_MAX_BUDGET_FEN,
                )
                model_used = str(model_result.get("model") or settings.INVESTMENT_AI_MODEL)
                usage = {
                    key: model_result.get(key)
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                }
            except Exception as exc:
                status = "fallback"
                fallback_reason = f"{type(exc).__name__}: {str(exc)[:300]}"

        completed_at = datetime.now(timezone.utc)
        latency_ms = round((time.monotonic() - started) * 1000)
        run = InvestmentDecisionRun(
            account_id=account_id,
            stat_start=envelope.stat_start,
            stat_end=envelope.stat_end,
            trigger_type="period_complete",
            input_hash=input_hash,
            attribution_quality=envelope.attribution_quality,
            data_completeness={"blocked": envelope.block_model, "reason": envelope.block_reason},
            rule_version=RULE_VERSION,
            prompt_version=PROMPT_VERSION,
            provider="deepseek",
            model_used=model_used,
            status=status,
            fallback_reason=fallback_reason,
            latency_ms=latency_ms,
            token_usage=usage,
            source_snapshot_ids=[int(item.id) for item in snapshots],
            completed_at=completed_at,
        )
        self.db.add(run)
        await self.db.flush()
        for item in recommendations:
            self.db.add(InvestmentRecommendation(
                decision_run_id=run.id,
                requires_human_confirm=True,
                executed=False,
                **item,
            ))
        self.db.add(LogAiCall(
            user_id=1,
            user_role="system_batch",
            call_type="investment_decision",
            data_scope=f"account:{account_id}:{envelope.stat_end}",
            prompt_version=PROMPT_VERSION,
            model_name=model_used,
            ai_provider="deepseek",
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            response_summary=recommendations[0]["title"][:500],
            data_quality_blocked=envelope.block_model,
            latency_ms=latency_ms,
            status="success" if status == "generated" else status,
            error_message=fallback_reason,
        ))
        await self.db.commit()
        return DecisionResult(int(run.id), status, model_used, tuple(recommendations))

    async def overview(self, account_id: str) -> dict[str, Any]:
        run = (
            await self.db.execute(
                select(InvestmentDecisionRun)
                .where(InvestmentDecisionRun.account_id == account_id)
                .order_by(InvestmentDecisionRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if run is None:
            return {
                "recommendation_source": "rules",
                "latest_run": None,
                "latest_recommendation": None,
                "environment_summary": None,
            }
        recommendation = (
            await self.db.execute(
                select(InvestmentRecommendation)
                .where(InvestmentRecommendation.decision_run_id == run.id)
                .order_by(InvestmentRecommendation.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        environment = (
            await self.db.execute(
                select(InvestmentEnvironmentSummaryDaily)
                .where(InvestmentEnvironmentSummaryDaily.account_id == account_id)
                .order_by(InvestmentEnvironmentSummaryDaily.summary_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return {
            "recommendation_source": (
                "deepseek" if run.status == "generated" and run.model_used != "deterministic_rules" else "rules"
            ),
            "latest_run": _run_dict(run),
            "latest_recommendation": (
                _recommendation_dict(recommendation) if recommendation else None
            ),
            "environment_summary": _environment_dict(environment) if environment else None,
        }

    async def history(self, account_id: str, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        runs = list(
            (
                await self.db.execute(
                    select(InvestmentDecisionRun)
                    .where(InvestmentDecisionRun.account_id == account_id)
                    .order_by(InvestmentDecisionRun.created_at.desc())
                    .offset(offset)
                    .limit(min(limit, 100))
                )
            ).scalars().all()
        )
        result = []
        for run in runs:
            recommendations = list(
                (
                    await self.db.execute(
                        select(InvestmentRecommendation).where(
                            InvestmentRecommendation.decision_run_id == run.id
                        )
                    )
                ).scalars().all()
            )
            result.append({
                **_run_dict(run),
                "recommendations": [_recommendation_dict(item) for item in recommendations],
            })
        return result

    async def detail(self, account_id: str, run_id: int) -> dict[str, Any] | None:
        run = (
            await self.db.execute(
                select(InvestmentDecisionRun).where(
                    InvestmentDecisionRun.id == run_id,
                    InvestmentDecisionRun.account_id == account_id,
                )
            )
        ).scalar_one_or_none()
        if run is None:
            return None
        recommendations = list(
            (
                await self.db.execute(
                    select(InvestmentRecommendation).where(
                        InvestmentRecommendation.decision_run_id == run.id
                    )
                )
            ).scalars().all()
        )
        items = []
        for recommendation in recommendations:
            execution = (
                await self.db.execute(
                    select(InvestmentExecutionRecord).where(
                        InvestmentExecutionRecord.recommendation_id == recommendation.id
                    )
                )
            ).scalar_one_or_none()
            outcomes = []
            if execution:
                outcomes = list(
                    (
                        await self.db.execute(
                            select(InvestmentOutcomeSnapshot)
                            .where(InvestmentOutcomeSnapshot.execution_record_id == execution.id)
                            .order_by(InvestmentOutcomeSnapshot.window_hours)
                        )
                    ).scalars().all()
                )
            items.append({
                **_recommendation_dict(recommendation),
                "execution": _execution_dict(execution) if execution else None,
                "outcomes": [_outcome_dict(item) for item in outcomes],
            })
        return {**_run_dict(run), "recommendations": items}

    async def record_decision(
        self,
        recommendation_id: int,
        user_id: int,
        request: InvestmentDecisionRequest,
    ) -> dict[str, Any]:
        recommendation = await self.db.get(InvestmentRecommendation, recommendation_id)
        if recommendation is None:
            raise ValueError("投流建议不存在")
        record = (
            await self.db.execute(
                select(InvestmentExecutionRecord).where(
                    InvestmentExecutionRecord.recommendation_id == recommendation_id
                )
            )
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if record is None:
            record = InvestmentExecutionRecord(
                recommendation_id=recommendation_id,
                decision=request.decision,
                confirmed_by=user_id,
                confirmed_at=now,
                execution_note=request.note,
            )
            self.db.add(record)
        else:
            record.decision = request.decision
            record.confirmed_by = user_id
            record.confirmed_at = now
            record.execution_note = request.note
        recommendation.executed = False
        await self.db.commit()
        return {
            "recommendation_id": recommendation_id,
            "decision": request.decision,
            "executed": False,
        }

    async def record_execution(
        self,
        recommendation_id: int,
        user_id: int,
        request: InvestmentExecutionRequest,
    ) -> dict[str, Any]:
        recommendation = await self.db.get(InvestmentRecommendation, recommendation_id)
        if recommendation is None:
            raise ValueError("投流建议不存在")
        record = (
            await self.db.execute(
                select(InvestmentExecutionRecord).where(
                    InvestmentExecutionRecord.recommendation_id == recommendation_id
                )
            )
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if record is None:
            record = InvestmentExecutionRecord(
                recommendation_id=recommendation_id,
                decision="accepted",
                confirmed_by=user_id,
                confirmed_at=now,
            )
            self.db.add(record)
        elif record.decision not in {"accepted", "partially_accepted"}:
            raise ValueError("只有采纳或部分采纳的建议可以登记执行")
        record.actual_budget_fen = request.actual_budget_fen
        record.external_campaign_id = request.external_campaign_id
        record.external_plan_id = request.external_plan_id
        record.external_creative_id = request.external_creative_id
        record.execution_note = request.note
        record.executed_at = now
        recommendation.executed = True
        await self.db.commit()
        return {"recommendation_id": recommendation_id, "executed": True}


def _recommendation_dict(item: InvestmentRecommendation) -> dict[str, Any]:
    return {
        "id": int(item.id),
        "action": item.action,
        "target_type": item.target_type,
        "target_key": item.target_key,
        "target_label": item.target_label,
        "title": item.title,
        "reasoning": item.reasoning,
        "budget_min_fen": item.budget_min_fen,
        "budget_max_fen": item.budget_max_fen,
        "review_window_hours": item.review_window_hours,
        "stop_loss": item.stop_loss,
        "confidence": item.confidence,
        "evidence_refs": item.evidence_refs,
        "requires_human_confirm": item.requires_human_confirm,
        "executed": item.executed,
    }


def _run_dict(run: InvestmentDecisionRun) -> dict[str, Any]:
    return {
        "id": int(run.id),
        "stat_start": run.stat_start.isoformat(),
        "stat_end": run.stat_end.isoformat(),
        "trigger_type": run.trigger_type,
        "attribution_quality": run.attribution_quality,
        "status": run.status,
        "provider": run.provider,
        "model_used": run.model_used,
        "rule_version": run.rule_version,
        "prompt_version": run.prompt_version,
        "fallback_reason": run.fallback_reason,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _execution_dict(item: InvestmentExecutionRecord) -> dict[str, Any]:
    return {
        "id": int(item.id),
        "decision": item.decision,
        "actual_budget_fen": item.actual_budget_fen,
        "executed_at": item.executed_at.isoformat() if item.executed_at else None,
        "execution_note": item.execution_note,
    }


def _outcome_dict(item: InvestmentOutcomeSnapshot) -> dict[str, Any]:
    return {
        "window_hours": item.window_hours,
        "observed_at": item.observed_at.isoformat(),
        "incremental_spend_fen": item.incremental_spend_fen,
        "incremental_verified_gmv_fen": item.incremental_verified_gmv_fen,
        "verified_roi": item.verified_roi,
        "attribution_quality": item.attribution_quality,
    }


def _environment_dict(item: InvestmentEnvironmentSummaryDaily) -> dict[str, Any]:
    return {
        "summary_date": item.summary_date.isoformat(),
        "lookback_days": item.lookback_days,
        "patterns": item.patterns,
        "risks": item.risks,
        "sample_size": item.sample_size,
        "confidence": item.confidence,
        "evidence_refs": item.evidence_refs,
    }
