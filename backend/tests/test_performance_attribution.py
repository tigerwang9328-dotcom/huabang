from datetime import datetime, timezone
from pathlib import Path

from app.services.performance_attribution_service import (
    REQUIRED_ATTRIBUTION_SOURCES,
    attribution_source_contract,
    build_adjudication_snapshot,
    build_attribution_exception_finding,
    build_rule_version,
    evaluate_attribution,
)


def ready_sources() -> dict[str, dict[str, str]]:
    return {
        source: {"status": "ready", "updated_at": "2026-07-14T06:30:00Z"}
        for source in REQUIRED_ATTRIBUTION_SOURCES
    }


def base_case(**overrides):
    data = {
        "business_date": "2026-07-13",
        "order_no": "POS-001",
        "transaction_store_code": "285204",
        "member_home_store_code": "285204",
        "claims": [{"claimant_id": "G001", "claim_type": "store_sale"}],
        "scheduled_guide_ids": ["G001"],
        "pos_guide_ids": ["G001"],
        "amendment_events": [],
        "douyin_owner_id": None,
        "member_owner_id": None,
        "recharge_owner_id": None,
        "is_refund": False,
    }
    data.update(overrides)
    return data


def test_missing_any_required_source_blocks_attribution():
    sources = ready_sources()
    sources["guide_schedule"] = {
        "status": "pending_data",
        "reason": "排班到门店关系尚未接入",
    }

    result = evaluate_attribution(base_case(), sources)

    assert result["status"] == "pending_data"
    assert result["metric_status"] == "pending_data"
    assert result["recommendation"] is None
    assert result["missing_sources"] == ["guide_schedule"]


def test_duplicate_claims_create_conflict_instead_of_silent_deduplication():
    result = evaluate_attribution(
        base_case(claims=[
            {"claimant_id": "G001", "claim_type": "store_sale", "claim_id": "C1"},
            {"claimant_id": "G001", "claim_type": "store_sale", "claim_id": "C2"},
        ]),
        ready_sources(),
    )

    assert result["status"] == "conflict"
    assert "duplicate_claim" in result["conflict_codes"]
    assert result["recommendation"] is None
    assert result["evidence"]["claim_count"] == 2
    assert result["evidence"]["distinct_claimant_count"] == 1


def test_same_order_claimed_by_multiple_people_creates_conflict():
    result = evaluate_attribution(
        base_case(claims=[
            {"claimant_id": "G001", "claim_type": "store_sale"},
            {"claimant_id": "G002", "claim_type": "douyin_followup"},
        ]),
        ready_sources(),
    )

    assert result["status"] == "conflict"
    assert "multiple_claimants" in result["conflict_codes"]
    assert result["recommendation"] is None
    assert result["candidate_owner_ids"] == ["G001", "G002"]


def test_manager_owner_edit_is_audited_and_not_auto_applied():
    result = evaluate_attribution(
        base_case(amendment_events=[{
            "event_id": "A-1",
            "field": "guide_id",
            "before": "G001",
            "after": "G009",
            "actor_id": "M001",
            "actor_role": "store_manager",
        }]),
        ready_sources(),
    )

    assert result["status"] == "conflict"
    assert "manual_owner_change" in result["conflict_codes"]
    assert result["recommendation"] is None
    assert result["evidence"]["amendment_events"][0]["before"] == "G001"
    assert result["evidence"]["amendment_events"][0]["after"] == "G009"


def test_cross_store_member_requires_human_adjudication():
    result = evaluate_attribution(
        base_case(
            transaction_store_code="285204",
            member_home_store_code="185805",
            member_owner_id="G088",
        ),
        ready_sources(),
    )

    assert result["status"] == "conflict"
    assert "cross_store_member" in result["conflict_codes"]
    assert result["recommendation"] is None
    assert result["evidence"]["transaction_store_code"] == "285204"
    assert result["evidence"]["member_home_store_code"] == "185805"


def test_refund_reverses_only_the_verified_original_owner():
    result = evaluate_attribution(
        base_case(
            order_no="RET-001",
            claims=[],
            is_refund=True,
            original_order_no="POS-889",
            original_owner_id="G007",
            pos_guide_ids=[],
            scheduled_guide_ids=[],
        ),
        ready_sources(),
    )

    assert result["status"] == "suggested"
    assert result["recommendation"] == {
        "owner_id": "G007",
        "owner_type": "guide",
        "action": "reverse_original_attribution",
    }


def test_refund_rule_can_disable_automatic_reversal_suggestion():
    result = evaluate_attribution(
        base_case(
            order_no="RET-002",
            claims=[],
            is_refund=True,
            original_order_no="POS-890",
            original_owner_id="G007",
            pos_guide_ids=[],
            scheduled_guide_ids=[],
        ),
        ready_sources(),
        {"refund_reverses_original_owner": False},
    )

    assert result["status"] == "pending_data"
    assert result["recommendation"] is None


def test_old_member_repurchase_requires_verified_history_before_using_owner():
    pending = evaluate_attribution(
        base_case(
            claims=[],
            pos_guide_ids=[],
            scheduled_guide_ids=[],
            is_old_member_repurchase=True,
            member_history_verified=False,
            member_owner_id="G008",
        ),
        ready_sources(),
    )
    verified = evaluate_attribution(
        base_case(
            claims=[],
            pos_guide_ids=[],
            scheduled_guide_ids=[],
            is_old_member_repurchase=True,
            member_history_verified=True,
            member_owner_id="G008",
        ),
        ready_sources(),
    )

    assert pending["status"] == "pending_data"
    assert "member_history" in pending["missing_sources"]
    assert verified["status"] == "suggested"
    assert verified["recommendation"]["owner_id"] == "G008"


