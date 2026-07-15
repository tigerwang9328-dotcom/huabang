import json
import inspect
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.ai_business_advice_service as advice_service_module
import app.services.ai_engine as ai_engine_module
from app.api.v1.ai_diagnosis import ConfirmTasksRequest
from app.core.config import settings
from app.models.ai import AiBusinessAdviceSnapshot
from app.services.ai_business_advice_service import (
    BusinessAdviceService,
    BUSINESS_ADVICE_MODULES,
    BUSINESS_ADVICE_SCOPES,
    PROMPT_VERSION as SERVICE_PROMPT_VERSION,
    business_advice_input_hash,
)
from app.services.ai_engine import AIEngine, PROMPT_VERSION as ENGINE_PROMPT_VERSION


def test_business_advice_prompt_contract_uses_v2_everywhere():
    assert SERVICE_PROMPT_VERSION == ENGINE_PROMPT_VERSION == "business-advice-v2"
    assert AiBusinessAdviceSnapshot.__table__.c.prompt_version.default.arg == "business-advice-v2"


def test_business_advice_matrix_has_company_plus_seven_stores_and_nine_modules():
    assert BUSINESS_ADVICE_MODULES == (
        "overview", "sales", "products", "inventory", "finance",
        "hr", "members", "audit", "action-tasks",
    )
    assert BUSINESS_ADVICE_SCOPES[0] == ("company", "company")
    assert {code for scope, code in BUSINESS_ADVICE_SCOPES if scope == "store"} == {
        "134681", "285204", "285702", "185805", "185808", "285101", "285102",
    }
    assert len(BUSINESS_ADVICE_MODULES) * len(BUSINESS_ADVICE_SCOPES) == 72


def test_business_advice_input_hash_is_order_stable_and_changes_with_facts(monkeypatch):
    left = {"metrics": {"sales_amount": {"value": 10, "status": "ready"}}, "rules": []}
    reordered = {"rules": [], "metrics": {"sales_amount": {"status": "ready", "value": 10}}}
    changed = {"metrics": {"sales_amount": {"value": 11, "status": "ready"}}, "rules": []}

    assert business_advice_input_hash(left) == business_advice_input_hash(reordered)
    assert business_advice_input_hash(left) != business_advice_input_hash(changed)
    original_hash = business_advice_input_hash(left)
    monkeypatch.setattr(advice_service_module, "PROMPT_VERSION", "business-advice-v3")
    assert business_advice_input_hash(left) != original_hash

    monkeypatch.setattr(advice_service_module, "PROMPT_VERSION", SERVICE_PROMPT_VERSION)
    original_hash = business_advice_input_hash(left)
    original = settings.AI_BUSINESS_ADVICE_MODEL
    monkeypatch.setattr(settings, "AI_BUSINESS_ADVICE_MODEL", "deepseek-contract-change", raising=False)
    assert business_advice_input_hash(left) != original_hash or original == "deepseek-contract-change"

    model_hash = business_advice_input_hash(left)
    original_enabled = settings.AI_BUSINESS_ADVICE_ENABLED
    monkeypatch.setattr(
        settings,
        "AI_BUSINESS_ADVICE_ENABLED",
        not original_enabled,
        raising=False,
    )
    assert business_advice_input_hash(left) != model_hash


def test_business_advice_generation_uses_database_unit_lock():
    source = inspect.getsource(BusinessAdviceService.generate_unit)
    assert "pg_advisory_xact_lock" in source
    assert 'existing.mode == "model"' in source
    assert 'existing.mode == "template"' in source
    assert "AI_BUSINESS_ADVICE_REFRESH_WINDOW_SECONDS" in source
    assert "generated_at.astimezone(timezone.utc) >= request_started" in source
    assert "waited_for_lock or generated_at" not in source


def test_snapshot_unique_key_and_audit_columns_match_cache_contract():
    columns = set(AiBusinessAdviceSnapshot.__table__.columns.keys())
    assert {
        "stat_date", "module", "scope_type", "target_code", "safe_context",
        "input_hash", "conclusion", "mode", "status", "data_status",
        "provider", "model_name", "prompt_version", "schema_version",
        "prompt_tokens", "completion_tokens", "total_tokens", "latency_ms",
        "error_code", "fallback_reason", "generated_at", "updated_at",
        "last_attempt_status", "last_attempt_error_code", "last_attempt_at",
    } <= columns
    unique_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in AiBusinessAdviceSnapshot.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("stat_date", "module", "scope_type", "target_code") in unique_sets


def test_task_confirmation_requires_real_assignee_and_due_date_but_keeps_legacy_ids():
    modern = ConfirmTasksRequest(
        module="inventory",
        suggestion_key="inventory:company:abc",
        assignee_id=7,
        due_date=date(2026, 7, 18),
    )
    assert modern.suggestion_key == "inventory:company:abc"
    assert modern.assignee_id == 7

    legacy = ConfirmTasksRequest(
        module="inventory",
        diagnosis_ids=["inventory-old"],
        assignee_id=7,
        due_date=date(2026, 7, 18),
    )
    assert legacy.diagnosis_ids == ["inventory-old"]


@pytest.mark.asyncio
async def test_deepseek_json_mode_request_uses_configured_timeout_and_response_format(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "model": "deepseek-v4-pro",
                "choices": [{"message": {"content": json.dumps({"ok": True})}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            }

    class Client:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, headers, json):
            captured.update({"url": url, "headers": headers, "payload": json})
            return Response()

    monkeypatch.setattr(ai_engine_module.httpx, "AsyncClient", Client)
    monkeypatch.setattr(settings, "AI_BUSINESS_ADVICE_TIMEOUT_SECONDS", 25, raising=False)
    engine = AIEngine(db=None)

    result = await engine._call_openai_compatible(
        base_url="https://api.deepseek.com",
        api_key="secret",
        model="deepseek-v4-pro",
        system_prompt="Return json.",
        user_content="Use the requested json schema.",
        json_mode=True,
    )

    assert captured["timeout"] == 25
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["model"] == "deepseek-v4-pro"
    assert captured["payload"]["max_tokens"] >= 4000
    assert captured["payload"]["temperature"] <= 0.1
    assert result["total_tokens"] == 3


def test_business_advice_prompt_forbids_every_narrative_number_except_due_days():
    source = inspect.getsource(AIEngine.generate_command_conclusion)

    assert "除 due_in_days 外" in source
    assert "阿拉伯数字、中文数字、日期" in source
    assert "见证据引用" in source
    assert "只能在 limitations 使用固定句" in source


def test_skill_exporter_is_select_only_and_never_exposes_raw_business_rows():
    source = Path("scripts/export_ai_business_advice_context.py").read_text(encoding="utf-8")
    lowered = source.lower()
    assert "ai_business_advice_snapshot" in source
    assert "dm_boss_daily_report" in source
    assert "UNION ALL" in source
    assert "snapshot_available" in source
    assert "raw_json" not in lowered
    for statement in ("insert into", "update ", "delete from", "truncate ", "app_action_task"):
        assert statement not in lowered


def test_task_confirmation_revalidates_snapshot_hash_and_data_status():
    source = inspect.getsource(__import__(
        "app.services.ai_diagnosis_service", fromlist=["AIDiagnosisService"]
    ).AIDiagnosisService.confirm_action_tasks)
    assert "current_input_hash" in source
    assert 'row.get("input_hash") != current_input_hash' in source
    assert '{"stale", "pending_data"}' in source
    assert 'action.get("requires_human_confirm") is not True' in source
