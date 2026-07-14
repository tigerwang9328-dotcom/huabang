from datetime import datetime, timezone
import json
from pathlib import Path

from app.services.member_action_service import (
    build_member_action_candidate,
    evaluate_member_action_outcome,
    summarize_member_action_outcomes,
)


def snapshot(**overrides):
    data = {
        "id": 77,
        "calc_date": "2026-07-14",
        "member_no": "VIP-001",
        "member_name": "张女士",
        "store_code": "285204",
        "risks": [{"code": "HIGH_BALANCE_DORMANT", "name": "大额余额长期未消费"}],
        "wakeup_reasons": [{"code": "HIGH_BALANCE_DORMANT", "name": "大额余额长期未消费"}],
        "metrics": {"current_balance": 6800, "recency_days": 132, "last_consume_date": "2026-03-04"},
        "preferences": [{"name": "羊毛衫", "product_code": "P001"}],
        "suggested_products": [
            {"product_code": "P001", "product_name": "羊毛衫", "sales_amount": 2200},
            {"product_code": "P002", "product_name": "夹克", "sales_amount": 1500},
        ],
        "candidate_guide_ids": ["G001"],
        "rule_version": "2026.07.1",
        "source_updated_at": "2026-07-14T05:50:00Z",
    }
    data.update(overrides)
    return data


def test_candidate_contains_reason_stocked_products_script_and_evidence():
    candidate = build_member_action_candidate(
        snapshot(),
        available_product_codes={"P001"},
        guide_users={
            "G001": {"user_id": 9, "real_name": "李导购", "store_codes": ["285204"]},
        },
    )

    assert candidate["contact_reason"] == "大额余额长期未消费"
    assert [item["product_code"] for item in candidate["recommended_products"]] == ["P001"]
    assert "余额" in candidate["suggested_script"]
    assert candidate["suggested_assignee"] == {"user_id": 9, "employee_no": "G001", "real_name": "李导购"}
    assert candidate["requires_human_confirmation"] is True
    assert candidate["data_evidence"]["source"] == "dm.dm_member_segment_snapshot"
    assert candidate["data_evidence"]["snapshot_id"] == 77


def test_candidate_evidence_is_json_serializable_with_database_types():
    candidate = build_member_action_candidate(
        snapshot(source_updated_at=datetime(2026, 7, 14, 5, 50, tzinfo=timezone.utc)),
    )

    assert json.loads(json.dumps(candidate, ensure_ascii=False))["data_evidence"]["source_updated_at"] == "2026-07-14T05:50:00+00:00"


def test_multiple_candidate_guides_never_prefill_an_owner():
    candidate = build_member_action_candidate(
        snapshot(candidate_guide_ids=["G001", "G002"]),
        guide_users={
            "G001": {"user_id": 9, "real_name": "李导购", "store_codes": ["285204"]},
            "G002": {"user_id": 10, "real_name": "王导购", "store_codes": ["285204"]},
        },
    )

    assert candidate["suggested_assignee"] is None
    assert candidate["responsibility_status"] == "unconfirmed"


def test_cross_store_guide_is_not_treated_as_a_credible_prefill():
    candidate = build_member_action_candidate(
        snapshot(),
        guide_users={
            "G001": {"user_id": 9, "real_name": "李导购", "store_codes": ["185805"]},
        },
    )

    assert candidate["suggested_assignee"] is None


def test_verified_linked_ticket_is_action_conversion():
    result = evaluate_member_action_outcome(
        {
            "contacted": True,
            "arrived": True,
            "converted": True,
            "conversion_amount": 1380,
            "linked_ticket_no": "POS-889",
        },
        linked_ticket_verified=True,
        verified_ticket_amount=1288,
        has_unlinked_repurchase=False,
    )

    assert result["attribution"] == "action_conversion"
    assert result["attributed_conversion"] is True
    assert result["attributed_amount"] == 1288
    assert result["reported_amount"] == 1380


def test_time_adjacent_purchase_without_ticket_link_is_natural_repurchase():
    result = evaluate_member_action_outcome(
        {"contacted": True, "arrived": False, "converted": False},
        linked_ticket_verified=False,
        has_unlinked_repurchase=True,
    )

    assert result["attribution"] == "natural_repurchase"
    assert result["attributed_conversion"] is False
    assert result["attributed_amount"] == 0


def test_claimed_conversion_without_verified_ticket_stays_unverified():
    result = evaluate_member_action_outcome(
        {
            "contacted": True,
            "arrived": True,
            "converted": True,
            "conversion_amount": 999,
            "linked_ticket_no": "POS-MISSING",
        },
        linked_ticket_verified=False,
        has_unlinked_repurchase=False,
    )

    assert result["attribution"] == "unverified_conversion"
    assert result["attributed_conversion"] is False
    assert result["attributed_amount"] == 0


def test_action_rates_use_explicit_denominators():
    summary = summarize_member_action_outcomes([
        {"confirmed": True, "contacted": True, "arrived": True, "attributed_conversion": True, "attributed_amount": 1000},
        {"confirmed": True, "contacted": True, "arrived": False, "attributed_conversion": False, "attributed_amount": 0},
        {"confirmed": True, "contacted": False, "arrived": False, "attributed_conversion": False, "attributed_amount": 0},
        {"confirmed": False, "contacted": False, "arrived": False, "attributed_conversion": False, "attributed_amount": 0},
    ])

    assert summary["confirmed_actions"] == 3
    assert summary["contact_rate"] == 2 / 3
    assert summary["arrival_rate"] == 1 / 2
    assert summary["conversion_rate"] == 1 / 2
    assert summary["attributed_sales"] == 1000


def test_member_and_task_apis_reuse_the_existing_task_workflow():
    repo = Path(__file__).resolve().parents[2]
    member_api = (repo / "backend" / "app" / "api" / "v1" / "member.py").read_text(encoding="utf-8")
    task_api = (repo / "backend" / "app" / "api" / "v1" / "task.py").read_text(encoding="utf-8")
    job = (repo / "backend" / "app" / "jobs" / "push_jobs.py").read_text(encoding="utf-8")

    assert '@router.get("/actions/overview")' in member_api
    assert '@router.get("/actions/list")' in member_api
    assert '@router.post("/actions/rebuild")' in member_api
    assert "member_contact_script" in task_api
    assert "MemberFollowupResult" in task_api
    assert "linked_ticket_no" in task_api
    assert '@router.get("/assignees",' in task_api
    assert "source_type == \"member_action\"" in task_api
    assert "UPDATE dm.dm_member_segment_snapshot" in task_api
    assert "VIP会员行动责任人必须属于会员归属门店" in task_api
    assert "generate_member_action_drafts" in job
    assert "CREATE TABLE" not in member_api + task_api
