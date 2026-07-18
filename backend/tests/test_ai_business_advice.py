import json
import inspect
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.ai_business_advice_service as advice_service_module
import app.services.ai_engine as ai_engine_module
from app.api.v1.ai_diagnosis import ConfirmTasksRequest
from app.api.v1.report import generate_boss_daily, get_boss_daily
from app.core.config import settings
from app.models.ai import AiBusinessAdviceSnapshot
from app.services.ai_business_advice_service import (
    BusinessAdviceService,
    BUSINESS_ADVICE_MODULES,
    BUSINESS_ADVICE_SCOPES,
    PROMPT_VERSION as SERVICE_PROMPT_VERSION,
    business_advice_input_hash,
    normalize_business_advice_context,
)
from app.services.ai_engine import AIEngine, PROMPT_VERSION as ENGINE_PROMPT_VERSION
from app.services.report_service import ReportService


def test_business_advice_prompt_contract_uses_v5_everywhere():
    assert SERVICE_PROMPT_VERSION == ENGINE_PROMPT_VERSION == "business-advice-v5"
    assert AiBusinessAdviceSnapshot.__table__.c.prompt_version.default.arg == "business-advice-v5"


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
    unordered_lists = {
        "metrics": {},
        "rules": [{"rule_id": "rule:b"}, {"rule_id": "rule:a"}],
        "tasks": [{"task_id": "task:b"}, {"task_id": "task:a"}],
    }
    reordered_lists = {
        "metrics": {},
        "rules": list(reversed(unordered_lists["rules"])),
        "tasks": list(reversed(unordered_lists["tasks"])),
    }
    assert business_advice_input_hash(unordered_lists) == business_advice_input_hash(reordered_lists)
    assert normalize_business_advice_context(unordered_lists) == normalize_business_advice_context(reordered_lists)
    assert [item["rule_id"] for item in normalize_business_advice_context(unordered_lists)["rules"]] == [
        "rule:a", "rule:b",
    ]
    changed_rule = {**reordered_lists, "rules": [{"rule_id": "rule:c"}, {"rule_id": "rule:a"}]}
    assert business_advice_input_hash(unordered_lists) != business_advice_input_hash(changed_rule)
    original_hash = business_advice_input_hash(left)
    monkeypatch.setattr(advice_service_module, "PROMPT_VERSION", "business-advice-v6")
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
    assert "existing.input_hash == input_hash" in source
    assert "normalize_business_advice_context" in source
    assert "and not force" in source
    assert 'existing.mode == "model"' not in source
    assert "template_cache_fresh" not in source
    assert "AI_BUSINESS_ADVICE_REFRESH_WINDOW_SECONDS" not in source
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
    assert "今天、昨天、本周、本月" in source
    assert "见证据引用" in source
    assert "只能在 limitations 使用固定句" in source




def test_business_advice_sensitive_text_allows_neutral_task_phrasing():
    assert ai_engine_module.contains_sensitive_text("任务执行进度需要主管复盘") is False
    assert ai_engine_module.contains_sensitive_text("任务跟进状态需要继续观察") is False
    assert ai_engine_module.contains_sensitive_text("张三负责复核异常") is True


def test_business_advice_finance_limitations_allow_non_deterministic_assessment_terms():
    assert ai_engine_module._validate_narrative(
        "费用数据待接入，无法评估盈亏",
        finance_complete=False,
    ) == "费用数据待接入，无法评估盈亏"
    assert ai_engine_module._validate_narrative(
        "费用数据待接入，无法计算净利润",
        finance_complete=False,
    ) == "费用数据待接入，无法计算净利润"
    with pytest.raises(ValueError, match="费用不完整"):
        ai_engine_module._validate_narrative("经营利润已经改善", finance_complete=False)



def test_business_advice_model_narrative_numbers_are_safely_coerced_without_changing_refs():
    safe_context = {
        "finance_complete": True,
        "metrics": {"inventory_amount": {"fact_id": "fact:inventory_amount", "status": "ready"}},
        "rules": [{"rule_id": "rule:risk", "level": "high"}],
    }
    payload = {
        "executive_summary": "近30天库存压力上升",
        "key_findings": [{
            "title": "90天库存偏高",
            "explanation": "有3款商品需要关注",
            "confidence": "high",
            "evidence_refs": ["rule:risk"],
        }],
        "recommendations": [{
            "action_type": "review_inventory",
            "title": "3天内复核库存",
            "reason": "90天库存风险较高",
            "priority": "high",
            "evidence_refs": ["rule:risk"],
            "responsible_role": "warehouse_manager",
            "due_in_days": 1,
            "review_metric": "90天库存复核状态",
        }],
        "limitations": [],
    }

    result = ai_engine_module.validate_model_business_advice(payload, safe_context=safe_context)

    rendered = json.dumps(result, ensure_ascii=False)
    assert "30" not in rendered
    assert "90" not in rendered
    assert "3款" not in rendered
    assert result["key_findings"][0]["evidence_refs"] == ["rule:risk"]
    assert result["recommendations"][0]["evidence_refs"] == ["rule:risk"]


