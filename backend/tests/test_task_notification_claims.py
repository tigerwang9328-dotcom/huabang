from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.dingtalk as dingtalk_module
import app.services.task_notification_service as notification_module
from app.services.dingtalk import DingtalkService
from app.services.task_notification_service import TaskNotificationService


class _Result:
    def __init__(self, values=()):
        self._values = list(values)

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_notification_key_still_uses_the_rate_limit(monkeypatch):
    calls = []

    async def deny(key, **kwargs):
        calls.append((key, kwargs))
        return False

    class FakeDb:
        def __init__(self):
            self.added = []

        def add(self, value):
            self.added.append(value)

    monkeypatch.setattr(dingtalk_module, "rate_limit_check", deny)

    service = DingtalkService(FakeDb())

    async def no_token(**kwargs):
        return None

    monkeypatch.setattr(service, "_get_access_token", no_token)

    result = await service._send_to_user(
        "user-1",
        "title",
        "content",
        "task_assignment",
        "task_assignment",
        notification_key="task:7:assignment:v1:user-1",
    )

    assert result["success"] is False
    assert result["uncertain"] is True
    assert result["reason"] == "duplicate_delivery_state_unknown"
    assert calls == [(
        "dingtalk_push:user-1:task_assignment:task:7:assignment:v1:user-1",
        {"max_count": 1, "window_seconds": 300},
    )]


@pytest.mark.asyncio
async def test_manual_retry_drains_rows_that_are_already_queued(monkeypatch):
    task = SimpleNamespace(
        id=7,
        notification_event_key="task:7:assignment:v1",
        notification_kind="assignment",
        notification_status="queued",
        notification_manual_retry_count=0,
        notification_last_retry_by=None,
        notification_last_retry_at=None,
        notification_error=None,
        notification_updated_at=None,
    )

    class FakeDb:
        def __init__(self):
            self.scalar_calls = 0
            self.committed = False
            self.rolled_back = False

        async def scalar(self, statement):
            self.scalar_calls += 1
            return task if self.scalar_calls == 1 else 0

        async def execute(self, statement, params=None):
            sql = str(statement)
            if "manual_retry_count=manual_retry_count+1" in sql:
                retryable = "status IN ('queued','failed','skipped','uncertain')"
                return _Result([91] if retryable in sql else [])
            return _Result()

        async def commit(self):
            self.committed = True

        async def rollback(self):
            self.rolled_back = True

    db = FakeDb()
    monkeypatch.setattr(
        notification_module,
        "AsyncSessionLocal",
        lambda: _SessionContext(db),
    )
    service = TaskNotificationService()
    drained = []

    async def process(event_key):
        drained.append(event_key)
        return {"success": True, "status": "success"}

    monkeypatch.setattr(service, "_process_event", process)

    result = await service.retry(7, actor_id=11)

    assert result == {"success": True, "status": "success"}
    assert drained == ["task:7:assignment:v1"]
    assert db.committed is True


@pytest.mark.asyncio
async def test_stale_claim_is_rejected_immediately_before_external_send(monkeypatch):
    service = TaskNotificationService()

    async def claim(outbox_id):
        return {
            "task_id": 7,
            "event_key": "task:7:assignment:v1",
            "recipient_user_id": "user-1",
            "attempt_count": 1,
            "claim_generation": 9,
        }

    async def claim_is_current(db, outbox_id, claim_generation):
        return False

    outbox = SimpleNamespace(
        id=91,
        task_id=7,
        event_key="task:7:assignment:v1",
        notification_kind="assignment",
        recipient_user_id="user-1",
    )
    task = SimpleNamespace(
        id=7,
        title="Check inventory",
        due_date=None,
        feedback_requirement=None,
    )

    class FakeDb:
        def __init__(self):
            self.scalar_calls = 0

        async def scalar(self, statement):
            self.scalar_calls += 1
            return outbox if self.scalar_calls == 1 else task

    sent = []

    class FakeDingtalkService:
        def __init__(self, db):
            pass

        async def send_work_notification(self, **kwargs):
            sent.append(kwargs)
            return {"success": True}

    monkeypatch.setattr(service, "_claim", claim)
    monkeypatch.setattr(service, "_claim_is_current", claim_is_current, raising=False)
    monkeypatch.setattr(
        notification_module,
        "AsyncSessionLocal",
        lambda: _SessionContext(FakeDb()),
    )
    monkeypatch.setattr(notification_module, "DingtalkService", FakeDingtalkService)

    result = await service._deliver_outbox(91)

    assert result == {
        "success": False,
        "superseded": True,
        "reason": "notification_claim_replaced",
    }
    assert sent == []


def test_claim_generation_is_monotonic_and_guards_all_finalization():
    source = Path("app/services/task_notification_service.py").read_text(encoding="utf-8")

    assert "claim_generation=claim_generation+1" in source
    assert "outbox.claim_generation" in source
    assert "claim_generation=:claim_generation" in source
    assert "_claim_is_current" in source
    assert "attempt_count=CASE WHEN attempt_count>=" not in source


def test_disabled_roles_are_not_notification_recipients():
    source = Path("app/services/task_notification_service.py").read_text(encoding="utf-8")

    assert "JOIN sys.sys_role r ON r.id=ur.role_id AND r.code=ANY(:roles) AND r.status=1" in source


def test_migrations_preserve_permission_metadata_and_claim_generation():
    workflow = Path(
        "alembic/versions/1f0a2b3c4d5e_task_workflow_notifications.py"
    ).read_text(encoding="utf-8")
    outbox = Path(
        "alembic/versions/222d5e6f7081_task_notification_recipient_outbox.py"
    ).read_text(encoding="utf-8")

    for field in ("old_name", "old_module", "old_description", "migration_created"):
        assert field in workflow
    assert "UPDATE sys.sys_permission permission" in workflow
    assert "DELETE FROM sys.sys_permission permission" in workflow
    assert "migration_created=true" in workflow
    assert "claim_generation bigint NOT NULL DEFAULT 0" in outbox
    assert "next_attempt_at timestamptz" in outbox
    assert "idx_task_notification_outbox_sending_claimed" in outbox
    assert "idx_dingtalk_bind_user_any" in outbox


def test_budget_deferred_delivery_keeps_attempt_available_until_next_window():
    service = Path("app/services/task_notification_service.py").read_text(encoding="utf-8")
    assert "next_attempt_at" in service
    assert "_defer_until_budget_reset" in service
    assert "attempt_count=GREATEST(attempt_count-1,0)" in service
    assert "result.get(\"deferred\")" in service


def test_overdue_job_queues_every_candidate_and_drains_in_worker_batches():
    source = Path("app/jobs/push_jobs.py").read_text(encoding="utf-8")
    function_source = source[source.index("async def run_overdue_reminder"):source.index("async def run_evening_diagnosis")]
    assert "LIMIT 20" not in function_source
    assert 'process_pending(kind="overdue", limit=20)' in function_source
