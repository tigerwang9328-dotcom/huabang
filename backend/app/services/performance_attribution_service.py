"""Deterministic, evidence-first performance attribution rules."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping


REQUIRED_ATTRIBUTION_SOURCES = (
    "douyin_source",
    "store_transaction",
    "member_ownership",
    "guide_schedule",
    "amendment_log",
    "cross_store_history",
    "refund_record",
)

DEFAULT_ATTRIBUTION_RULES: dict[str, Any] = {
    "douyin_owner_priority": True,
    "old_member_repurchase_requires_history": True,
    "vip_recharge_owner_enabled": True,
    "vip_consumption_owner_enabled": True,
    "cross_store_requires_review": True,
    "refund_reverses_original_owner": True,
    "manual_owner_change_requires_review": True,
    "duplicate_claim_requires_review": True,
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def build_rule_version(rules: Mapping[str, Any] | None = None) -> str:
    definition = {**DEFAULT_ATTRIBUTION_RULES, **dict(rules or {})}
    digest = hashlib.sha256(_canonical_json(definition).encode("utf-8")).hexdigest()
    return f"attr-v-{digest[:12]}"


def attribution_source_contract(
    *,
    transaction_updated_at: Any = None,
    refund_updated_at: Any = None,
    member_updated_at: Any = None,
) -> dict[str, dict[str, Any]]:
    """Describe production source readiness without overstating ownership data."""

    def available(source: str, updated_at: Any, reason: str) -> dict[str, Any]:
        if updated_at:
            return {"status": "ready", "source": source, "updated_at": updated_at, "reason": None}
        return {"status": "pending_data", "source": source, "updated_at": None, "reason": reason}

    sources = {
        "store_transaction": available(
            "dwd.dwd_pos_ticket",
            transaction_updated_at,
            "百胜门店交易在该业务日无完整同步记录",
        ),
        "refund_record": available(
            "baison_pos.refund_amount",
            refund_updated_at,
            "百胜退款记录在该业务日无完整同步记录",
        ),
        "cross_store_history": available(
            "dwd.dwd_pos_ticket+dim.dim_member",
            transaction_updated_at if transaction_updated_at and member_updated_at else None,
            "跨店消费需要门店交易和会员主档同时可用",
        ),
        "douyin_source": {
            "status": "pending_data",
            "source": "life_data_aggregate",
            "updated_at": None,
            "reason": "当前抖音数据仅到聚合层，缺少客户/订单级绑定",
        },
        "member_ownership": {
            "status": "pending_data",
            "source": "dim.dim_member",
            "updated_at": member_updated_at,
            "reason": "会员主档有注册门店，但没有已核验的责任导购字段",
        },
        "guide_schedule": {
            "status": "pending_data",
            "source": "hr_attendance_daily",
            "updated_at": None,
            "reason": "考勤已接入，但导购到门店的排班关系尚未接入",
        },
        "amendment_log": {
            "status": "pending_data",
            "source": "baison_ticket_change",
            "updated_at": None,
            "reason": "改单前后值日志尚未接入",
        },
    }
    return {source: sources[source] for source in REQUIRED_ATTRIBUTION_SOURCES}


def _normalise_claims(raw_claims: Any) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for raw in raw_claims or []:
        if not isinstance(raw, Mapping):
            continue
        claimant_id = str(raw.get("claimant_id") or "").strip()
        if not claimant_id:
            continue
        claim = dict(raw)
        claim["claimant_id"] = claimant_id
        claim["claim_type"] = str(raw.get("claim_type") or "unspecified").strip()
        claims.append(claim)
    return claims


def _candidate_ids(
    case: Mapping[str, Any],
    claims: list[dict[str, Any]],
    rules: Mapping[str, Any],
) -> list[str]:
    candidates = {claim["claimant_id"] for claim in claims}
    if rules["douyin_owner_priority"]:
        value = str(case.get("douyin_owner_id") or "").strip()
        if value:
            candidates.add(value)
    member_owner = str(case.get("member_owner_id") or "").strip()
    if member_owner and (
        (case.get("is_old_member_repurchase") and case.get("member_history_verified"))
        or (case.get("is_vip_consumption") and rules["vip_consumption_owner_enabled"])
    ):
        candidates.add(member_owner)
    recharge_owner = str(case.get("recharge_owner_id") or "").strip()
    if case.get("is_vip_recharge") and rules["vip_recharge_owner_enabled"] and recharge_owner:
        candidates.add(recharge_owner)
    for value in case.get("pos_guide_ids") or []:
        cleaned = str(value or "").strip()
        if cleaned:
            candidates.add(cleaned)
    return sorted(candidates)


def evaluate_attribution(
    case: Mapping[str, Any],
    source_statuses: Mapping[str, Mapping[str, Any]],
    rules: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one order without mutating any source transaction.

    A result is only suggestible when every required source reports ``ready``.
    Conflicting evidence is returned for human adjudication and never picks an
    owner automatically.
    """
    rule_definition = {**DEFAULT_ATTRIBUTION_RULES, **dict(rules or {})}
    missing_sources = [
        source
        for source in REQUIRED_ATTRIBUTION_SOURCES
        if (source_statuses.get(source) or {}).get("status") != "ready"
    ]
    claims = _normalise_claims(case.get("claims"))
    evidence = {
        "business_date": case.get("business_date"),
        "order_no": case.get("order_no"),
        "transaction_store_code": case.get("transaction_store_code"),
        "member_home_store_code": case.get("member_home_store_code"),
        "claims": claims,
        "claim_count": len(claims),
        "distinct_claimant_count": len({item["claimant_id"] for item in claims}),
        "scheduled_guide_ids": sorted({str(item) for item in case.get("scheduled_guide_ids") or []}),
        "pos_guide_ids": sorted({str(item) for item in case.get("pos_guide_ids") or []}),
        "amendment_events": copy.deepcopy(case.get("amendment_events") or []),
        "is_refund": bool(case.get("is_refund")),
        "original_order_no": case.get("original_order_no"),
        "source_statuses": copy.deepcopy(dict(source_statuses)),
    }
    base = {
        "rule_version": build_rule_version(rule_definition),
        "metric_status": "ready",
        "missing_sources": missing_sources,
        "candidate_owner_ids": [],
        "conflict_codes": [],
        "recommendation": None,
        "requires_human_confirmation": True,
        "evidence": evidence,
    }
    if missing_sources:
        return {**base, "status": "pending_data", "metric_status": "pending_data"}

    if (
        case.get("is_old_member_repurchase")
        and rule_definition["old_member_repurchase_requires_history"]
        and not case.get("member_history_verified")
    ):
        return {
            **base,
            "status": "pending_data",
            "metric_status": "pending_data",
            "missing_sources": [*missing_sources, "member_history"],
        }

    if case.get("is_refund"):
        if not rule_definition["refund_reverses_original_owner"]:
            return {**base, "status": "pending_data", "metric_status": "pending_data"}
        original_owner_id = str(case.get("original_owner_id") or "").strip()
        if not original_owner_id or not case.get("original_order_no"):
            return {**base, "status": "pending_data", "metric_status": "pending_data"}
        return {
            **base,
            "status": "suggested",
            "candidate_owner_ids": [original_owner_id],
            "recommendation": {
                "owner_id": original_owner_id,
                "owner_type": "guide",
                "action": "reverse_original_attribution",
            },
        }

    candidates = _candidate_ids(case, claims, rule_definition)
    conflicts: list[str] = []
    claim_keys = [(item["claimant_id"], item["claim_type"]) for item in claims]
    if rule_definition["duplicate_claim_requires_review"] and any(
        count > 1 for count in Counter(claim_keys).values()
    ):
        conflicts.append("duplicate_claim")
    if len({item["claimant_id"] for item in claims}) > 1:
        conflicts.append("multiple_claimants")
    if rule_definition["manual_owner_change_requires_review"] and any(
        str(item.get("field") or "") in {"guide_id", "owner_id", "attribution_owner"}
        and item.get("before") != item.get("after")
        for item in case.get("amendment_events") or []
        if isinstance(item, Mapping)
    ):
        conflicts.append("manual_owner_change")
    transaction_store = str(case.get("transaction_store_code") or "").upper()
    member_home_store = str(case.get("member_home_store_code") or "").upper()
    if (
        rule_definition["cross_store_requires_review"]
        and transaction_store
        and member_home_store
        and transaction_store != member_home_store
    ):
        conflicts.append("cross_store_member")
    scheduled = {str(item) for item in case.get("scheduled_guide_ids") or []}
    pos_guides = {str(item) for item in case.get("pos_guide_ids") or []}
    if pos_guides and not pos_guides.issubset(scheduled):
        conflicts.append("guide_not_scheduled")
    if len(candidates) > 1 and "multiple_claimants" not in conflicts:
        conflicts.append("multiple_owner_evidence")

    if conflicts:
        return {
            **base,
            "status": "conflict",
            "candidate_owner_ids": candidates,
            "conflict_codes": conflicts,
        }
    if not candidates:
        return {**base, "status": "pending_data", "metric_status": "pending_data"}
    owner_id = candidates[0]
    return {
        **base,
        "status": "suggested",
        "candidate_owner_ids": candidates,
        "recommendation": {
            "owner_id": owner_id,
            "owner_type": "guide",
            "action": "attribute_sale",
        },
    }


