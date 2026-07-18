from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.models.ai import AiAssistantConversation, AiAssistantMessage
import app.services.ai_assistant_service as assistant_service_module
from app.services.ai_assistant_service import (
    ASSISTANT_ALLOWED_ROLES,
    ASSISTANT_MODULES,
    AssistantContext,
    AiAssistantService,
    build_brief_payload,
    build_deterministic_answer,
    is_assistant_role_allowed,
    parse_assistant_context,
    sanitize_tavily_query,
    validate_assistant_model_answer,
)


def test_ai_assistant_models_match_conversation_contract():
    conversation_columns = set(AiAssistantConversation.__table__.columns.keys())
    message_columns = set(AiAssistantMessage.__table__.columns.keys())

    assert AiAssistantConversation.__table__.schema == "ai"
    assert AiAssistantMessage.__table__.schema == "ai"
    assert {
        "id", "user_id", "title", "route", "stat_date", "store_code",
        "is_archived", "last_message_at", "created_at", "updated_at", "archived_at",
    } <= conversation_columns
    assert {
        "id", "conversation_id", "user_id", "role", "content", "answer_payload",
        "sources", "context", "used_web", "created_at",
    } <= message_columns


def test_ai_assistant_migration_creates_conversation_and_message_tables():
    source = Path("alembic/versions/299f6a7b8c92_ai_assistant_conversation.py").read_text(encoding="utf-8")

    assert "ai_assistant_conversation" in source
    assert "ai_assistant_message" in source
    assert "CREATE SCHEMA IF NOT EXISTS ai" in source
    assert "ix_ai_assistant_conversation_user_last" in source


def test_assistant_role_gate_allows_only_management_roles():
    assert "boss" in ASSISTANT_ALLOWED_ROLES
    assert is_assistant_role_allowed(SimpleNamespace(is_admin=False), ["ceo"]) is True
    assert is_assistant_role_allowed(SimpleNamespace(is_admin=True), []) is True
    assert is_assistant_role_allowed(SimpleNamespace(is_admin=False), ["store_manager"]) is False


def test_sanitize_tavily_query_removes_internal_numbers_store_codes_and_pii_terms():
    query = sanitize_tavily_query("285204昨天销售13519元，会员张三审批备注异常，试穿率20%，帮我找服装零售经验")

    assert "285204" not in query
    assert "13519" not in query
    assert "20" not in query
    assert "张三" not in query
    assert "审批" not in query
    assert "备注" not in query
    assert "服装零售" in query
    assert len(query) <= 80


def test_parse_assistant_context_prefers_page_context_and_maps_route_module():
    context = parse_assistant_context(
        question="昨天库存有什么问题，285204门店也看一下",
        route="/app/ai-diagnosis/inventory?stat_date=2026-07-16&store_code=185805",
        stat_date="2026-07-15",
        store_code="285204",
        today=date(2026, 7, 17),
    )

    assert isinstance(context, AssistantContext)
    assert context.stat_date == "2026-07-15"
    assert context.store_code == "285204"
    assert context.scope_type == "store"
    assert context.modules == ["inventory"]


def test_parse_assistant_context_uses_question_when_page_context_absent():
    context = parse_assistant_context(
        question="昨天公司销售和会员有什么异常",
        route="/app/dashboard",
        stat_date=None,
        store_code=None,
        today=date(2026, 7, 17),
    )

    assert context.stat_date == "2026-07-16"
    assert context.store_code is None
    assert context.scope_type == "company"
    assert context.modules == ["sales", "members"]
    assert set(context.modules) < set(ASSISTANT_MODULES)


def test_build_brief_payload_hides_pending_numbers_and_marks_estimated_confidence():
    snapshots = [
        SimpleNamespace(
            stat_date=date(2026, 7, 17),
            data_status="ready",
            safe_context={"metrics": {"sales": {"label": "销售额", "value": 100, "unit": "元", "status": "ready"}}},
            conclusion={
                "executive_summary": "销售有增长",
                "key_findings": [{"text": "销售表现较好", "evidence_refs": ["metric:sales"], "confidence": "high"}],
                "recommendations": [{"text": "复盘高效门店", "requires_human_confirm": True, "executed": False}],
            },
        ),
        SimpleNamespace(
            stat_date=date(2026, 7, 17),
            data_status="pending_data",
            safe_context={"metrics": {"traffic": {"label": "客流", "value": 999, "status": "pending_data"}}},
            conclusion={"executive_summary": "客流未接入"},
        ),
        SimpleNamespace(
            stat_date=date(2026, 7, 17),
            data_status="estimated",
            safe_context={"metrics": {"cost": {"label": "费用", "value": 1, "status": "estimated"}}},
            conclusion={"key_findings": [{"text": "费用为估算", "confidence": "high"}]},
        ),
    ]

    payload = build_brief_payload(snapshots)

    assert payload["data_as_of"] == "2026-07-17"
    assert payload["data_health"]["ready"] == 1
    assert payload["data_health"]["pending_data"] == 1
    assert payload["data_health"]["estimated"] == 1
    assert all("999" not in item["text"] for item in payload["findings"])
    estimated = [item for item in payload["findings"] if item["text"] == "费用为估算"][0]
    assert estimated["confidence"] == "medium"