def test_business_advice_narrative_rejects_named_relative_dates():
    with pytest.raises(ValueError, match="具体时间"):
        ai_engine_module._validate_narrative("今天需要复盘库存风险", finance_complete=True)
    with pytest.raises(ValueError, match="具体时间"):
        ai_engine_module._validate_narrative("本周需要关注销售趋势", finance_complete=True)


@pytest.mark.asyncio
async def test_business_advice_large_rule_context_uses_compact_prompt_and_more_completion_tokens(monkeypatch):
    captured = {}
    monkeypatch.setattr(settings, "AI_BUSINESS_ADVICE_MODEL", "deepseek-v4-pro", raising=False)
    monkeypatch.setattr(settings, "AI_BUSINESS_ADVICE_ENABLED", True, raising=False)

    class CapturingEngine(AIEngine):
        async def _call_business_advice(self, system_prompt, user_content, *, max_tokens=4000):
            captured["max_tokens"] = max_tokens
            captured["user_content"] = user_content
            return {
                "content": json.dumps({
                    "executive_summary": "库存压力需要优先复核",
                    "key_findings": [{
                        "title": "库存压力集中",
                        "explanation": "见证据引用提示库存风险",
                        "confidence": "high",
                        "evidence_refs": ["rule:r00"],
                    }],
                    "recommendations": [{
                        "action_type": "review_inventory",
                        "title": "复核库存风险",
                        "reason": "见证据引用提示库存压力",
                        "priority": "high",
                        "evidence_refs": ["rule:r00"],
                        "responsible_role": "warehouse_manager",
                        "due_in_days": 1,
                        "review_metric": "库存风险复核状态",
                    }],
                    "limitations": [],
                }, ensure_ascii=False),
                "model": "deepseek-v4-pro",
                "prompt_tokens": 1,
                "completion_tokens": 2,
                "total_tokens": 3,
            }

    rules = [
        {
            "id": f"r{i:02d}",
            "title": f"库存风险规则{i:02d}",
            "level": "critical" if i == 0 else "warning",
            "evidence": ["见证据引用"],
            "source": "rule_engine",
        }
        for i in range(40)
    ]
    result = await CapturingEngine(db=None).generate_command_conclusion({
        "finance_complete": True,
        "metrics": {
            "inventory_amount": {
                "value": 100,
                "status": "ready",
                "source": "dwd_inventory_balance",
                "as_of": "2026-07-16",
            },
        },
        "rules": rules,
    })

    assert result["mode"] == "model"
    assert captured["max_tokens"] > 4000
    assert captured["user_content"].count('"rule_id"') <= 15


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


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", [get_boss_daily, generate_boss_daily])
async def test_boss_daily_endpoints_attach_cached_company_overview_advice(monkeypatch, endpoint):
    report = {
        "report_date": "2026-07-14",
        "command_conclusion": {"mode": "template"},
    }
    calls = []

    async def fake_get_existing(_self, report_date, _db):
        assert report_date == "2026-07-14"
        return dict(report)

    async def fake_generate(_self, report_date, _db, *, force=False):
        assert report_date == "2026-07-14"
        assert force is False
        return dict(report)

    async def fake_attach(_self, payload, module, stat_date, store_code):
        calls.append((module, stat_date, store_code))
        payload["command_conclusion"] = {
            "mode": "model",
            "model_used": "deepseek-v4-pro",
        }
        return payload

    monkeypatch.setattr(ReportService, "_get_existing_report", fake_get_existing)
    monkeypatch.setattr(ReportService, "generate_boss_daily", fake_generate)
    monkeypatch.setattr(BusinessAdviceService, "attach_cached", fake_attach)

    kwargs = {
        "current_user": SimpleNamespace(id=1),
        "db": object(),
    }
    if endpoint is get_boss_daily:
        kwargs["report_date"] = "2026-07-14"
    else:
        kwargs["stat_date"] = "2026-07-14"
        kwargs["force"] = False

    response = await endpoint(**kwargs)

    assert response.data["command_conclusion"]["mode"] == "model"
    assert calls == [("overview", "2026-07-14", None)]


@pytest.mark.asyncio
async def test_blocked_boss_daily_generation_never_attaches_stale_ai_advice(monkeypatch):
    async def fake_generate(_self, report_date, _db, *, force=False):
        return {
            "report_date": report_date,
            "blocked": True,
            "block_reason": "销售同步未完成",
        }

    async def forbidden_attach(*_args, **_kwargs):
        raise AssertionError("blocked report must not attach cached AI advice")

    monkeypatch.setattr(ReportService, "generate_boss_daily", fake_generate)
    monkeypatch.setattr(BusinessAdviceService, "attach_cached", forbidden_attach)

    response = await generate_boss_daily(
        stat_date="2026-07-14",
        force=False,
        current_user=SimpleNamespace(id=1),
        db=object(),
    )

    assert response.data["blocked"] is True
    assert "command_conclusion" not in response.data
