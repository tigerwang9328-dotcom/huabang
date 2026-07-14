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
                "source": "baison_cost",
                "as_of": "2026-07-12",
            },
            "operating_profit": {
                "value": 7000,
                "status": "ready",
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


def test_template_marks_estimates_and_blocks_operating_profit_when_expenses_missing():
    conclusion = build_template_command_conclusion(sanitize_command_context(_context()))
    rendered = json.dumps(conclusion, ensure_ascii=False)

    assert "预估" in rendered
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

    async def invalid_model(*_args, **_kwargs):
        return {"content": "not-json", "model": "fake"}

    monkeypatch.setattr(engine, "_call_ai", invalid_model)
    result = await engine.generate_command_conclusion(_context())

    assert result["mode"] == "template"
    assert result["facts"]
    assert result["limitations"]


@pytest.mark.asyncio
async def test_invalid_recommendation_shape_falls_back_without_blocking_report(monkeypatch):
    engine = AIEngine(db=object())
    model_payload = build_template_command_conclusion(sanitize_command_context(_context()))
    model_payload["recommendations"] = ["直接执行"]

    async def invalid_recommendation(*_args, **_kwargs):
        return {"content": json.dumps(model_payload, ensure_ascii=False), "model": "fake"}

    monkeypatch.setattr(engine, "_call_ai", invalid_recommendation)
    result = await engine.generate_command_conclusion(_context())

    assert result["mode"] == "template"
    assert result["facts"]


@pytest.mark.asyncio
async def test_model_profit_synonyms_and_forbidden_actions_are_not_exposed(monkeypatch):
    engine = AIEngine(db=object())
    model_payload = build_template_command_conclusion(
        sanitize_command_context(_context(finance_complete=False))
    )
    model_payload["recommendations"] = [
        {"title": "本期实现盈利，利润为正", "reason": "建议扩大采购并联系会员"}
    ]
    model_payload["actions"] = [
        {
            "title": "立即采购并调拨库存，同时联系会员",
            "owner": "商品经理",
            "status": "已执行",
            "requires_human_confirm": False,
            "evidence": ["R006:134681"],
        }
    ]

    async def model(*_args, **_kwargs):
        pytest.fail("deterministic command conclusions must not call a language model")

    monkeypatch.setattr(engine, "_call_ai", model)
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

    class Db:
        async def execute(self, *_args, **_kwargs):
            return Result()

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
