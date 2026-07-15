import json
from datetime import date
from pathlib import Path

import pytest

from app.services.ai_engine import (
    AIEngine,
    build_template_command_conclusion,
    sanitize_command_context,
    validate_command_conclusion,
)
from app.services.ai_diagnosis_service import AIDiagnosisService
from app.services.report_service import ReportService
from app.core.config import settings


def _context(*, finance_complete=False):
    return {
        "metrics": {
            "sales_amount": {
                "value": 18560,
                "status": "ready",
                "source": "baison_pos",
                "as_of": "2026-07-12",
            },
            "gross_profit": {
                "value": 9120,
                "status": "estimated",
                "source": "baison_standard_purchase_price",
                "as_of": "2026-07-12",
            },
            "operating_profit": {
                "value": 7000,
                "status": "ready" if finance_complete else "estimated",
                "source": "finance",
                "as_of": "2026-07-12",
            },
            "online_sales": {
                "value": 9,
                "status": "pending_data",
                "source": "baison_pos.member_points",
                "as_of": "2026-07-12",
            },
            "member_phone": {
                "value": "13800000000",
                "status": "ready",
                "source": "member",
            },
        },
        "rules": [
            {
                "id": "R006:134681",
                "title": "负库存",
                "level": "critical",
                "evidence": ["库存=-1"],
                "source": "dm_inventory_warning",
            }
        ],
        "tasks": [{"id": 8, "title": "复核负库存", "status": "draft"}],
        "finance_complete": finance_complete,
    }


def test_ai_input_keeps_only_whitelisted_sourced_metrics():
    safe = sanitize_command_context(_context())

    assert "member_phone" not in safe["metrics"]
    assert safe["metrics"]["online_sales"]["value"] is None
    assert safe["metrics"]["online_sales"]["status"] == "pending_data"
    assert safe["metrics"]["sales_amount"]["source"] == "baison_pos"
    assert safe["finance_complete"] is False


def test_template_removes_operating_profit_when_expenses_missing():
    conclusion = build_template_command_conclusion(sanitize_command_context(_context()))
    rendered = json.dumps(conclusion, ensure_ascii=False)

    assert "费用" in rendered
    assert "公司盈利" not in rendered
    assert "公司亏损" not in rendered
    assert not any(item.get("key") == "operating_profit" for item in conclusion["facts"])
    assert all(item["status"] == "draft" for item in conclusion["actions"])
    assert all(item["requires_human_confirm"] is True for item in conclusion["actions"])


def test_diagnosis_metric_status_prevents_missing_sales_from_becoming_zero_fact():
    payload = AIDiagnosisService(None)._attach_command_conclusion({
        "summary": {"stat_date": "2026-07-12", "net_sales": 0, "order_count": 0},
        "diagnoses": [],
        "action_suggestions": [],
        "data_quality": {
            "missing_fields": ["门店销售汇总"],
            "warnings": ["销售ETL未完成"],
            "source_tables": ["dws_store_daily"],
            "metric_status": {"net_sales": "pending_data", "order_count": "pending_data"},
        },
    })

    conclusion = payload["command_conclusion"]
    assert not any(item["key"] in {"sales_amount", "order_count"} for item in conclusion["facts"])
    assert any("待接入" in item for item in conclusion["limitations"])


def test_incomplete_module_without_field_status_defaults_to_pending_not_zero():
    payload = AIDiagnosisService(None)._attach_command_conclusion({
        "summary": {"stat_date": "2026-07-12", "net_sales": 0, "gross_profit": 0, "gross_margin": 0},
        "diagnoses": [],
        "action_suggestions": [],
        "data_quality": {
            "is_complete": False,
            "missing_fields": ["销售/财务基础数据"],
            "warnings": [],
            "source_tables": ["dm_finance_profit_daily"],
        },
    })

    assert payload["command_conclusion"]["facts"] == []


