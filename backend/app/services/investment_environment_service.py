"""Evidence-limited daily summaries of the investment environment."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.life_data import (
    InvestmentEnvironmentSummaryDaily,
    InvestmentMetricSnapshot,
)
from app.services.ai_engine import AIEngine


PROMPT_VERSION = "investment-environment-v1"
CAUSAL_TERMS = ("造成", "导致", "证明", "带来提升", "必然")


class EnvironmentSummaryRejected(ValueError):
    pass


def deterministic_insufficient_summary(*, sample_size: int, lookback_days: int) -> dict[str, Any]:
    return {
        "patterns": [],
        "risks": [f"样本不足：{lookback_days}天窗口仅有{sample_size}条可用快照"],
        "confidence": "low",
        "evidence_refs": [],
    }


def validate_environment_payload(
    payload: dict[str, Any], *, allowed_evidence: set[str]
) -> dict[str, Any]:
    patterns = payload.get("patterns")
    risks = payload.get("risks")
    evidence_refs = payload.get("evidence_refs")
    confidence = payload.get("confidence")
    if not isinstance(patterns, list) or not isinstance(risks, list):
        raise EnvironmentSummaryRejected("invalid summary shape")
    if confidence not in {"low", "medium"}:
        raise EnvironmentSummaryRejected("confidence exceeds observational evidence")
    if any(term in str(item) for item in patterns for term in CAUSAL_TERMS):
        raise EnvironmentSummaryRejected("causal claim is not supported")
    if not isinstance(evidence_refs, list) or not set(evidence_refs).issubset(allowed_evidence):
        raise EnvironmentSummaryRejected("evidence reference does not exist")
    return {
        "patterns": [str(item)[:1000] for item in patterns[:30]],
        "risks": [str(item)[:1000] for item in risks[:30]],
        "confidence": confidence,
        "evidence_refs": evidence_refs[:100],
    }


class InvestmentEnvironmentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def summarize(
        self, account_id: str, summary_date: date, lookback_days: int
    ) -> InvestmentEnvironmentSummaryDaily:
        start = summary_date - timedelta(days=lookback_days - 1)
        snapshots = list(
            (
                await self.db.execute(
                    select(InvestmentMetricSnapshot).where(
                        InvestmentMetricSnapshot.account_id == account_id,
                        InvestmentMetricSnapshot.stat_end >= start,
                        InvestmentMetricSnapshot.stat_end <= summary_date,
                    )
                )
            ).scalars().all()
        )
        evidence = {f"snapshot:{int(item.id)}" for item in snapshots}
        contract = {
            "account_id": account_id,
            "summary_date": summary_date.isoformat(),
            "lookback_days": lookback_days,
            "snapshots": [
                {
                    "evidence_ref": f"snapshot:{int(item.id)}",
                    "stat_end": item.stat_end.isoformat(),
                    "dimension_type": item.dimension_type,
                    "dimension_label": item.dimension_label,
                    "spend_fen": item.spend_fen,
                    "ad_pay_gmv_fen": item.ad_pay_gmv_fen,
                    "verified_gmv_fen": item.verified_gmv_fen,
                    "refund_gmv_fen": item.refund_gmv_fen,
                    "attribution_quality": item.attribution_quality,
                }
                for item in snapshots
            ],
            "instruction": "只描述同期观察和风险，不得声称因果。",
        }
        input_hash = hashlib.sha256(
            json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        existing = (
            await self.db.execute(
                select(InvestmentEnvironmentSummaryDaily).where(
                    InvestmentEnvironmentSummaryDaily.account_id == account_id,
                    InvestmentEnvironmentSummaryDaily.summary_date == summary_date,
                    InvestmentEnvironmentSummaryDaily.lookback_days == lookback_days,
                    InvestmentEnvironmentSummaryDaily.input_hash == input_hash,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        model_used = "deterministic_rules"
        if len(snapshots) < 3:
            payload = deterministic_insufficient_summary(
                sample_size=len(snapshots), lookback_days=lookback_days
            )
        else:
            try:
                result = await AIEngine(self.db)._call_business_advice(
                    "你是投流环境观察器，只能输出patterns、risks、confidence、evidence_refs JSON。禁止因果断言。",
                    json.dumps(contract, ensure_ascii=False, sort_keys=True),
                    max_tokens=1800,
                )
                payload = validate_environment_payload(
                    json.loads(result["content"]), allowed_evidence=evidence
                )
                model_used = str(result.get("model") or settings.INVESTMENT_AI_MODEL)
            except Exception as exc:
                payload = {
                    "patterns": [],
                    "risks": [f"DeepSeek规律总结不可用，已回退：{type(exc).__name__}"],
                    "confidence": "low",
                    "evidence_refs": [],
                }

        statement = (
            pg_insert(InvestmentEnvironmentSummaryDaily)
            .values(
                account_id=account_id,
                summary_date=summary_date,
                lookback_days=lookback_days,
                input_hash=input_hash,
                provider="deepseek",
                model_used=model_used,
                prompt_version=PROMPT_VERSION,
                patterns=payload["patterns"],
                risks=payload["risks"],
                sample_size=len(snapshots),
                confidence=payload["confidence"],
                evidence_refs=payload["evidence_refs"],
            )
            .on_conflict_do_nothing(constraint="uq_investment_environment_summary_input")
            .returning(InvestmentEnvironmentSummaryDaily)
        )
        inserted = (await self.db.execute(statement)).scalar_one_or_none()
        await self.db.commit()
        if inserted:
            return inserted
        return (
            await self.db.execute(
                select(InvestmentEnvironmentSummaryDaily).where(
                    InvestmentEnvironmentSummaryDaily.account_id == account_id,
                    InvestmentEnvironmentSummaryDaily.summary_date == summary_date,
                    InvestmentEnvironmentSummaryDaily.lookback_days == lookback_days,
                    InvestmentEnvironmentSummaryDaily.input_hash == input_hash,
                )
            )
        ).scalar_one()
