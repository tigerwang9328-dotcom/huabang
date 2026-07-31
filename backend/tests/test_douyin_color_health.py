"""Tests for the Douyin color analytics health endpoint (Task 11)."""

from pathlib import Path

import pytest


def test_health_route_is_registered_with_get_method():
    from app.api.v1.douyin_color_analytics import router

    routes = {(route.path, frozenset(route.methods or [])) for route in router.routes}
    assert ("/douyin-color-analytics/health", frozenset({"GET"})) in routes


def test_health_route_requires_admin_or_operator_permission():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "api"
        / "v1"
        / "douyin_color_analytics.py"
    ).read_text(encoding="utf-8")
    health_start = source.index("def get_health")
    health_section = source[health_start : health_start + 800]
    assert "douyin.admin" in health_section
    assert "douyin.operator" in health_section


@pytest.mark.asyncio
async def test_health_returns_collector_status_queue_capacity_and_feature_flags():
    from app.api.v1.douyin_color_analytics import get_health

    class _Collector:
        def __init__(self, account_id, current_status, queued_batch_count, queued_bytes):
            self.account_id = account_id
            self.current_status = current_status
            self.queued_batch_count = queued_batch_count
            self.queued_bytes = queued_bytes

    class _Scalars:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

    class _Result:
        def __init__(self, scalars=None, scalar=None):
            self._scalars = scalars or []
            self._scalar = scalar

        def scalars(self):
            return _Scalars(self._scalars)

        def scalar(self):
            return self._scalar

    class _Db:
        def __init__(self, collectors, queued_count):
            self._call = 0
            self._collectors = collectors
            self._queued_count = queued_count

        async def execute(self, _query):
            self._call += 1
            if self._call == 1:
                return _Result(scalars=self._collectors)
            return _Result(scalar=self._queued_count)

        def add(self, _obj):
            pass

        async def flush(self):
            pass

    collectors = [
        _Collector(
            account_id=1,
            current_status="online_active",
            queued_batch_count=2,
            queued_bytes=1024,
        ),
        _Collector(
            account_id=2,
            current_status="offline_expected",
            queued_batch_count=0,
            queued_bytes=0,
        ),
    ]
    db = _Db(collectors, queued_count=5)

    response = await get_health(request=None, current_user=None, db=db)

    assert response.code == 200
    data = response.data
    assert "collector_status" in data
    assert "queue_capacity" in data
    assert "feature_flags" in data
    assert len(data["collector_status"]) == 2
    assert data["collector_status"][0]["current_status"] == "online_active"
    assert data["collector_status"][0]["queued_batch_count"] == 2
    assert data["queue_capacity"]["queued_jobs"] == 5


@pytest.mark.asyncio
async def test_health_returns_empty_lists_when_no_collectors():
    from app.api.v1.douyin_color_analytics import get_health

    class _Scalars:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

    class _Result:
        def __init__(self, scalars=None, scalar=None):
            self._scalars = scalars or []
            self._scalar = scalar

        def scalars(self):
            return _Scalars(self._scalars)

        def scalar(self):
            return self._scalar

    class _Db:
        def __init__(self):
            self._call = 0

        async def execute(self, _query):
            self._call += 1
            if self._call == 1:
                return _Result(scalars=[])
            return _Result(scalar=0)

        def add(self, _obj):
            pass

        async def flush(self):
            pass

    response = await get_health(request=None, current_user=None, db=_Db())
    assert response.code == 200
    assert response.data["collector_status"] == []
    assert response.data["queue_capacity"]["queued_jobs"] == 0
    assert isinstance(response.data["feature_flags"], dict)