def test_finance_complete_exposes_only_approved_operating_profit():
    payload = AIDiagnosisService(None)._attach_command_conclusion({
        "summary": {
            "stat_date": "2026-07-12",
            "finance_complete": True,
            "operating_profit": 500,
        },
        "diagnoses": [],
        "action_suggestions": [],
        "data_quality": {
            "is_complete": False,
            "missing_fields": [],
            "warnings": ["成本已按经营估算口径复核"],
            "source_tables": ["dm_finance_profit_daily"],
            "metric_status": {"operating_profit": "ready"},
        },
    })

    facts = payload["command_conclusion"]["facts"]
    assert any(item["key"] == "operating_profit" and item["value"] == 500 for item in facts)
    assert not any("费用未完整" in item for item in payload["command_conclusion"]["limitations"])


@pytest.mark.asyncio
async def test_common_metric_status_separates_ticket_and_cost_sources(monkeypatch):
    service = AIDiagnosisService(None)
    responses = iter([
        {
            "net_sales": 1200,
            "gross_profit": 0,
            "gross_margin": None,
            "source_row_count": 7,
            "is_cost_complete": True,
        },
        {"order_count": 0, "source_row_count": 0},
    ])

    async def fake_one(*_args, **_kwargs):
        return next(responses)

    monkeypatch.setattr(service, "_one", fake_one)
    result = await service._common_metrics(date(2026, 7, 12))

    assert result["_metric_status"]["net_sales"] == "ready"
    assert result["_metric_status"]["order_count"] == "pending_data"
    assert result["_metric_status"]["gross_profit"] == "ready"
    assert result["_metric_status"]["gross_margin"] == "pending_data"


def test_validator_rejects_profit_claim_without_complete_finance():
    payload = build_template_command_conclusion(sanitize_command_context(_context()))
    payload["recommendations"].append({"title": "公司盈利，应扩大采购", "reason": "利润较高"})

    with pytest.raises(ValueError, match="费用不完整"):
        validate_command_conclusion(payload, finance_complete=False)


@pytest.mark.asyncio
async def test_invalid_model_structure_falls_back_without_blocking_report(monkeypatch):
    engine = AIEngine(db=object())
    monkeypatch.setattr(settings, "AI_BUSINESS_ADVICE_ENABLED", True, raising=False)

    async def invalid_model(*_args, **_kwargs):
        return {"content": "not-json", "model": "fake"}

    monkeypatch.setattr(engine, "_call_business_advice", invalid_model)
    result = await engine.generate_command_conclusion(_context())

    assert result["mode"] == "template"
    assert result["facts"]
    assert result["limitations"]


@pytest.mark.asyncio
async def test_invalid_recommendation_shape_falls_back_without_blocking_report(monkeypatch):
    engine = AIEngine(db=object())
    monkeypatch.setattr(settings, "AI_BUSINESS_ADVICE_ENABLED", True, raising=False)
    model_payload = {
        "executive_summary": "经营状态需要持续跟进。",
        "key_findings": [],
        "recommendations": ["直接执行"],
        "limitations": [],
    }

    async def invalid_recommendation(*_args, **_kwargs):
        return {"content": json.dumps(model_payload, ensure_ascii=False), "model": "fake"}

    monkeypatch.setattr(engine, "_call_business_advice", invalid_recommendation)
    result = await engine.generate_command_conclusion(_context())

    assert result["mode"] == "template"
    assert result["facts"]


@pytest.mark.asyncio
async def test_model_profit_synonyms_and_forbidden_actions_are_not_exposed(monkeypatch):
    engine = AIEngine(db=object())
    monkeypatch.setattr(settings, "AI_BUSINESS_ADVICE_ENABLED", True, raising=False)
    model_payload = {
        "executive_summary": "本期实现盈利，利润为正。",
        "key_findings": [],
        "recommendations": [{
            "action_type": "review_inventory",
            "title": "立即采购并调拨库存",
            "reason": "利润较高。",
            "priority": "high",
            "evidence_refs": ["rule:R006:134681"],
            "responsible_role": "product_manager",
            "due_in_days": 1,
            "review_metric": "库存预警",
        }],
        "limitations": [],
    }

    async def model(*_args, **_kwargs):
        return {"content": json.dumps(model_payload, ensure_ascii=False), "model": "deepseek-v4-pro"}

    monkeypatch.setattr(engine, "_call_business_advice", model)
    result = await engine.generate_command_conclusion(_context(finance_complete=False))

    assert result["mode"] == "template"
    assert result["model_used"] == "deterministic_rules"
    rendered = json.dumps(result, ensure_ascii=False)
    assert "实现盈利" not in rendered
    assert "利润为正" not in rendered
    assert "立即采购" not in rendered
    assert "联系会员" not in rendered
    assert result["actions"][0]["status"] == "draft"
    assert result["actions"][0]["requires_human_confirm"] is True


