from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.api.v1.task as task_api
from app.api.v1.task import TaskConfirmRequest
from app.services.ai_diagnosis_service import _can_assert_operating_profit
from app.services.exception_rule_service import RULE_SOURCE_BY_CODE, normalize_rule_finding
from app.services.member_segment_service import build_member_segment_result
from app.services.profit_service import REQUIRED_EXPENSE_TYPES, ExpenseAllocation, calculate_profit
from app.services.rule_engine import RULE_DEFS
from app.services.task_workflow_service import next_task_status


REPO = Path(__file__).resolve().parents[2]
ACCEPTANCE_DATE = date(2026, 7, 14)


def test_every_rule_engine_rule_has_three_traceable_evidence_samples():
    """Every deployed rule must retain facts, thresholds, source and drill-down data."""
    enabled_rule_codes = {rule_code for rule_code, *_ in RULE_DEFS}
    assert enabled_rule_codes <= set(RULE_SOURCE_BY_CODE)

    for rule_code in sorted(enabled_rule_codes):
        source_name, route = RULE_SOURCE_BY_CODE[rule_code]
        samples = []
        for sample_no in range(1, 4):
            normalized = normalize_rule_finding(
                business_date=ACCEPTANCE_DATE,
                finding={
                    "rule_id": rule_code,
                    "rule_name": f"{rule_code}验收规则",
                    "store_code": "285204",
                    "product_code": f"{rule_code}-SAMPLE-{sample_no}",
                    "title": f"{rule_code}证据样本{sample_no}",
                    "evidence": {
                        "sample_no": sample_no,
                        "observed_value": sample_no * 10,
                    },
                    "suggestion": "复核原始业务记录",
                    "source_record_id": f"RAW-{rule_code}-{sample_no}",
                    "source_updated_at": datetime(2026, 7, 14, 1, sample_no, tzinfo=timezone.utc),
                },
                thresholds={"warning_value": 9},
            )
            samples.append(normalized)

            assert normalized["source_name"] == source_name
            assert normalized["drilldown"]["route"] == route
            assert normalized["drilldown"]["params"]["date"] == "2026-07-14"
            assert normalized["data_snapshot"]["facts"]["sample_no"] == sample_no
            assert normalized["data_snapshot"]["thresholds"] == {"warning_value": 9}
            assert normalized["rule_version"].startswith("v-")
            assert normalized["evidence_hash"]
            assert len(normalized["evidence_records"]) == 1
            evidence = normalized["evidence_records"][0]
            assert evidence["source_table"] == source_name
            assert evidence["source_record_id"] == f"RAW-{rule_code}-{sample_no}"
            assert evidence["source_fields"]["observed_value"] == sample_no * 10

        assert len(samples) == 3
        assert len({item["unique_key"] for item in samples}) == 3


def test_inventory_warning_rules_persist_threshold_evidence_and_source_contract():
    service = (
        REPO / "backend" / "app" / "services" / "command_center_service.py"
    ).read_text(encoding="utf-8")
    migration = (
        REPO / "backend" / "alembic" / "versions"
        / "0a9b0c1d2e3f_inventory_warning_evidence.py"
    ).read_text(encoding="utf-8")
    inventory_rule_codes = {"R016", "R017", "R018", "R019", "R020", "R021"}

    assert "rule_id, thresholds, evidence, source_name" in service
    assert "FROM dm.dm_inventory_warning" in service
    for rule_code in inventory_rule_codes:
        assert f"'{rule_code}'" in service
        assert f"('{rule_code}'" in migration
    for column in ("rule_id", "thresholds", "evidence", "source_name"):
        assert f'Column("{column}"' in migration



def _approved_expenses(amount: str = "100") -> list[ExpenseAllocation]:
    return [
        ExpenseAllocation(
            expense_type=expense_type,
            amount=Decimal(amount),
            allocation_start=ACCEPTANCE_DATE,
            allocation_end=ACCEPTANCE_DATE,
            data_type="actual",
        )
        for expense_type in REQUIRED_EXPENSE_TYPES
    ]