def build_attribution_exception_finding(
    case: Mapping[str, Any], result: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Convert only attribution conflicts into the shared exception model."""
    if result.get("status") != "conflict":
        return None
    order_no = str(case.get("order_no") or "").strip()
    store_code = str(case.get("transaction_store_code") or "").strip().upper() or None
    conflict_codes = list(result.get("conflict_codes") or [])
    evidence = {
        "rule_version": result.get("rule_version"),
        "conflict_codes": conflict_codes,
        "candidate_owner_ids": list(result.get("candidate_owner_ids") or []),
        "case_evidence": copy.deepcopy(result.get("evidence") or {}),
    }
    return {
        "rule_id": "ATTRIBUTION_CONFLICT",
        "rule_code": "ATTRIBUTION_CONFLICT",
        "rule_name": "业绩归属冲突",
        "definition_marker": result.get("rule_version"),
        "exception_type": "performance_attribution_conflict",
        "title": f"订单 {order_no or '未知'} 存在业绩归属冲突",
        "severity": "risk",
        "store_code": store_code,
        "order_no": order_no or None,
        "metric_status": "ready",
        "source_name": "performance_attribution",
        "responsibility_confirmed": False,
        "evidence": evidence,
        "evidence_records": [{
            "source_table": "performance_attribution",
            "record_key": order_no or _canonical_json(evidence),
            "source_record_id": order_no or None,
            "document_no": order_no or None,
            "source_fields": evidence,
            "source_updated_at": None,
        }],
    }


def build_adjudication_snapshot(
    source_snapshot: Mapping[str, Any],
    *,
    selected_owner_id: str,
    selected_owner_type: str,
    reason: str,
    decision_evidence: Mapping[str, Any],
    decided_by: int,
    decided_at: datetime | None = None,
) -> dict[str, Any]:
    owner_id = str(selected_owner_id or "").strip()
    decision_reason = str(reason or "").strip()
    if not owner_id:
        raise ValueError("selected_owner_id is required")
    if not decision_reason:
        raise ValueError("adjudication reason is required")
    timestamp = decided_at or datetime.now(timezone.utc)
    result = copy.deepcopy(dict(source_snapshot))
    previous_decision = result.get("adjudication")
    if previous_decision:
        history = list(result.get("adjudication_history") or [])
        history.append(copy.deepcopy(previous_decision))
        result["adjudication_history"] = history
    result["adjudication"] = {
        "selected_owner_id": owner_id,
        "selected_owner_type": str(selected_owner_type or "guide").strip(),
        "reason": decision_reason,
        "decision_evidence": copy.deepcopy(dict(decision_evidence or {})),
        "decided_by": int(decided_by),
        "decided_at": timestamp.isoformat(),
    }
    return result