@pytest.mark.asyncio
async def test_valid_model_output_enriches_but_never_rewrites_facts_or_risks(monkeypatch):
    engine = AIEngine(db=object())
    monkeypatch.setattr(settings, "AI_BUSINESS_ADVICE_ENABLED", True, raising=False)
    model_payload = {
        "executive_summary": "销售与订单基础稳定，先处理库存异常。",
        "key_findings": [{
            "title": "库存异常优先",
            "explanation": "规则证据指向需要人工复核的库存问题。",
            "confidence": "high",
            "evidence_refs": ["rule:R006:134681"],
        }],
        "recommendations": [{
            "action_type": "review_inventory",
            "title": "复核库存异常",
            "reason": "先核验证据，再决定后续处理。",
            "priority": "high",
            "evidence_refs": ["rule:R006:134681"],
            "responsible_role": "warehouse_manager",
            "due_in_days": 1,
            "review_metric": "负库存规则状态",
        }],
        "limitations": ["费用数据尚未完整接入。"],
    }
    calls = []

    async def model(_system, _user):
        calls.append(True)
        return {
            "content": json.dumps(model_payload, ensure_ascii=False),
            "model": "deepseek-v4-pro",
            "prompt_tokens": 20,
            "completion_tokens": 30,
            "total_tokens": 50,
        }

    monkeypatch.setattr(engine, "_call_business_advice", model)
    safe = sanitize_command_context(_context())
    expected = build_template_command_conclusion(safe)
    result = await engine.generate_command_conclusion(_context())

    assert calls == [True]
    assert result["mode"] == "model"
    assert result["model_used"] == "deepseek-v4-pro"
    assert result["facts"] == expected["facts"]
    assert result["risks"] == expected["risks"]
    assert result["executive_summary"] == model_payload["executive_summary"]
    assert result["actions"][0]["status"] == "draft"
    assert result["actions"][0]["requires_human_confirm"] is True


