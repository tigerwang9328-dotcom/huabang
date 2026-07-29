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

    with pytest.raises(OpeningBalanceError, match="immediately precede"):
        await FinanceV2OpeningBalanceService(Db()).assert_current_writes_allowed(book_id=3)
