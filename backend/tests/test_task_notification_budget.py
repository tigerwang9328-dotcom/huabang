from datetime import datetime
from pathlib import Path

import pytest
import httpx

import app.services.dingtalk as dingtalk_module

from app.services.dingtalk import DingtalkService
from app.services.dingtalk_budget_service import (
    DINGTALK_DAILY_API_LIMIT,
    DINGTALK_TASK_RESERVED_CALLS,
    DingtalkApiBudgetExceeded,
    budget_ceiling,
    consume_daily_dingtalk_budget,
)


class FakeRedis:
    def __init__(self, used=0):
        self.used = used
        self.expiries = []

    async def incr(self, _key):
        self.used += 1
        return self.used

    async def decr(self, _key):
        self.used -= 1
        return self.used

    async def expire(self, key, ttl):
        self.expiries.append((key, ttl))


def test_normal_sync_preserves_calls_for_task_assignment_and_overdue():
    assert DINGTALK_DAILY_API_LIMIT == 160
    assert DINGTALK_TASK_RESERVED_CALLS > 0
    assert budget_ceiling("normal") == DINGTALK_DAILY_API_LIMIT - DINGTALK_TASK_RESERVED_CALLS
    assert budget_ceiling("task") == DINGTALK_DAILY_API_LIMIT


@pytest.mark.asyncio
async def test_normal_sync_is_stopped_at_reserved_boundary(monkeypatch):
    ceiling = budget_ceiling("normal")
    redis = FakeRedis(used=ceiling)
    monkeypatch.setattr("app.services.dingtalk_budget_service.get_redis", lambda: _async_value(redis))

    with pytest.raises(DingtalkApiBudgetExceeded):
        await consume_daily_dingtalk_budget("/attendance/list", category="attendance")
    assert redis.used == ceiling


@pytest.mark.asyncio
async def test_task_notification_can_use_the_reserved_budget(monkeypatch):
    redis = FakeRedis(used=budget_ceiling("normal"))
    monkeypatch.setattr("app.services.dingtalk_budget_service.get_redis", lambda: _async_value(redis))

    used = await consume_daily_dingtalk_budget(
        "/topapi/message/corpconversation/asyncsend_v2",
        category="task_notification",
        priority="task",
        now=datetime(2026, 7, 14, 12, 0, 0),
    )
    assert used == budget_ceiling("normal") + 1


async def _async_value(value):
    return value


class _PushDb:
    def __init__(self):
        self.rows = []

    def add(self, row):
        self.rows.append(row)


@pytest.mark.asyncio
async def test_task_budget_denial_is_deferred_instead_of_failed(monkeypatch):
    service = DingtalkService(_PushDb())
    monkeypatch.setattr(dingtalk_module, "rate_limit_check", lambda *args, **kwargs: _async_value(True))
    monkeypatch.setattr(service, "_get_access_token", lambda **kwargs: _async_value("token"))

    async def deny(*args, **kwargs):
        raise DingtalkApiBudgetExceeded("daily budget exhausted")

    monkeypatch.setattr(dingtalk_module, "consume_daily_dingtalk_budget", deny)
    monkeypatch.setattr(dingtalk_module, "record_dingtalk_api_call", lambda **kwargs: _async_value(None))
    result = await service._send_to_user(
        "user-1", "title", "content", "task_assignment", "task_assignment",
        notification_key="task:1:assignment:v1:user-1",
    )
    assert result["deferred"] is True
    assert result["reason"] == "budget_exhausted"


@pytest.mark.asyncio
async def test_task_transport_timeout_is_uncertain_and_not_retried(monkeypatch):
    service = DingtalkService(_PushDb())
    monkeypatch.setattr(dingtalk_module, "rate_limit_check", lambda *args, **kwargs: _async_value(True))
    monkeypatch.setattr(service, "_get_access_token", lambda **kwargs: _async_value("token"))
    monkeypatch.setattr(dingtalk_module, "consume_daily_dingtalk_budget", lambda *args, **kwargs: _async_value(1))
    monkeypatch.setattr(dingtalk_module, "record_dingtalk_api_call", lambda **kwargs: _async_value(None))
    monkeypatch.setattr(dingtalk_module.asyncio, "sleep", lambda *_: _async_value(None))
    calls = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            calls.append((args, kwargs))
            raise httpx.ReadTimeout("result unknown")

    monkeypatch.setattr(dingtalk_module.httpx, "AsyncClient", lambda **kwargs: Client())
    result = await service._send_to_user(
        "user-1", "title", "content", "task_assignment", "task_assignment",
        notification_key="task:1:assignment:v1:user-1",
    )
    assert result["uncertain"] is True
    assert result["reason"] == "transport_result_unknown"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_task_notification_rate_limit_is_uncertain_not_retryable(monkeypatch):
    service = DingtalkService(_PushDb())
    monkeypatch.setattr(dingtalk_module, "rate_limit_check", lambda *args, **kwargs: _async_value(False))

    result = await service._send_to_user(
        "user-1", "title", "content", "task_assignment", "task_assignment",
        notification_key="task:1:assignment:v1:user-1",
    )

    assert result["uncertain"] is True
    assert result["reason"] == "duplicate_delivery_state_unknown"


def test_all_dingtalk_http_paths_use_the_shared_budget_service():
    common = Path("app/modules/dingtalk/sync/_common.py").read_text(encoding="utf-8")
    attendance = Path("app/modules/dingtalk/attendance_sync.py").read_text(encoding="utf-8")
    push = Path("app/services/dingtalk.py").read_text(encoding="utf-8")
    assert "consume_daily_dingtalk_budget" in common
    assert "consume_daily_dingtalk_budget" in push
    assert "priority=notification_priority" in push
    assert "post_oapi" in attendance
    assert "await client.post" not in attendance


@pytest.mark.asyncio
async def test_work_notification_requires_every_recipient_to_succeed(monkeypatch):
    service = DingtalkService(db=object())
    monkeypatch.setattr("app.services.dingtalk.settings.DINGTALK_PUSH_ENABLED", True)

    async def fake_send(user_id, *_args, **_kwargs):
        return {"success": user_id == "ok", "user_id": user_id}

    monkeypatch.setattr(service, "_send_to_user", fake_send)
    result = await service.send_work_notification(
        ["ok", "failed"],
        "title",
        "content",
        push_type="task_assignment",
        notification_key="task:42:assignment:1",
    )

    assert result["success"] is False
    assert result["partial"] is True
    assert result["failed_recipient_ids"] == ["failed"]


@pytest.mark.asyncio
async def test_task_notification_key_is_forwarded_to_each_recipient(monkeypatch):
    service = DingtalkService(db=object())
    monkeypatch.setattr("app.services.dingtalk.settings.DINGTALK_PUSH_ENABLED", True)
    seen = []

    async def fake_send(user_id, *_args, **kwargs):
        seen.append((user_id, kwargs["notification_key"]))
        return {"success": True, "user_id": user_id}

    monkeypatch.setattr(service, "_send_to_user", fake_send)
    result = await service.send_work_notification(
        ["u1", "u2"],
        "title",
        "content",
        push_type="task_assignment",
        notification_key="task:42:assignment:2",
    )

    assert result["success"] is True
    assert seen == [
        ("u1", "task:42:assignment:2"),
        ("u2", "task:42:assignment:2"),
    ]