@pytest.mark.asyncio
async def test_empty_model_content_retries_once_then_uses_valid_json(monkeypatch):
    engine = AIEngine(db=object())
    monkeypatch.setattr(settings, "AI_BUSINESS_ADVICE_ENABLED", True, raising=False)
    responses = iter([
        {"content": "", "model": "deepseek-v4-pro"},
        {"content": json.dumps({
            "executive_summary": "先核验库存规则。",
            "key_findings": [],
            "recommendations": [],
            "limitations": [],
        }, ensure_ascii=False), "model": "deepseek-v4-pro"},
    ])
    calls = 0

    async def model(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return next(responses)

    monkeypatch.setattr(engine, "_call_business_advice", model)
    result = await engine.generate_command_conclusion(_context())

    assert calls == 2
    assert result["mode"] == "model"


@pytest.mark.asyncio
async def test_wrong_response_model_retries_once_then_falls_back(monkeypatch):
    engine = AIEngine(db=object())
    monkeypatch.setattr(settings, "AI_BUSINESS_ADVICE_ENABLED", True, raising=False)
    calls = 0

    async def wrong_model(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return {"content": json.dumps({
            "executive_summary": "先复核经营证据。",
            "key_findings": [], "recommendations": [], "limitations": [],
        }, ensure_ascii=False), "model": "deepseek-chat"}

    monkeypatch.setattr(engine, "_call_business_advice", wrong_model)
    result = await engine.generate_command_conclusion(_context())

    assert calls == 2
    assert result["mode"] == "template"
    assert result["model_used"] == "deterministic_rules"


@pytest.mark.asyncio
async def test_pending_or_stale_only_context_skips_model(monkeypatch):
    engine = AIEngine(db=object())
    monkeypatch.setattr(settings, "AI_BUSINESS_ADVICE_ENABLED", True, raising=False)
    context = {
        "finance_complete": False,
        "metrics": {
            "sales_amount": {"value": 100, "status": "stale", "source": "baison_pos"},
            "expense_amount": {"value": 0, "status": "pending_data", "source": "finance"},
        },
        "rules": [],
    }

    async def model(*_args, **_kwargs):
        pytest.fail("stale/pending-only context must not call the model")

    monkeypatch.setattr(engine, "_call_business_advice", model)
    result = await engine.generate_command_conclusion(context)

    assert result["mode"] == "template"
    assert result["fallback_reason"]


def test_context_removes_task_people_and_rule_pii():
    context = _context()
    context["tasks"] = [{"id": 9, "title": "联系张三", "owner": "张三", "status": "draft"}]
    context["rules"][0]["evidence"] = [
        "会员手机号13800000000",
        "会员号000344279445",
        "审批备注：张三同意",
        "员工：李四",
        "库存聚合异常",
    ]

    safe = sanitize_command_context(context)

    assert safe["tasks"] == []
    assert safe["rules"][0]["evidence"] == ["库存聚合异常"]
    assert "13800000000" not in json.dumps(safe, ensure_ascii=False)
    assert "张三" not in json.dumps(safe, ensure_ascii=False)
    assert "李四" not in json.dumps(safe, ensure_ascii=False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_ref", "numeric_narrative", "estimated_high",
        "execution_paraphrase", "profit_synonym", "named_person",
        "direct_name", "raw_json", "relative_multiplier",
        "unlabeled_person", "execution_ended", "mixed_finance_claim",
        "execution_completed_work", "mixed_finance_comma",
    ],
)
async def test_invalid_evidence_numeric_text_and_overconfident_estimate_fall_back(monkeypatch, mutation):
    engine = AIEngine(db=object())
    monkeypatch.setattr(settings, "AI_BUSINESS_ADVICE_ENABLED", True, raising=False)
    payload = {
        "executive_summary": "先复核经营证据。",
        "key_findings": [{
            "title": "库存异常优先",
            "explanation": "规则证据需要人工复核。",
            "confidence": "high",
            "evidence_refs": ["rule:R006:134681"],
        }],
        "recommendations": [],
        "limitations": [],
    }
    context = _context()
    if mutation == "unknown_ref":
        payload["key_findings"][0]["evidence_refs"] = ["rule:missing"]
    elif mutation == "numeric_narrative":
        payload["executive_summary"] = "销售额增长百分之十。"
    elif mutation == "estimated_high":
        payload["key_findings"][0]["evidence_refs"] = ["fact:gross_profit"]
    elif mutation == "execution_paraphrase":
        payload["executive_summary"] = "任务已完成，等待复查。"
    elif mutation == "profit_synonym":
        payload["executive_summary"] = "公司正在赚钱。"
    elif mutation == "named_person":
        payload["executive_summary"] = "负责人：张三需要复核。"
    elif mutation == "direct_name":
        payload["executive_summary"] = "请张三复核库存证据。"
    elif mutation == "unlabeled_person":
        payload["executive_summary"] = "张三负责库存复核。"
    elif mutation == "execution_ended":
        payload["executive_summary"] = "采购工作已经结束。"
    elif mutation == "execution_completed_work":
        payload["executive_summary"] = "采购工作已经完成。"
    elif mutation == "mixed_finance_claim":
        payload["executive_summary"] = "不能判断最终盈亏，但公司正在赚钱。"
    elif mutation == "mixed_finance_comma":
        payload["executive_summary"] = "不能判断最终盈亏，公司正在赚钱。"
    elif mutation == "raw_json":
        payload["executive_summary"] = '原始内容为{"member":"secret"}。'
    else:
        payload["executive_summary"] = "预计效果可能翻倍。"

    async def model(*_args, **_kwargs):
        return {"content": json.dumps(payload, ensure_ascii=False), "model": "deepseek-v4-pro"}

    monkeypatch.setattr(engine, "_call_business_advice", model)
    result = await engine.generate_command_conclusion(context)

    assert result["mode"] == "template"
    assert result["model_used"] == "deterministic_rules"


@pytest.mark.asyncio
async def test_report_with_all_stale_metrics_summarizes_limitations_not_zero_values():
    result = await ReportService()._generate_ai_summary({
        "stat_date": "2026-07-12",
        "total_sales": 0,
        "offline_sales": 0,
        "online_sales": 0,
        "order_count": 0,
        "item_count": 0,
        "avg_order_value": 0,
        "items_per_order": 0,
        "gross_profit": 0,
        "gross_margin": 0,
        "total_inventory": 0,
        "age_90_plus": 0,
        "today_expense": 0,
        "is_cost_complete": False,
        "is_finance_complete": False,
        "exception_count": 0,
        "inventory_warnings": [],
        "metric_status": {
            "sales": "stale",
            "sales_detail": "stale",
            "online_sales": "stale",
            "gross_profit": "stale",
            "inventory": "stale",
            "inventory_age": "stale",
        },
    }, object())

    assert "销售额0" not in result["summary"]
    assert "毛利额0" not in result["summary"]
    assert "过期" in result["summary"]


@pytest.mark.asyncio
async def test_report_zero_sales_keeps_gross_profit_but_not_undefined_margin():
    result = await ReportService()._generate_ai_summary({
        "stat_date": "2026-07-12",
        "total_sales": 0,
        "gross_profit": 0,
        "gross_margin": None,
        "is_cost_complete": True,
        "is_finance_complete": False,
        "inventory_warnings": [],
        "metric_status": {"sales": "ready", "gross_profit": "ready"},
    }, object())

    facts = result["command_conclusion"]["facts"]
    assert any(item["key"] == "gross_profit" and item["value"] == 0 for item in facts)
    assert not any(item["key"] == "gross_margin" for item in facts)
    assert any("毛利率待接入" in item for item in result["command_conclusion"]["limitations"])


@pytest.mark.asyncio
async def test_existing_report_rebuilds_and_returns_structured_conclusion():
    row = [None] * 45
    row[0] = date(2026, 7, 12)
    row[1:13] = [18560, 18551, 9, 9 / 18560, 18560, 34, 66, 545.88, 1.94, 0.8, 9120, 0.4914]
    row[13:23] = [800, 500, 0, 0, 2400000, 100000, 50000, 3, 1, 4]
    row[23:32] = ["摘要", "重点", "风险", "完整性", "deterministic_rules", None, True, True, None]
    row[32:41] = [19000, 100, 0.0054, 18760, 1119591, 0, 15800, 0.85, 2]
    row[41] = {}
    row[42] = {
        "sales": "ready", "sales_detail": "ready", "actual_pay": "ready",
        "online_sales": "ready", "returns": "ready", "gross_profit": "ready",
        "inventory": "ready", "inventory_age": "estimated", "vip_balance": "ready",
        "operating_profit": "ready",
    }
    row[43:45] = [0, 0]

    class Result:
        def fetchone(self):
            return tuple(row)

    class EmptyResult:
        def mappings(self):
            return self

        def first(self):
            return None

    class Db:
        calls = 0

        async def execute(self, *_args, **_kwargs):
            self.calls += 1
            return Result() if self.calls == 1 else EmptyResult()

    result = await ReportService()._get_existing_report("2026-07-12", Db())

    assert set(result["command_conclusion"]) >= {
        "facts", "risks", "recommendations", "actions", "limitations"
    }
    assert any(item["key"] == "operating_profit" for item in result["command_conclusion"]["facts"])


def test_report_and_diagnosis_use_the_constrained_conclusion_contract():
    report = Path("app/services/report_service.py").read_text(encoding="utf-8")
    diagnosis = Path("app/services/ai_diagnosis_service.py").read_text(encoding="utf-8")
    api = Path("app/api/v1/ai_diagnosis.py").read_text(encoding="utf-8")

    assert "generate_command_conclusion" in report
    assert 'statuses.get("sales")' in report
    assert "httpx.AsyncClient" not in report
    assert '"command_conclusion"' in diagnosis
    assert "ticket_source" in diagnosis
    assert "is_cost_complete" in diagnosis
    assert "finance_complete" in diagnosis
    assert "source_row_count" in diagnosis
    assert 'if not row or _num(row.get("net_sales")) == 0' not in diagnosis
    assert 'cost_complete = bool(row.get("is_cost_complete")) and bool(cost_source.get("is_cost_complete"))' in diagnosis
    assert "then sum(gross_profit)/sum(net_sales_amount) else 0 end gross_margin" not in diagnosis
    assert "suggestion_only" in api
