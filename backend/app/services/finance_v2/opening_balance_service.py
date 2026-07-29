"""Runtime enforcement for the Finance V2.0 opening-balance cutover boundary."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance_v2 import FinanceV2AccountingBook
from app.models.finance_v2_opening import FinanceV2OpeningBalanceBatch
from app.services.finance_v2.opening_balance_domain import (
    OpeningBalanceError,
    OpeningBalanceState,
    assert_current_writes_allowed,
)


class FinanceV2OpeningBalanceService:
    """Read the immutable final opening boundary before enabling current writes.

    This deliberately does not create or edit opening balances.  Their real
    preparation remains a controlled cutover operation; this service only
    makes it impossible for a separately enabled write Gate to bypass that
    prerequisite.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def assert_current_writes_allowed(self, *, book_id: int) -> None:
        book = await self.db.get(FinanceV2AccountingBook, book_id)
        if not book or not book.current_book_go_live_date:
            raise OpeningBalanceError("final locked opening balance is required before current writes")

        batch = (
            await self.db.execute(
                select(FinanceV2OpeningBalanceBatch).where(
                    FinanceV2OpeningBalanceBatch.book_id == book_id,
                    FinanceV2OpeningBalanceBatch.batch_kind == "final",
                    FinanceV2OpeningBalanceBatch.go_live_date == book.current_book_go_live_date,
                )
            )
        ).scalar_one_or_none()
        if not batch:
            raise OpeningBalanceError("final locked opening balance is required before current writes")

        if batch.history_coverage_end_date + timedelta(days=1) != batch.go_live_date:
            raise OpeningBalanceError("history coverage endpoint must immediately precede current go-live date")

        assert_current_writes_allowed(
            OpeningBalanceState(
                batch_kind=batch.batch_kind,
                status=batch.status,
                coverage_continuous=bool(batch.coverage_continuous),
                approved_by=batch.approved_by,
            )
        )