def test_profit_gate_matches_approved_finance_and_blocks_estimated_conclusions():
    approved_expenses = _approved_expenses()
    approved = calculate_profit(
        period_start=ACCEPTANCE_DATE,
        period_end=ACCEPTANCE_DATE,
        net_sales=Decimal("2000"),
        cost_of_goods=Decimal("700"),
        is_cost_complete=True,
        expenses=approved_expenses,
    )
    approved_expense_total = sum((item.amount for item in approved_expenses), Decimal("0"))
    finance_approved_profit = Decimal("2000") - Decimal("700") - approved_expense_total

    assert approved.total_expense == approved_expense_total
    assert approved.operating_profit == finance_approved_profit == Decimal("500")
    assert approved.operating_profit_status == "ready"
    assert approved.finance_approved is True
    assert _can_assert_operating_profit({
        "operating_profit": approved.operating_profit,
        "is_cost_complete": True,
        "is_expense_complete": not approved.missing_expense_types,
        "finance_approved": approved.finance_approved,
    }) is True

    incomplete = calculate_profit(
        period_start=ACCEPTANCE_DATE,
        period_end=ACCEPTANCE_DATE,
        net_sales=Decimal("2000"),
        cost_of_goods=Decimal("700"),
        is_cost_complete=True,
        expenses=[item for item in approved_expenses if item.expense_type != "other"],
    )

    assert incomplete.gross_profit == Decimal("1300")
    assert incomplete.gross_profit_status == "ready"
    assert incomplete.missing_expense_types == ("other",)
    assert incomplete.operating_profit == Decimal("600")
    assert incomplete.operating_profit_status == "estimated"
    assert "expense_coverage_incomplete" in incomplete.reasons
    assert _can_assert_operating_profit({
        "operating_profit": incomplete.operating_profit,
        "is_cost_complete": True,
        "is_expense_complete": not incomplete.missing_expense_types,
        "finance_approved": incomplete.finance_approved,
    }) is False


def _vip_metrics() -> dict:
    return {
        "member_no": "VIP-ACCEPT-001",
        "store_code": "285204",
        "current_balance": 8000,
        "total_amount": 30000,
        "total_count": 30,
        "recency_days": 120,
        "avg_order_value": 1000,
        "current_period_orders": 1,
        "previous_period_orders": 6,
        "ticket_history_days": 180,
        "avg_discount_rate": 0.5,
        "discount_order_count": 3,
        "return_rate": 0.25,
        "return_orders": 2,
        "sales_order_count": 4,
        "latest_recharge_date": "2026-06-01",
        "days_since_recharge": 43,
        "post_recharge_order_count": 1,
        "gross_margin": 0.7,
        "cost_coverage": 0.98,
        "preferences": ["衬衫"],
        "suggested_products": ["SKU-1"],
        "candidate_guide_ids": ["G001"],
    }


def test_vip_wakeup_segmentation_keeps_rule_evidence_and_full_task_workflow():
    segment = build_member_segment_result(_vip_metrics(), ACCEPTANCE_DATE)

    assert segment["is_wakeup_candidate"] is True
    assert segment["wakeup_priority"] == 1
    assert segment["responsibility_status"] == "unconfirmed"
    assert segment["responsible_employee_no"] is None
    assert segment["candidate_guide_ids"] == ["G001"]
    assert all(item["rule_version"] for item in segment["labels"] + segment["risks"])
    assert all(item["evidence"] for item in segment["labels"] + segment["risks"])
    high_balance = next(item for item in segment["labels"] if item["code"] == "HIGH_BALANCE")
    assert high_balance["evidence"]["source"] == "baison.CZ_DQJE"
    assert high_balance["evidence"]["current_balance"] == 8000
    assert {item["code"] for item in segment["wakeup_reasons"]} >= {
        "HIGH_BALANCE_DORMANT",
        "HIGH_VALUE_INACTIVE",
    }

    status = next_task_status("draft", "confirm")
    assert status == "pending"
    status = next_task_status(status, "feedback")
    assert status == "feedback_submitted"
    status = next_task_status(status, "review", review_result="failed")
    assert status == "processing"
    status = next_task_status(status, "feedback")
    assert status == "feedback_submitted"
    status = next_task_status(status, "review", review_result="passed")
    assert status == "review_passed"
    assert next_task_status(status, "close") == "closed"


