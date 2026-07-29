from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import finance_v2
from app.api.v1.finance_v2 import router


def test_v2_routes_are_separate_from_legacy_write_paths_during_read_only_gate():
    routes = {(route.path, next(iter(route.methods))) for route in router.routes}

    assert ("/finance-center/v2/books", "GET") in routes
    assert ("/finance-center/v2/books/{book_id}/periods", "GET") in routes
    assert ("/finance-center/v2/books/{book_id}/accounts", "GET") in routes
    assert ("/finance-center/v2/books/{book_id}/write-readiness", "GET") in routes
    assert ("/finance-center/v2/vouchers", "POST") in routes
    assert ("/finance-center/v2/vouchers", "GET") in routes
    assert ("/finance-center/v2/vouchers/{voucher_id}/commands", "POST") in routes
    assert ("/finance-center/v2/history/vouchers", "GET") in routes


@pytest.mark.asyncio
async def test_v2_draft_endpoint_is_fail_closed_when_no_write_gate_is_enabled(monkeypatch):
    class FakeWorkflow:
        def __init__(self, _db):
            pass

        async def create_draft(self, **_kwargs):
            return {"status": "draft"}

    class EmptyGateResult:
        def scalars(self):
            return self

        def all(self):
            return []

    class EmptyGateDb:
        async def execute(self, _statement):
            return EmptyGateResult()

    monkeypatch.setattr(finance_v2, "FinanceV2VoucherWorkflow", FakeWorkflow)

    with pytest.raises(HTTPException) as error:
        await finance_v2.create_voucher_draft(
            finance_v2.VoucherDraftInput(
                book_id=1,
                period_id=1,
                voucher_date=date(2026, 8, 1),
                request_id="draft-command-1",
                entries=[],
            ),
            current_user=SimpleNamespace(id=1, username="finance"),
            db=EmptyGateDb(),
        )

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_v2_command_gate_uses_the_vouchers_book_not_its_identifier(monkeypatch):
    class FakeWorkflow:
        def __init__(self, _db):
            pass

        async def command(self, **_kwargs):
            return {"status": "submitted"}

    gates = [
        SimpleNamespace(scope_type="global", scope_key="*", gate_name="draft_enabled", enabled=True),
        SimpleNamespace(scope_type="book", scope_key="7", gate_name="draft_enabled", enabled=False),
        SimpleNamespace(scope_type="book", scope_key="100", gate_name="draft_enabled", enabled=True),
    ]

    class GateResult:
        def scalars(self):
            return self

        def all(self):
            return gates

    class GateDb:
        async def execute(self, _statement):
            return GateResult()

        async def get(self, _model, voucher_id):
            assert voucher_id == 7
            return SimpleNamespace(book_id=100)

    monkeypatch.setattr(finance_v2, "FinanceV2VoucherWorkflow", FakeWorkflow)

    response = await finance_v2.execute_voucher_command(
        7,
        finance_v2.VoucherCommandInput(action="submit", command_id="submit-route-test-1", expected_version=1),
        current_user=SimpleNamespace(id=1, username="finance"),
        db=GateDb(),
    )

    assert response.data["status"] == "submitted"


@pytest.mark.asyncio
async def test_v2_write_gate_uses_super_admin_role_for_an_administrator(monkeypatch):
    class FakeWorkflow:
        def __init__(self, _db):
            pass

        async def create_draft(self, **_kwargs):
            return {"status": "draft"}

    gates = [
        SimpleNamespace(scope_type="global", scope_key="*", gate_name="draft_enabled", enabled=True),
        SimpleNamespace(scope_type="role", scope_key="finance_manager", gate_name="draft_enabled", enabled=False),
        SimpleNamespace(scope_type="role", scope_key="super_admin", gate_name="draft_enabled", enabled=True),
    ]

    class GateResult:
        def scalars(self):
            return self

        def all(self):
            return gates

    class GateDb:
        async def execute(self, _statement):
            return GateResult()

    monkeypatch.setattr(finance_v2, "FinanceV2VoucherWorkflow", FakeWorkflow)

    response = await finance_v2.create_voucher_draft(
        finance_v2.VoucherDraftInput(
            book_id=1,
            period_id=1,
            voucher_date=date(2026, 8, 1),
            request_id="draft-command-admin",
            entries=[],
        ),
        current_user=SimpleNamespace(id=1, username="admin", is_admin=True),
        db=GateDb(),
    )

    assert response.data["status"] == "draft"


@pytest.mark.asyncio
async def test_v2_post_commits_primary_transaction_before_marking_attempt_success(monkeypatch):
    instances = []

    class FakeWorkflow:
        def __init__(self, _db):
            self.completed_attempt_id = None
            instances.append(self)

        async def command(self, **_kwargs):
            return {"status": "posted", "posting_attempt_id": 42}

        async def mark_posting_attempt_succeeded(self, attempt_id):
            self.completed_attempt_id = attempt_id

    gates = [SimpleNamespace(scope_type="global", scope_key="*", gate_name="post_enabled", enabled=True)]

    class GateResult:
        def scalars(self):
            return self

        def all(self):
            return gates

    class GateDb:
        committed = False

        async def execute(self, _statement):
            return GateResult()

        async def get(self, _model, _voucher_id):
            return SimpleNamespace(book_id=100)

        async def commit(self):
            self.committed = True

    monkeypatch.setattr(finance_v2, "FinanceV2VoucherWorkflow", FakeWorkflow)
    db = GateDb()

    response = await finance_v2.execute_voucher_command(
        7,
        finance_v2.VoucherCommandInput(
            action="post", command_id="post-route-test-1", expected_version=4, reason="人工过账"
        ),
        current_user=SimpleNamespace(id=1, username="poster"),
        db=db,
    )

    assert response.data["status"] == "posted"
    assert db.committed is True
    assert instances[0].completed_attempt_id == 42


@pytest.mark.asyncio
async def test_v2_post_marks_independent_attempt_failed_when_primary_commit_fails(monkeypatch):
    instances = []

    class FakeWorkflow:
        def __init__(self, _db):
            self.failed_attempt_id = None
            instances.append(self)

        async def command(self, **_kwargs):
            return {"status": "posted", "posting_attempt_id": 43}

        async def mark_posting_attempt_failed(self, attempt_id, _error):
            self.failed_attempt_id = attempt_id

    gates = [SimpleNamespace(scope_type="global", scope_key="*", gate_name="post_enabled", enabled=True)]

    class GateResult:
        def scalars(self):
            return self

        def all(self):
            return gates

    class GateDb:
        rolled_back = False

        async def execute(self, _statement):
            return GateResult()

        async def get(self, _model, _voucher_id):
            return SimpleNamespace(book_id=100)

        async def commit(self):
            raise RuntimeError("primary commit failed")

        async def rollback(self):
            self.rolled_back = True

    monkeypatch.setattr(finance_v2, "FinanceV2VoucherWorkflow", FakeWorkflow)
    db = GateDb()

    with pytest.raises(RuntimeError, match="primary commit failed"):
        await finance_v2.execute_voucher_command(
            7,
            finance_v2.VoucherCommandInput(
                action="post", command_id="post-route-test-2", expected_version=4, reason="人工过账"
            ),
            current_user=SimpleNamespace(id=1, username="poster"),
            db=db,
        )

    assert db.rolled_back is True
    assert instances[0].failed_attempt_id == 43
