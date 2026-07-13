from datetime import date, datetime, timezone
import inspect

import pytest
from pydantic import ValidationError

from app.api.v1.ai_diagnosis import ConfirmTasksRequest, confirm_action_tasks, overview
from app.integrations.baison.services.store_target_service import normalize_store_target
from app.services.ai_diagnosis_service import AIDiagnosisService, _is_expense_sync_covered


def test_confirm_request_accepts_only_server_side_diagnosis_ids():
    body = ConfirmTasksRequest(module="sales", diagnosis_ids=["sales-abc123"], stat_date="2026-07-11", store_code="285204")
    assert body.diagnosis_ids == ["sales-abc123"]
    with pytest.raises(ValidationError):
        ConfirmTasksRequest(tasks=[{"problem_type": "伪造任务"}])


def test_task_create_permission_is_only_required_by_confirm_route():
    confirm_dependency = inspect.signature(confirm_action_tasks).parameters["current_user"].default.dependency
    overview_dependency = inspect.signature(overview).parameters["current_user"].default.dependency
    assert any(cell.cell_contents == "task:create" for cell in confirm_dependency.__closure__ or ())
    assert overview_dependency.__name__ == "get_current_user"


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