def test_vip_recharge_owner_respects_the_versioned_rule_switch():
    case = base_case(
        claims=[],
        pos_guide_ids=[],
        scheduled_guide_ids=[],
        is_vip_recharge=True,
        recharge_owner_id="G009",
    )

    enabled = evaluate_attribution(case, ready_sources())
    disabled = evaluate_attribution(case, ready_sources(), {"vip_recharge_owner_enabled": False})

    assert enabled["status"] == "suggested"
    assert enabled["recommendation"]["owner_id"] == "G009"
    assert disabled["status"] == "pending_data"
    assert disabled["recommendation"] is None


def test_clean_single_owner_case_produces_a_suggestion_only():
    result = evaluate_attribution(base_case(), ready_sources())

    assert result["status"] == "suggested"
    assert result["recommendation"] == {
        "owner_id": "G001",
        "owner_type": "guide",
        "action": "attribute_sale",
    }
    assert result["requires_human_confirmation"] is True


def test_rule_version_changes_when_config_changes():
    first = build_rule_version({"cross_store_requires_review": True})
    second = build_rule_version({"cross_store_requires_review": False})

    assert first.startswith("attr-v-")
    assert first != second


def test_adjudication_snapshot_preserves_source_evidence():
    source_snapshot = {
        "status": "conflict",
        "evidence": {"claims": [{"claimant_id": "G001"}, {"claimant_id": "G002"}]},
    }
    decided_at = datetime(2026, 7, 14, 10, 30, tzinfo=timezone.utc)

    updated = build_adjudication_snapshot(
        source_snapshot,
        selected_owner_id="G002",
        selected_owner_type="guide",
        reason="核对原始沟通记录后确认",
        decision_evidence={"document_no": "CHAT-9"},
        decided_by=1,
        decided_at=decided_at,
    )

    assert updated["evidence"] == source_snapshot["evidence"]
    assert updated["adjudication"]["selected_owner_id"] == "G002"
    assert updated["adjudication"]["decided_by"] == 1
    assert updated["adjudication"]["decided_at"] == "2026-07-14T10:30:00+00:00"


def test_readjudication_keeps_the_previous_decision_in_history():
    first = build_adjudication_snapshot(
        {"status": "conflict", "evidence": {"order_no": "POS-001"}},
        selected_owner_id="G001",
        selected_owner_type="guide",
        reason="首次核对",
        decision_evidence={"document_no": "CHAT-1"},
        decided_by=1,
        decided_at=datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc),
    )

    second = build_adjudication_snapshot(
        first,
        selected_owner_id="G002",
        selected_owner_type="guide",
        reason="补充证据后更正",
        decision_evidence={"document_no": "CHAT-2"},
        decided_by=2,
        decided_at=datetime(2026, 7, 14, 11, 0, tzinfo=timezone.utc),
    )

    assert second["adjudication"]["selected_owner_id"] == "G002"
    assert second["adjudication_history"] == [first["adjudication"]]


def test_live_source_contract_does_not_overstate_unavailable_owner_data():
    sources = attribution_source_contract(
        transaction_updated_at="2026-07-14T06:20:00Z",
        refund_updated_at="2026-07-14T06:20:00Z",
        member_updated_at="2026-07-14T05:50:00Z",
    )

    assert sources["store_transaction"]["status"] == "ready"
    assert sources["refund_record"]["status"] == "ready"
    assert sources["douyin_source"]["status"] == "pending_data"
    assert sources["member_ownership"]["status"] == "pending_data"
    assert sources["guide_schedule"]["status"] == "pending_data"
    assert sources["amendment_log"]["status"] == "pending_data"


def test_only_conflicts_become_exception_audit_items():
    conflict_case = base_case(claims=[
        {"claimant_id": "G001", "claim_type": "store_sale"},
        {"claimant_id": "G002", "claim_type": "douyin_followup"},
    ])
    conflict = evaluate_attribution(conflict_case, ready_sources())
    clean = evaluate_attribution(base_case(), ready_sources())

    finding = build_attribution_exception_finding(conflict_case, conflict)

    assert finding["rule_code"] == "ATTRIBUTION_CONFLICT"
    assert finding["order_no"] == "POS-001"
    assert finding["metric_status"] == "ready"
    assert finding["responsibility_confirmed"] is False
    assert finding["evidence"]["conflict_codes"] == ["multiple_claimants"]
    assert build_attribution_exception_finding(base_case(), clean) is None


def test_audit_api_exposes_source_gate_evaluation_and_human_adjudication():
    repo = Path(__file__).resolve().parents[2]
    source = (repo / "backend" / "app" / "api" / "v1" / "audit.py").read_text(encoding="utf-8")

    assert '@router.get("/attribution/status",' in source
    assert '@router.post("/attribution/evaluate",' in source
    assert '@router.post("/exceptions/{exception_id}/adjudicate",' in source
    assert "build_adjudication_snapshot" in source
    assert 'if row["sync_updated_at"] else None' in source
    assert "UPDATE dwd.dwd_pos_ticket" not in source
