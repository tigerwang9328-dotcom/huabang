"""Locked database allocation for V2 manual-posting voucher numbers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance_v2_operations import FinanceV2VoucherNumberCounter, FinanceV2VoucherNumberReservation
from app.services.finance_v2.domain import FinanceV2DomainError


class FinanceV2VoucherNumberService:
    """Reserve a period-scoped number in the same transaction as manual posting.

    The counter row is created with ``ON CONFLICT DO NOTHING`` and immediately
    locked before incrementing, so concurrent first postings for one scope do
    not issue the same number.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def reserve(
        self,
        *,
        book_id: int,
        period_id: int,
        voucher_group: str,
        command_id: str,
        voucher_id: int,
    ) -> FinanceV2VoucherNumberReservation:
        existing = (
            await self.db.execute(
                select(FinanceV2VoucherNumberReservation)
                .where(FinanceV2VoucherNumberReservation.command_id == command_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing:
            if (
                existing.book_id != book_id
                or existing.period_id != period_id
                or existing.voucher_group != voucher_group
                or existing.voucher_id != voucher_id
            ):
                raise FinanceV2DomainError("command id was already used for a different voucher-number scope")
            return existing

        await self.db.execute(
            pg_insert(FinanceV2VoucherNumberCounter)
            .values(book_id=book_id, period_id=period_id, voucher_group=voucher_group, next_number=1)
            .on_conflict_do_nothing(constraint="uq_fin_current_voucher_number_counter_scope")
        )
        counter = (
            await self.db.execute(
                select(FinanceV2VoucherNumberCounter)
                .where(
                    FinanceV2VoucherNumberCounter.book_id == book_id,
                    FinanceV2VoucherNumberCounter.period_id == period_id,
                    FinanceV2VoucherNumberCounter.voucher_group == voucher_group,
                )
                .with_for_update()
            )
        ).scalar_one()
        number = counter.next_number
        counter.next_number = number + 1
        reservation = FinanceV2VoucherNumberReservation(
            book_id=book_id,
            period_id=period_id,
            voucher_group=voucher_group,
            voucher_no=f"{number:04d}",
            command_id=command_id,
            status="reserved",
            voucher_id=voucher_id,
        )
        self.db.add(reservation)
        await self.db.flush()
        return reservation

    @staticmethod
    def mark_used(reservation: FinanceV2VoucherNumberReservation) -> None:
        reservation.status = "used"
        reservation.finalized_at = datetime.now(timezone.utc)
