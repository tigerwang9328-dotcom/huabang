from datetime import date
from types import SimpleNamespace

import pytest

from app.services.finance_v2.opening_balance_domain import OpeningBalanceError
from app.services.finance_v2.opening_balance_service import FinanceV2OpeningBalanceService


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


@pytest.mark.asyncio
async def test_final_locked_opening_must_match_the_book_go_live_boundary():
    book = SimpleNamespace(current_book_go_live_date=date(2026, 8, 1))
    batch = SimpleNamespace(
        batch_kind="final",
        status="locked",
        coverage_continuous=True,
        approved_by="finance-manager",
        history_coverage_end_date=date(2026, 7, 31),
        go_live_date=date(2026, 8, 1),
    )

    class Db:
        async def get(self, _model, book_id):
            assert book_id == 3
            return book

        async def execute(self, _statement):
            return _Result(batch)

    await FinanceV2OpeningBalanceService(Db()).assert_current_writes_allowed(book_id=3)


@pytest.mark.asyncio
async def test_final_opening_with_a_date_gap_cannot_enable_current_writes():
    book = SimpleNamespace(current_book_go_live_date=date(2026, 8, 2))
    batch = SimpleNamespace(
        batch_kind="final",
        status="locked",
        coverage_continuous=True,
        approved_by="finance-manager",
        history_coverage_end_date=date(2026, 7, 31),
        go_live_date=date(2026, 8, 2),
    )

    class Db:
        async def get(self, _model, _book_id):
            return book

        async def execute(self, _statement):
            return _Result(batch)

    with pytest.raises(OpeningBalanceError, match="gap is not approved"):
        await FinanceV2OpeningBalanceService(Db()).assert_current_writes_allowed(book_id=3)


@pytest.mark.asyncio
async def test_approved_coverage_gap_allows_current_writes_only_when_formal_reports_are_blocked():
    book = SimpleNamespace(current_book_go_live_date=date(2026, 8, 2), formal_report_blocked=True)
    batch = SimpleNamespace(
        batch_kind="final",
        status="locked",
        coverage_continuous=False,
        coverage_gap_id=9,
        approved_by="finance-manager",
        history_coverage_end_date=date(2026, 7, 30),
        go_live_date=date(2026, 8, 2),
    )
    gap = SimpleNamespace(
        status="approved",
        gap_start_date=date(2026, 7, 31),
        gap_end_date=date(2026, 8, 1),
    )

    class Db:
        async def get(self, _model, item_id):
            return book if item_id == 3 else gap

        async def execute(self, _statement):
            return _Result(batch)

    await FinanceV2OpeningBalanceService(Db()).assert_current_writes_allowed(book_id=3)


@pytest.mark.asyncio
async def test_provisional_opening_batch_records_source_lines_without_enabling_current_writes():
    book = SimpleNamespace(id=3, current_book_go_live_date=None)

    class Db:
        def __init__(self):
            self.added = []

        async def get(self, _model, book_id):
            assert book_id == 3
            return book

        async def execute(self, _statement):
            return _Result(None)

        def add(self, item):
            if not getattr(item, "id", None):
                item.id = len(self.added) + 1
            self.added.append(item)

        async def flush(self):
            pass

    db = Db()
    result = await FinanceV2OpeningBalanceService(db).create_batch(
        book_id=3,
        batch_kind="provisional",
        history_coverage_end_date=date(2026, 7, 31),
        go_live_date=date(2026, 8, 1),
        coverage_continuous=True,
        actor_id="finance-manager",
        command_id="opening-provisional-001",
        lines=[
            {
                "account_version_id": 10,
                "dimension_set_id": 20,
                "currency_code": "CNY",
                "debit_amount": "100.00",
                "credit_amount": "0",
                "source_system": "kingdee",
                "source_reference": "balance:1001",
            },
            {
                "account_version_id": 30,
                "dimension_set_id": 20,
                "currency_code": "CNY",
                "debit_amount": "0",
                "credit_amount": "100.00",
                "source_system": "kingdee",
                "source_reference": "balance:3001",
            },
        ],
    )

    assert result == {"batch_id": 1, "book_id": 3, "batch_kind": "provisional", "status": "draft"}
    assert [item.source_system for item in db.added if hasattr(item, "source_system")] == ["kingdee", "kingdee"]


@pytest.mark.asyncio
async def test_opening_draft_rejects_incomplete_or_double_sided_lines_before_persistence():
    class Db:
        async def get(self, _model, _book_id):
            return SimpleNamespace(id=3)

        async def execute(self, _statement):
            raise AssertionError("invalid draft must not query idempotency or persist")

    with pytest.raises(OpeningBalanceError, match="account and dimension"):
        await FinanceV2OpeningBalanceService(Db()).create_batch(
            book_id=3,
            batch_kind="provisional",
            history_coverage_end_date=date(2026, 7, 31),
            go_live_date=date(2026, 8, 1),
            coverage_continuous=True,
            actor_id="finance-manager",
            command_id="opening-provisional-invalid-001",
            lines=[
                {
                    "account_version_id": None,
                    "dimension_set_id": 20,
                    "debit_amount": "10",
                    "credit_amount": "10",
                    "source_system": "kingdee",
                }
            ],
        )


@pytest.mark.asyncio
async def test_locking_a_final_opening_updates_book_boundary_and_records_approval():
    book = SimpleNamespace(id=3, formal_report_blocked=True)
    batch = SimpleNamespace(
        id=8,
        book_id=3,
        batch_kind="final",
        status="validated",
        version=1,
        coverage_continuous=True,
        coverage_gap_id=None,
        history_coverage_end_date=date(2026, 7, 31),
        go_live_date=date(2026, 8, 1),
        approved_by=None,
    )
    lines = [
        SimpleNamespace(account_version_id=10, dimension_set_id=20, currency_code="CNY", debit_amount="100", credit_amount="0", source_system="kingdee"),
        SimpleNamespace(account_version_id=30, dimension_set_id=20, currency_code="CNY", debit_amount="0", credit_amount="100", source_system="kingdee"),
    ]

    class Result:
        def __init__(self, value=None, *, rowcount=None):
            self.value = value
            self.rowcount = rowcount

        def scalar_one_or_none(self):
            return self.value

        def scalars(self):
            return self

        def all(self):
            return self.value

    class Db:
        def __init__(self):
            self.calls = 0
            self.added = []

        async def get(self, _model, book_id):
            assert book_id == 3
            return book

        async def execute(self, _statement):
            self.calls += 1
            return [Result(batch), Result(None), Result(lines), Result(rowcount=1)][self.calls - 1]

        def add(self, item):
            self.added.append(item)

        async def flush(self):
            pass

    db = Db()
    result = await FinanceV2OpeningBalanceService(db).lock_batch(
        book_id=3, batch_id=8, actor_id="finance-manager", expected_version=1, command_id="opening-lock-001", reason="期初核对完成"
    )

    assert result["status"] == "locked"
    assert book.current_book_go_live_date == date(2026, 8, 1)
    assert any(type(item).__name__ == "FinanceV2OpeningBalanceApproval" for item in db.added)
