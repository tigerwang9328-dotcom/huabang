import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.api.v1.dashboard as dashboard_api
import app.api.v1.mobile as mobile_api
import app.services.command_center_service as command_center_service
from app.models.app import AppActionTask, AppTaskFeedback, AppTaskReview
from app.services.ai_engine import (
    AIEngine,
    build_template_command_conclusion,
    sanitize_command_context,
    validate_command_conclusion,
)
from app.services.task_workflow_service import next_task_status


REPO = Path(__file__).resolve().parents[2]


def _unsafe_context() -> dict:
    return {
        "finance_complete": False,
        "metrics": {
            "sales_amount": {
                "value": 13455,
                "status": "ready",
                "source": "baison_pos",
                "as_of": "2026-07-13",
            },
            "inventory_amount": {
                "value": 2401938.52,
                "status": "stale",
                "source": "apparel_inventory",
                "as_of": "2026-07-11",
            },
            "expense_amount": {
                "value": 0,
                "status": "pending_data",
                "source": "finance",
                "reason": "费用未完整接入",
            },
            "operating_profit": {
                "value": -999999,
                "status": "ready",
                "source": "finance",
            },
            "footfall": {
                "value": 0,
                "status": "ready",
                "source": "unknown",
            },
        },
        "rules": [{
            "id": "R018",
            "title": "高库存低动销",
            "level": "risk",
            "evidence": ["库存 120 件", "7 天销量 0 件"],
            "source": "rule_engine",
        }],
    }


def test_ai_context_hides_missing_inputs_and_never_turns_them_into_zero():
    safe = sanitize_command_context(_unsafe_context())

    assert "footfall" not in safe["metrics"]
    assert safe["metrics"]["expense_amount"]["value"] is None
    assert "operating_profit" not in safe["metrics"]

    conclusion = build_template_command_conclusion(safe)
    fact_keys = {item["key"] for item in conclusion["facts"]}
    rendered = json.dumps(conclusion, ensure_ascii=False)

    assert fact_keys == {"sales_amount"}
    assert "费用未完整接入" in rendered
    assert "库存金额数据已过期" in rendered
    assert "-999999" not in rendered
    assert all(item["status"] == "draft" for item in conclusion["actions"])
    assert all(item["requires_human_confirm"] is True for item in conclusion["actions"])


@pytest.mark.asyncio
async def test_model_unavailable_uses_deterministic_template(monkeypatch):
    engine = AIEngine(db=None)

    async def unavailable(*_args, **_kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(engine, "_call_business_advice", unavailable)
    result = await engine.generate_command_conclusion(_unsafe_context())

    assert result["mode"] == "template"
    assert result["model_used"] == "deterministic_rules"
    assert result["fallback_reason"]
    assert result["actions"][0]["requires_human_confirm"] is True


def test_incomplete_finance_rejects_deterministic_profit_claims():
    payload = {
        "facts": [{"label": "经营结论", "title": "公司亏损"}],
        "risks": [],
        "recommendations": [],
        "actions": [],
        "limitations": [],
    }

    with pytest.raises(ValueError, match="禁止输出确定性盈亏结论"):
        validate_command_conclusion(payload, finance_complete=False)


def test_attribution_and_vip_tasks_retain_full_human_audit_chain():
    status = next_task_status("draft", "confirm")
    assert status == "pending"
    status = next_task_status(status, "feedback")
    assert status == "feedback_submitted"
    status = next_task_status(status, "review", review_result="failed")
    assert status == "processing"
    status = next_task_status(status, "feedback")
    status = next_task_status(status, "review", review_result="passed")
    assert status == "review_passed"
    assert next_task_status(status, "close") == "closed"

    task_columns = set(AppActionTask.__table__.columns.keys())
    feedback_columns = set(AppTaskFeedback.__table__.columns.keys())
    review_columns = set(AppTaskReview.__table__.columns.keys())
    assert {
        "data_evidence", "confirmed_by", "confirmed_at", "assignee_id",
        "due_date", "workflow_version", "closed_by", "closed_at",
    } <= task_columns
    assert {"request_id", "feedback_by", "metrics_after", "created_at"} <= feedback_columns
    assert {
        "request_id", "reviewed_by", "review_result", "metrics_before",
        "metrics_after", "created_at",
    } <= review_columns


@pytest.mark.asyncio
async def test_web_and_mobile_use_the_same_command_center_snapshot(monkeypatch):
    expected = {
        "available": True,
        "report_date": "2026-07-13",
        "core_metrics": {
            "sales": {"value": 13455, "status": "ready"},
            "actual_pay": {"value": 8820, "status": "ready"},
            "return_amount": {"value": 0, "status": "ready"},
        },
    }

    async def fake_overview(_db, stat_date, _user):
        assert stat_date == "2026-07-13"
        return {"stat_date": stat_date}

    async def fake_snapshot(_db, report_date):
        assert report_date == date(2026, 7, 13)
        return expected

    monkeypatch.setattr(dashboard_api, "get_business_overview", fake_overview)
    monkeypatch.setattr(command_center_service, "get_command_center_snapshot", fake_snapshot)
    monkeypatch.setattr(mobile_api, "get_command_center_snapshot", fake_snapshot)

    web = await dashboard_api.get_overview(
        stat_date="2026-07-13",
        current_user=SimpleNamespace(id=1),
        db=object(),
    )
    mobile = await mobile_api.mobile_command_center(
        stat_date="2026-07-13",
        current_user=SimpleNamespace(id=1),
        db=object(),
    )

    assert web.data["command_center"] == mobile["data"] == expected


def test_command_center_exposes_return_amount_from_baison_refund_source():

    service = (
        REPO / "backend" / "app" / "services" / "command_center_service.py"
    ).read_text(encoding="utf-8")
    for metric in (
        "sales",
        "actual_pay",
        "inventory_amount",
        "vip_balance",
        "major_exception_count",
        "pending_task_count",
        "return_amount",
    ):
        assert f'"{metric}"' in service
    assert 'source="baison_pos.refund_amount"' in service


def test_final_acceptance_and_operations_runbook_cover_release_gates():
    acceptance = (
        REPO / "docs" / "acceptance" / "boss-command-center-final.md"
    ).read_text(encoding="utf-8")
    runbook = (
        REPO / "docs" / "operations" / "boss-command-center-runbook.md"
    ).read_text(encoding="utf-8")

    for gate in (
        "AI安全边界",
        "任务审计链",
        "Web与移动一致性",
        "退货金额",
        "生产抽查",
        "人工签字",
    ):
        assert gate in acceptance
    for operation in (
        "06:30",
        "幂等",
        "回滚",
        "退货金额",
        "一个完整北京时间日周期",
    ):
        assert operation in runbook
