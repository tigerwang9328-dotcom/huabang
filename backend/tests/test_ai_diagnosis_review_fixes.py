from datetime import date, datetime, timezone
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app.api.v1.ai_diagnosis as ai_api_module
from app.api.v1.ai_diagnosis import (
    ConfirmTasksRequest, assignee_options, confirm_action_tasks, overview,
)
from app.integrations.baison.services.store_target_service import normalize_store_target
from app.services.ai_diagnosis_service import AIDiagnosisService, _is_expense_sync_covered


def test_confirm_request_accepts_only_server_side_diagnosis_ids():
    body = ConfirmTasksRequest(
        module="sales", diagnosis_ids=["sales-abc123"], stat_date="2026-07-11",
        store_code="285204", assignee_id=7, due_date="2026-07-18",
    )
    assert body.diagnosis_ids == ["sales-abc123"]
    with pytest.raises(ValidationError):
        ConfirmTasksRequest(tasks=[{"problem_type": "伪造任务"}])


def test_task_create_permission_is_only_required_by_confirm_route():
    confirm_dependency = inspect.signature(confirm_action_tasks).parameters["current_user"].default.dependency
    overview_dependency = inspect.signature(overview).parameters["current_user"].default.dependency
    assert any(cell.cell_contents == "task:create" for cell in confirm_dependency.__closure__ or ())
    assert overview_dependency.__name__ == "get_current_user"
    assignee_dependency = inspect.signature(assignee_options).parameters["current_user"].default.dependency
    assert any(cell.cell_contents == "task:create" for cell in assignee_dependency.__closure__ or ())


def test_assignee_options_route_precedes_dynamic_module_route():
    paths = [route.path for route in ai_api_module.router.routes if "GET" in (route.methods or set())]
    assert paths.index("/ai-diagnosis/assignee-options") < paths.index("/ai-diagnosis/{module}")


def test_diagnosis_id_is_stable_sha_identifier():
    service = AIDiagnosisService(None)
    first = service._diag("sales", "high", "标题", "描述", [], "原因", "动作", "店长", "今天", "销售额", "source")
    second = service._diag("sales", "high", "标题", "描述", [], "原因", "动作", "店长", "今天", "销售额", "source")
    assert first["id"] == second["id"]
    assert first["id"].startswith("sales-")
    assert len(first["id"].split("-", 1)[1]) == 16


def test_store_target_rows_keep_daily_snapshot_date():
    row = normalize_store_target(
        {"zddm": "285204", "ydzb": 100, "ydxs": 50, "dbl": "50%"},
        date(2026, 7, 1),
        snapshot_date=date(2026, 7, 12),
    )
    assert row["snapshot_date"] == date(2026, 7, 12)


def test_expense_completeness_requires_recent_sync_covering_diagnosis_date():
    synced = datetime(2026, 7, 12, 2, tzinfo=timezone.utc)
    assert _is_expense_sync_covered(synced, date(2026, 7, 11), now=datetime(2026, 7, 12, 8, tzinfo=timezone.utc))
    assert not _is_expense_sync_covered(synced, date(2026, 6, 1), now=datetime(2026, 7, 12, 8, tzinfo=timezone.utc))
    assert not _is_expense_sync_covered(None, date(2026, 7, 11), now=datetime(2026, 7, 12, 8, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_store_overview_uses_store_sales_instead_of_company_totals(monkeypatch):
    service = AIDiagnosisService(None)

    async def company_row(*_args, **_kwargs):
        return {"net_sales_amount": 999999, "total_order_count": 999, "gross_margin": 0.99}

    def module_payload(summary=None):
        return {"summary": summary or {}, "diagnoses": [], "data_quality": {"warnings": [], "missing_fields": []}}

    async def sales(*_args, **_kwargs):
        return module_payload({"net_sales": 321, "order_count": 4, "gross_margin": 0.52})

    async def empty_module(*_args, **_kwargs):
        return module_payload()

    async def overdue(*_args, **_kwargs):
        return 0

    monkeypatch.setattr(service, "_one", company_row)
    monkeypatch.setattr(service, "sales", sales)
    for name in ("products", "inventory", "hr", "finance", "audit"):
        monkeypatch.setattr(service, name, empty_module)
    monkeypatch.setattr(service, "_overdue_task_count", overdue)

    result = await service.overview("2026-07-14", "285204")

    assert result["summary"]["net_sales"] == 321
    assert result["summary"]["order_count"] == 4
    assert result["summary"]["gross_margin"] == 0.52


@pytest.mark.asyncio
async def test_limited_user_without_filter_is_resolved_to_owned_store(monkeypatch):
    captured = {}

    async def data_scope(*_args, **_kwargs):
        return SimpleNamespace(is_limited_store=True, store_codes=["285204"])

    class Diagnosis:
        async def overview(self, stat_date, store_code):
            captured["store_code"] = store_code
            return {"summary": {"stat_date": "2026-07-14"}}

    class Advice:
        def __init__(self, _db):
            pass

        async def attach_cached(self, payload, module, stat_date, store_code):
            captured["cached_store_code"] = store_code
            return payload

    async def service(_db):
        return Diagnosis()

    monkeypatch.setattr(ai_api_module, "get_data_scope", data_scope)
    monkeypatch.setattr(ai_api_module, "_service", service)
    monkeypatch.setattr(ai_api_module, "BusinessAdviceService", Advice)

    await ai_api_module.overview(
        stat_date=None, store_code=None, current_user=SimpleNamespace(id=8), db=object(),
    )

    assert captured == {"store_code": "285204", "cached_store_code": "285204"}


@pytest.mark.asyncio
async def test_limited_user_cannot_read_other_store_advice(monkeypatch):
    async def data_scope(*_args, **_kwargs):
        return SimpleNamespace(is_limited_store=True, store_codes=["285204"])

    monkeypatch.setattr(ai_api_module, "get_data_scope", data_scope)

    with pytest.raises(HTTPException) as exc:
        await ai_api_module.overview(
            stat_date=None, store_code="285702", current_user=SimpleNamespace(id=8), db=object(),
        )

    assert exc.value.status_code == 403