def test_build_deterministic_answer_keeps_actions_read_only_and_structured():
    snapshot = SimpleNamespace(
        stat_date=date(2026, 7, 17),
        data_status="stale",
        safe_context={"metrics": {"profit": {"label": "利润", "value": 10, "status": "stale"}}},
        conclusion={
            "executive_summary": "费用不完整，不能判断利润",
            "key_findings": [{"text": "费用口径待核验", "evidence_refs": ["metric:profit"], "confidence": "high"}],
            "recommendations": [{"text": "核验费用数据"}],
        },
    )

    answer = build_deterministic_answer(
        question="利润怎么样",
        snapshots=[snapshot],
        external_findings=[],
        used_web=False,
    )

    assert answer["answer_type"] == "internal"
    assert answer["used_web"] is False
    assert answer["data_as_of"] == "2026-07-17"
    assert answer["findings"][0]["confidence"] == "medium"
    assert answer["actions"][0]["requires_human_confirm"] is True
    assert answer["actions"][0]["executed"] is False
    assert any("数据较旧" in item for item in answer["limitations"])
    assert "external_findings" in answer


def test_build_deterministic_answer_preserves_external_intent_when_search_unavailable():
    answer = build_deterministic_answer(
        question="服装零售提高连带率有什么行业经验？",
        snapshots=[],
        external_findings=[],
        used_web=False,
        requested_web=True,
    )

    assert answer["answer_type"] == "external"
    assert answer["used_web"] is False
    assert any("外部经验检索暂不可用" in item for item in answer["limitations"])


def test_build_deterministic_answer_marks_mixed_intent_even_when_web_falls_back():
    snapshot = SimpleNamespace(
        stat_date=date(2026, 7, 17),
        data_status="ready",
        safe_context={"metrics": {"inventory": {"label": "库存", "value": 10, "status": "ready"}}},
        conclusion={"key_findings": [{"text": "库存需要关注", "evidence_refs": ["metric:inventory"], "confidence": "high"}]},
    )

    answer = build_deterministic_answer(
        question="结合华邦库存情况，参考服装零售经验给三条建议",
        snapshots=[snapshot],
        external_findings=[],
        used_web=False,
        requested_web=True,
    )

    assert answer["answer_type"] == "mixed"
    assert answer["used_web"] is False
    assert any("外部经验检索暂不可用" in item for item in answer["limitations"])


def test_ai_assistant_settings_defaults_are_safe():
    assert settings.AI_ASSISTANT_ENABLED is True
    assert settings.AI_ASSISTANT_WEB_SEARCH_ENABLED is False
    assert settings.AI_ASSISTANT_RATE_LIMIT_PER_MINUTE == 6
    assert settings.AI_ASSISTANT_TAVILY_MAX_RESULTS <= 5


def test_validate_assistant_model_answer_forces_read_only_actions_and_rejects_bad_refs():
    fallback = {
        "answer_type": "internal",
        "summary": "确定性回答",
        "findings": [],
        "evidence": [{"ref": "fact:sales", "label": "销售额", "value": 1}],
        "external_findings": [],
        "sources": [],
        "actions": [],
        "limitations": [],
        "suggested_questions": [],
        "data_as_of": "2026-07-17",
        "used_web": False,
    }
    payload = {
        **fallback,
        "summary": "模型整理后的回答",
        "findings": [{"text": "销售需要复盘", "evidence_refs": ["fact:sales"], "confidence": "high"}],
        "actions": [{"text": "复盘销售", "requires_human_confirm": False, "executed": True}],
    }

    validated = validate_assistant_model_answer(payload, fallback)

    assert validated["actions"][0]["requires_human_confirm"] is True
    assert validated["actions"][0]["executed"] is False
    assert validated["evidence"] == fallback["evidence"]

    bad = {**payload, "findings": [{"text": "伪造证据", "evidence_refs": ["fact:fake"], "confidence": "high"}]}
    try:
        validate_assistant_model_answer(bad, fallback)
    except ValueError as exc:
        assert "证据引用" in str(exc)
    else:
        raise AssertionError("bad evidence ref should fail")


@pytest.mark.asyncio
async def test_tavily_search_uses_redis_cache_and_stores_only_sanitized_summary(monkeypatch):
    calls = {"post": 0, "setex": []}

    class FakeRedis:
        async def get(self, key):
            return None

        async def setex(self, key, ttl, value):
            calls["setex"].append((key, ttl, value))

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"title": "服装零售经验", "url": "https://example.com", "content": "控制库存并复盘销售。"}]}

    class FakeClient:
        def __init__(self, timeout):
            assert timeout == settings.AI_ASSISTANT_TAVILY_TIMEOUT_SECONDS

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, json):
            calls["post"] += 1
            assert json["search_depth"] == "basic"
            assert json["max_results"] <= 5
            assert "285204" not in json["query"]
            assert "13519" not in json["query"]
            return FakeResponse()

    monkeypatch.setattr(settings, "AI_ASSISTANT_WEB_SEARCH_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "secret", raising=False)
    monkeypatch.setattr(assistant_service_module, "get_redis", lambda: FakeRedis())
    monkeypatch.setattr(assistant_service_module.httpx, "AsyncClient", FakeClient)

    service = AiAssistantService(db=None)
    results = await service.search_external_experience("285204销售13519元，找服装零售经验")

    assert calls["post"] == 1
    assert results[0]["url"] == "https://example.com"
    assert calls["setex"]
    assert "secret" not in calls["setex"][0][2]
    assert "13519" not in calls["setex"][0][2]


def test_scheduler_registers_ai_assistant_cleanup_job():
    source = Path("app/jobs/scheduler.py").read_text(encoding="utf-8")
    job_source = Path("app/jobs/ai_assistant_jobs.py").read_text(encoding="utf-8")

    assert "cleanup_ai_assistant_conversations" in source
    assert 'id="ai_assistant_conversation_cleanup"' in source
    assert "hour=3, minute=30" in source
    assert "cleanup_archived" in job_source