@pytest.mark.asyncio
async def test_notification_failure_does_not_lose_confirmed_vip_task(monkeypatch):
    task = SimpleNamespace(
        id=71,
        task_no="T202607140071",
        title="VIP唤醒回访",
        status="draft",
        priority=8,
        risk_level="high",
        assignee_id=19,
        assignee_name="测试负责人",
        assignee_role="operation_manager",
        due_date=ACCEPTANCE_DATE,
        related_store_code="285204",
        source_type="member_wakeup",
        source_id=901,
        requires_human_confirm=True,
        notification_status=None,
        notification_event_key=None,
        notification_kind=None,
        notification_attempt_count=0,
        notification_manual_retry_count=0,
        created_at=datetime(2026, 7, 14, 1, 0, tzinfo=timezone.utc),
        confirmed_by=None,
        confirmed_at=None,
        feedback_requirement="电话回访并记录结果",
        data_evidence={"member_no": "VIP-ACCEPT-001", "segment": "WAKEUP_CANDIDATE"},
        data_evidence_text=None,
        workflow_version=0,
    )

    class FakeDb:
        def __init__(self):
            self.committed = False

        async def commit(self):
            self.committed = True

    db = FakeDb()

    async def no_op(*_args, **_kwargs):
        return None

    monkeypatch.setattr(task_api, "_require_manager", no_op)
    monkeypatch.setattr(task_api, "_locked_scoped_task", lambda *_args, **_kwargs: _async_value(task))
    monkeypatch.setattr(task_api, "_canonical_assignee_role", lambda *_args, **_kwargs: _async_value("operation_manager"))
    monkeypatch.setattr(task_api, "_validate_assignment_scope", no_op)

    class FailingNotifier:
        async def enqueue_assignment(self, _db, current_task):
            current_task.notification_status = "queued"
            current_task.notification_event_key = "task:71:assignment:v1"
            current_task.notification_kind = "assignment"

        async def notify_assignment(self, task_id):
            assert task_id == 71
            assert db.committed is True
            return {"success": False, "status": "failed", "reason": "transport_error"}

    monkeypatch.setattr(task_api, "TaskNotificationService", FailingNotifier)

    response = await task_api.confirm_task(
        task_id=71,
        body=TaskConfirmRequest(),
        current_user=SimpleNamespace(id=3),
        db=db,
    )

    assert response.success is True
    assert response.data["status"] == "pending"
    assert response.data["notification"]["success"] is False
    assert task.status == "pending"
    assert task.confirmed_by == 3
    assert task.confirmed_at is not None
    assert task.requires_human_confirm is False
    assert db.committed is True


async def _async_value(value):
    return value


def test_head_one_step_rollback_preserves_phase_two_business_history_contract():
    latest = (
        REPO
        / "backend"
        / "alembic"
        / "versions"
        / "222d5e6f7081_task_notification_recipient_outbox.py"
    ).read_text(encoding="utf-8")
    workflow = (
        REPO
        / "backend"
        / "alembic"
        / "versions"
        / "1f0a2b3c4d5e_task_workflow_notifications.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "211c4d5e6f70"' in latest
    assert "def upgrade()" in latest and "def downgrade()" in latest
    assert "DROP TABLE IF EXISTS app.app_task_notification_outbox" in latest
    for historical_table in (
        "dm.dm_exception_audit",
        "dm.dm_exception_evidence",
        "dm.dm_member_segment_snapshot",
    ):
        assert historical_table not in latest
    assert "DELETE FROM app.app_action_task" not in latest

    assert "task12_migration_task_backup" in workflow
    assert "task12_migration_permission_meta_backup" in workflow
    assert "SET status=backup.old_status" in workflow
    assert "SET assignee_role=backup.old_role" in workflow


def test_phase_two_acceptance_record_separates_automation_from_boss_signoff():
    acceptance = REPO / "docs" / "acceptance" / "boss-command-center-phase2.md"
    content = acceptance.read_text(encoding="utf-8")

    for section in (
        "异常证据链",
        "利润门禁",
        "VIP 分层与任务闭环",
        "迁移回滚",
        "自动化验收证据",
        "老板人工签字",
    ):
        assert section in content
    assert "签字状态：待老板签字" in content
    assert "老板签字：通过" not in content
