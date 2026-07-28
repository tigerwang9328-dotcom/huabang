"""Ledger read-model rebuild; only posted V2 vouchers contribute balances."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class LedgerLine:
    account_version_id: int
    dimension_set_id: int
    currency_code: str
    debit: Decimal
    credit: Decimal


@dataclass
class PeriodBalance:
    period_debit: Decimal = Decimal("0")
    period_credit: Decimal = Decimal("0")


def aggregate_period_balances(lines: list[LedgerLine]) -> dict[tuple[int, int, str], PeriodBalance]:
    """Aggregate one period deterministically; opening/closing are handled by the close service."""

    balances: dict[tuple[int, int, str], PeriodBalance] = {}
    for line in lines:
        key = (line.account_version_id, line.dimension_set_id, line.currency_code)
        balance = balances.setdefault(key, PeriodBalance())
        balance.period_debit += Decimal(line.debit)
        balance.period_credit += Decimal(line.credit)
    return balances


class FinanceV2LedgerService:
    async def rebuild_period(self, db: "AsyncSession", *, book_id: int, period_id: int) -> None:
        # Delayed imports keep the pure aggregation logic runnable without a
        # configured application database in unit tests.
        from sqlalchemy import delete, select

        from app.models.finance_v2 import FinanceV2LedgerBalance, FinanceV2Voucher, FinanceV2VoucherLine

        rows = (
            await db.execute(
                select(FinanceV2VoucherLine)
                .join(FinanceV2Voucher, FinanceV2Voucher.id == FinanceV2VoucherLine.voucher_id)
                .where(
                    FinanceV2Voucher.book_id == book_id,
                    FinanceV2Voucher.period_id == period_id,
                    FinanceV2Voucher.status == "posted",
                )
            )
        ).scalars().all()
        lines = [
            LedgerLine(
                account_version_id=line.account_version_id,
                dimension_set_id=line.dimension_set_id,
                currency_code=line.currency_code,
                debit=Decimal(line.debit_amount),
                credit=Decimal(line.credit_amount),
            )
            for line in rows
        ]
        balances = aggregate_period_balances(lines)
        await db.execute(
            delete(FinanceV2LedgerBalance).where(
                FinanceV2LedgerBalance.book_id == book_id,
                FinanceV2LedgerBalance.period_id == period_id,
            )
        )
        for (account_version_id, dimension_set_id, currency_code), amount in balances.items():
            db.add(
                FinanceV2LedgerBalance(
                    book_id=book_id,
                    period_id=period_id,
                    account_version_id=account_version_id,
                    dimension_set_id=dimension_set_id,
                    currency_code=currency_code,
                    period_debit=amount.period_debit,
                    period_credit=amount.period_credit,
                    closing_debit=amount.period_debit,
                    closing_credit=amount.period_credit,
                )
            )
        await db.flush()
