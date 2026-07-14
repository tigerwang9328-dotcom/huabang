from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api.v1.task import TaskFeedbackRequest
from app.services.task_workflow_service import (
    MANAGER_ROLE_CODES,
    TaskTransitionError,
    can_submit_feedback,
    next_task_status,
)


def test_task_state_machine_requires_the_full_workflow():
    assert next_task_status("draft", "confirm") == "pending"
    assert next_task_status("pending", "feedback") == "feedback_submitted"
    assert next_task_status("overdue", "feedback") == "feedback_submitted"
    assert next_task_status("feedback_submitted", "review", review_result="passed") == "review_passed"
    assert next_task_status("review_passed", "close") == "closed"


def test_failed_review_returns_task_for_another_feedback_round():
    assert next_task_status("feedback_submitted", "review", review_result="failed") == "processing"


@pytest.mark.parametrize("status", ["draft", "pending", "processing", "feedback_submitted", "overdue"])
def test_task_cannot_skip_directly_to_closed(status):
    with pytest.raises(TaskTransitionError):
        next_task_status(status, "close")


def test_only_the_named_or_role_responsible_person_can_feedback():
    assert can_submit_feedback(7, None, 7, []) is True
    assert can_submit_feedback(7, None, 8, ["store_manager"]) is False
    assert can_submit_feedback(None, "store_manager", 8, ["store_manager"]) is True
    assert can_submit_feedback(None, "store_manager", 8, ["guide"]) is False
    assert can_submit_feedback(None, "operation", 8, ["operation_manager"]) is True
    assert can_submit_feedback(None, "运营经理", 8, ["operation_manager"]) is True
    assert can_submit_feedback(None, "财务经理 / 商品经理", 8, ["finance_manager"]) is True
    assert can_submit_feedback(None, "仓库主管 / 商品经理", 8, ["warehouse_manager"]) is True


def test_feedback_attachment_urls_reject_unsafe_schemes():
    safe = TaskFeedbackRequest(
        request_id="safe-request-0001",
        feedback_content="done",
        attachment_urls=["https://files.example.com/evidence.png"],
    )
    assert safe.attachment_urls == ["https://files.example.com/evidence.png"]
    with pytest.raises(ValidationError):
        TaskFeedbackRequest(
            request_id="unsafe-request-001",
            feedback_content="done",
            attachment_urls=["javascript:alert(document.domain)"],
        )


def test_manager_roles_are_explicit_and_do_not_include_ordinary_staff():
    assert {"super_admin", "boss", "ceo", "area_supervisor"} <= MANAGER_ROLE_CODES
    assert "staff" not in MANAGER_ROLE_CODES
    assert "guide" not in MANAGER_ROLE_CODES


def test_task_api_locks_rows_and_exposes_idempotency_keys():
    source = Path("app/api/v1/task.py").read_text(encoding="utf-8")
    assert "with_for_update()" in source
    assert "request_id" in source
    assert "TaskNotificationService" in source
    assert "begin_nested()" in source
    assert "except IntegrityError" in source
    assert "_scoped_task_statement" in source
    assert "effective_store_code.in_" in source
    assert 'scope.scope == "self"' in source
    assert 'AppActionTask.assignee_id == user.id' in source
    assert "enqueue_assignment" in source
    assert "_role_assignment_condition" in source
    assert "AppActionTask.assignee_id.is_(None)" in source


def test_notification_recipient_query_respects_scope_and_disabled_bindings():
    source = Path("app/services/task_notification_service.py").read_text(encoding="utf-8")
    assert "NOT EXISTS" in source
    assert "any_bind.user_id=u.id" in source
    assert "r.data_scope" in source
    assert "sys.sys_user_store" in source


def test_overdue_notification_is_attempted_at_most_once_per_day():
    source = Path("app/jobs/push_jobs.py").read_text(encoding="utf-8")
    notification = Path("app/services/task_notification_service.py").read_text(encoding="utf-8")
    assert "app_task_notification_outbox" in source
    assert ":business_date" in source
    assert "beijing_today()" in source
    assert "NOT EXISTS" in source
    assert "enqueue_overdue" in source
    assert "FOR UPDATE SKIP LOCKED" in notification
    assert "interval '30 minutes'" in notification


