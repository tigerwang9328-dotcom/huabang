"""Tests for the Douyin color analytics upload-token rotation endpoint (Task 13)."""

from datetime import datetime, timezone
from pathlib import Path

import pytest


def test_rotate_route_is_registered_with_post_method():
    from app.api.v1.douyin_color_analytics import router

    routes = {(route.path, frozenset(route.methods or [])) for route in router.routes}
    assert (
        "/douyin-color-analytics/accounts/{account_id}/upload-tokens/rotate",
        frozenset({"POST"}),
    ) in routes


def test_rotate_route_requires_admin_permission():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "api"
        / "v1"
        / "douyin_color_analytics.py"
    ).read_text(encoding="utf-8")
    rotate_start = source.index("def rotate_upload_tokens")
    rotate_section = source[rotate_start : rotate_start + 600]
    assert 'require_permission("douyin.admin")' in rotate_section


def test_rotate_route_queries_only_active_tokens():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "api"
        / "v1"
        / "douyin_color_analytics.py"
    ).read_text(encoding="utf-8")
    rotate_start = source.index("def rotate_upload_tokens")
    rotate_section = source[rotate_start : rotate_start + 1200]
    assert (
        'DouyinUploadToken.status == "active"' in rotate_section
        or "DouyinUploadToken.status == 'active'" in rotate_section
    )


@pytest.mark.asyncio
async def test_rotate_revokes_active_tokens_and_issues_new_active_token():
    from app.api.v1.douyin_color_analytics import rotate_upload_tokens

    class _Account:
        def __init__(self, id):
            self.id = id

    class _Token:
        def __init__(self, id, status, prefix):
            self.id = id
            self.account_id = 1
            self.status = status
            self.token_prefix = prefix
            self.token_hash = "hash_placeholder"
            self.created_by = 99
            self.expires_at = datetime.now(timezone.utc)
            self.revoked_by = None
            self.revoked_at = None

    class _User:
        id = 1

    class _Scalars:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

    class _Result:
        def __init__(self, scalars=None, scalar_one_or_none=None):
            self._scalars = scalars or []
            self._scalar_one_or_none = scalar_one_or_none

        def scalars(self):
            return _Scalars(self._scalars)

        def scalar_one_or_none(self):
            return self._scalar_one_or_none

    class _Db:
        def __init__(self, results):
            self._results = list(results)
            self.added = []
            self.flush_count = 0

        async def execute(self, _query):
            return self._results.pop(0)

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            self.flush_count += 1
            if self.added and getattr(self.added[-1], "id", None) is None:
                self.added[-1].id = 999

    active_tokens = [
        _Token(id=10, status="active", prefix="dyup_old_aaa"),
        _Token(id=11, status="active", prefix="dyup_old_bbb"),
    ]
    db = _Db(
        [
            _Result(scalar_one_or_none=_Account(id=1)),
            _Result(scalars=active_tokens),
        ]
    )

    audit_calls = []

    async def _mock_audit(_db, **kwargs):
        audit_calls.append(kwargs)

    import app.api.v1.douyin_color_analytics as mod

    original_audit = mod.write_operation_audit
    mod.write_operation_audit = _mock_audit
    try:
        response = await rotate_upload_tokens(
            account_id=1, request=None, current_user=_User(), db=db
        )
    finally:
        mod.write_operation_audit = original_audit

    # Old active tokens are revoked
    assert all(t.status == "revoked" for t in active_tokens)
    assert all(t.revoked_by == 1 for t in active_tokens)
    assert all(t.revoked_at is not None for t in active_tokens)

    # New token is added with status active
    assert len(db.added) == 1
    new_token = db.added[0]
    assert new_token.status == "active"
    assert new_token.account_id == 1
    assert new_token.created_by == 1

    # Response carries the new token and revoked count
    assert response.code == 200
    assert "upload_token" in response.data
    assert response.data["revoked_count"] == 2

    # Audit log was written
    assert len(audit_calls) == 1
    assert audit_calls[0]["action"] == "rotate_upload_token"
    assert audit_calls[0]["module"] == "douyin_color_analytics"
    assert audit_calls[0]["target_type"] == "douyin_upload_token"


@pytest.mark.asyncio
async def test_rotate_returns_404_when_account_not_found():
    from fastapi import HTTPException

    from app.api.v1.douyin_color_analytics import rotate_upload_tokens

    class _Result:
        def scalar_one_or_none(self):
            return None

    class _Db:
        async def execute(self, _query):
            return _Result()

        def add(self, _obj):
            pass

        async def flush(self):
            pass

    with pytest.raises(HTTPException) as exc:
        await rotate_upload_tokens(
            account_id=999, request=None, current_user=None, db=_Db()
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "account_not_found"


@pytest.mark.asyncio
async def test_rotate_writes_audit_with_before_and_after_data(monkeypatch):
    from app.api.v1.douyin_color_analytics import rotate_upload_tokens

    class _Account:
        id = 1

    class _Token:
        def __init__(self, prefix):
            self.id = 10
            self.account_id = 1
            self.status = "active"
            self.token_prefix = prefix
            self.token_hash = "h"
            self.created_by = 99
            self.expires_at = datetime.now(timezone.utc)
            self.revoked_by = None
            self.revoked_at = None

    class _User:
        id = 1

    class _Scalars:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

    class _Result:
        def __init__(self, scalars=None, scalar_one_or_none=None):
            self._scalars = scalars or []
            self._scalar_one_or_none = scalar_one_or_none

        def scalars(self):
            return _Scalars(self._scalars)

        def scalar_one_or_none(self):
            return self._scalar_one_or_none

    class _Db:
        def __init__(self):
            self._call = 0
            self.added = []

        async def execute(self, _query):
            self._call += 1
            if self._call == 1:
                return _Result(scalar_one_or_none=_Account())
            return _Result(scalars=[_Token(prefix="dyup_old_xxx")])

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            if self.added and getattr(self.added[-1], "id", None) is None:
                self.added[-1].id = 42

    audit_calls = []

    async def _mock_audit(_db, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(
        "app.api.v1.douyin_color_analytics.write_operation_audit", _mock_audit
    )

    await rotate_upload_tokens(
        account_id=1, request=None, current_user=_User(), db=_Db()
    )

    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["action"] == "rotate_upload_token"
    assert "before_data" in call
    assert "after_data" in call
    assert "revoked_token_prefixes" in call["before_data"]
    assert "new_token_prefix" in call["after_data"]
