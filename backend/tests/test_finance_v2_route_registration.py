from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import finance_v2
from app.api.v1.finance_v2 import router
from app.services.finance_v2.platform_permissions import (
    FINANCE_V2_READ_PERMISSION,
    FINANCE_V2_WRITE_PERMISSION,
)


def test_v2_routes_are_separate_from_legacy_write_paths_during_read_only_gate():
    routes = {(route.path, next(iter(route.methods))) for route in router.routes}

    assert ("/finance-center/v2/books", "GET") in routes
    assert ("/finance-center/v2/books/{book_id}/periods", "GET") in routes
    assert ("/finance-center/v2/books/{book_id}/accounts", "GET") in routes
    assert ("/finance-center/v2/books/{book_id}/write-readiness", "GET") in routes
    assert ("/finance-center/v2/books/{book_id}/periods/{period_id}/close-readiness", "GET") in routes
    assert ("/finance-center/v2/books/{book_id}/periods/{period_id}/commands", "POST") in routes
    assert ("/finance-center/v2/books/{book_id}/periods/{period_id}/trial-balance", "GET") in routes
    assert ("/finance-center/v2/books/{book_id}/periods/{period_id}/ledger-lines", "GET") in routes
    assert ("/finance-center/v2/monitoring/summary", "GET") in routes
    assert ("/finance-center/v2/vouchers", "POST") in routes
    assert ("/finance-center/v2/vouchers", "GET") in routes
    assert ("/finance-center/v2/vouchers/{voucher_id}/commands", "POST") in routes
    assert ("/finance-center/v2/history/vouchers", "GET") in routes
    assert ("/finance-center/v2/history/vouchers/{voucher_id}/lines", "GET") in routes


def test_every_finance_v2_route_uses_the_huabang_platform_permission_dependency():
    expected = {
        ("/finance-center/v2/books", "GET"): FINANCE_V2_READ_PERMISSION,
        ("/finance-center/v2/books/{book_id}/write-readiness", "GET"): FINANCE_V2_READ_PERMISSION,
        ("/finance-center/v2/books/{book_id}/periods", "GET"): FINANCE_V2_READ_PERMISSION,
        ("/finance-center/v2/books/{book_id}/periods/{period_id}/close-readiness", "GET"): FINANCE_V2_READ_PERMISSION,
        ("/finance-center/v2/books/{book_id}/periods/{period_id}/commands", "POST"): FINANCE_V2_WRITE_PERMISSION,
        ("/finance-center/v2/books/{book_id}/periods/{period_id}/trial-balance", "GET"): FINANCE_V2_READ_PERMISSION,
        ("/finance-center/v2/books/{book_id}/periods/{period_id}/ledger-lines", "GET"): FINANCE_V2_READ_PERMISSION,
        ("/finance-center/v2/monitoring/summary", "GET"): FINANCE_V2_READ_PERMISSION,
        ("/finance-center/v2/books/{book_id}/accounts", "GET"): FINANCE_V2_READ_PERMISSION,
        ("/finance-center/v2/vouchers", "GET"): FINANCE_V2_READ_PERMISSION,
        ("/finance-center/v2/history/vouchers", "GET"): FINANCE_V2_READ_PERMISSION,
        ("/finance-center/v2/history/vouchers/{voucher_id}/lines", "GET"): FINANCE_V2_READ_PERMISSION,
        ("/finance-center/v2/vouchers", "POST"): FINANCE_V2_WRITE_PERMISSION,
        ("/finance-center/v2/vouchers/{voucher_id}/commands", "POST"): FINANCE_V2_WRITE_PERMISSION,
    }
    actual = {}
    for route in router.routes:
        for method in route.methods:
            dependency_codes = [
                getattr(dependency.call, "finance_v2_permission", None)
                for dependency in route.dependant.dependencies
            ]
            code = next((value for value in dependency_codes if value), None)
            if code:
                actual[(route.path, method)] = code

    assert actual == expected


@pytest.mark.asyncio
async def test_v2_history_line_endpoint_reads_only_the_published_read_view():
    captured = {}

    class MappingResult:
        def mappings(self):
            return self

        def all(self):
            return [{"voucher_id": 17, "line_no": 1, "historical_marker": True}]

    class ReadOnlyDb:
        async def execute(self, statement, params):
            captured["statement"] = str(statement)
            captured["params"] = params
            return MappingResult()

    response = await finance_v2.list_history_voucher_lines(
        17,
        limit=200,
        current_user=SimpleNamespace(id=1, username="finance"),
        db=ReadOnlyDb(),
    )

    assert response.data == [{"voucher_id": 17, "line_no": 1, "historical_marker": True}]
    assert "fin_read.history_voucher_line" in captured["statement"]
    assert "fin_history.voucher_line" not in captured["statement"]
    assert captured["params"] == {"voucher_id": 17, "limit": 200}


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