def test_overdue_job_has_runtime_dependencies_in_its_local_scope():
    source = Path("app/jobs/push_jobs.py").read_text(encoding="utf-8")
    function_source = source[source.index("async def run_overdue_reminder"):source.index("async def run_evening_diagnosis")]
    assert "from sqlalchemy import select, text" in function_source
    assert "from app.models.app import AppActionTask" in function_source


def test_task_notification_business_date_uses_beijing_timezone():
    import app.services.task_notification_service as notification

    assert hasattr(notification, "beijing_today")
    utc_boundary = datetime(2026, 7, 14, 16, 30, tzinfo=timezone.utc)
    assert notification.beijing_today(utc_boundary).isoformat() == "2026-07-15"


def test_assignment_notification_uses_a_durable_atomic_outbox_claim():
    notification = Path("app/services/task_notification_service.py").read_text(encoding="utf-8")
    scheduler = Path("app/jobs/scheduler.py").read_text(encoding="utf-8")
    push_jobs = Path("app/jobs/push_jobs.py").read_text(encoding="utf-8")
    assert "FOR UPDATE SKIP LOCKED" in notification
    assert "notification_pending_recipients" in notification
    assert "AppTaskNotificationOutbox" in notification
    assert "event_key" in notification
    assert "recipient_user_id" in notification
    assert "status='uncertain'" in notification
    assert "run_task_assignment_notifications" in push_jobs
    assert 'id="task_assignment_notifications"' in scheduler


def test_task_model_preserves_closure_and_notification_audit_fields():
    source = Path("app/models/app.py").read_text(encoding="utf-8")
    for field in (
        "closed_by",
        "closed_at",
        "notification_status",
        "notification_error",
        "notification_manual_retry_count",
        "notification_last_retry_by",
        "request_id",
    ):
        assert field in source


def test_manual_notification_retry_uses_the_stored_kind_and_is_audited():
    source = Path("app/api/v1/task.py").read_text(encoding="utf-8")
    notification = Path("app/services/task_notification_service.py").read_text(encoding="utf-8")
    assert '"/{task_id}/retry-notification"' in source
    assert "task.notification_event_key" in notification
    assert "outbox.notification_kind" in notification
    assert "notification_manual_retry_count" in source
    assert "notification_last_retry_by" in notification
    assert "notification_manual_retry_count" in notification
    assert 'AppTaskNotificationOutbox.status == "sending"' in notification
    assert "interval '30 minutes'" in notification
    assert 'notification_key=f"{outbox.event_key}:{outbox.recipient_user_id}"' in notification


def test_notification_outbox_keeps_assignment_and_overdue_events_separate():
    model = Path("app/models/app.py").read_text(encoding="utf-8")
    migration = Path("alembic/versions/222d5e6f7081_task_notification_recipient_outbox.py").read_text(encoding="utf-8")
    push = Path("app/jobs/push_jobs.py").read_text(encoding="utf-8")
    assert "class AppTaskNotificationOutbox" in model
    assert "app_task_notification_outbox" in migration
    assert "event_key" in migration
    assert "recipient_user_id" in migration
    assert "enqueue_overdue" in push


def test_role_recipient_scope_handles_department_and_has_no_silent_cap():
    source = Path("app/services/task_notification_service.py").read_text(encoding="utf-8")
    assert "r.data_scope IN ('all','company')" in source
    assert "r.data_scope='dept'" in source
    assert "u.dept_id=creator.dept_id" in source
    assert "LIMIT 10" not in source


def test_ai_diagnosis_tasks_store_canonical_actionable_roles():
    source = Path("app/services/ai_diagnosis_service.py").read_text(encoding="utf-8")
    assert "normalize_assignee_roles(owner)" in source
    assert '"assignee_role": assignee_role' in source
