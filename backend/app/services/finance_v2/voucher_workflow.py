"""Database-backed V2 voucher commands with optimistic concurrency."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance_v2 import (
    FinanceV2CommandIdempotency,
    FinanceV2DimensionSet,
    FinanceV2FiscalPeriod,
    FinanceV2OperationEvent,
    FinanceV2Voucher,
    FinanceV2VoucherLine,
)
from app.services.finance_v2.domain import (
    FinanceV2DomainError,
    VoucherCommand,
    VoucherDraft,
    VoucherLineDraft,
    apply_voucher_command,
    canonical_dimension_hash,
)
from app.services.finance_v2.ledger_service import FinanceV2LedgerService
from app.services.finance_v2.posting_attempt_service import FinanceV2PostingAttemptRecorder
from app.services.finance_v2.voucher_number_service import FinanceV2VoucherNumberService


class FinanceV2VoucherWorkflow:
    """The only service allowed to change V2 voucher business state."""

    def __init__(self, db: AsyncSession, *, posting_attempt_recorder: FinanceV2PostingAttemptRecorder | None = None):
        self.db = db
        self._posting_attempt_recorder = posting_attempt_recorder or FinanceV2PostingAttemptRecorder()

    async def create_draft(
        self,
        *,
        book_id: int,
        period_id: int,
        voucher_date: date,
        prepared_by: str,
        request_id: str,
        entries: list[dict],
    ) -> dict:
        period = await self.db.get(FinanceV2FiscalPeriod, period_id)
        if not period or period.book_id != book_id:
            raise FinanceV2DomainError("fiscal period does not belong to the requested book")
        if period.status != "open":
            raise FinanceV2DomainError("fiscal period is not open")
        existing = (
            await self.db.execute(
                select(FinanceV2Voucher).where(
                    FinanceV2Voucher.book_id == book_id,
                    FinanceV2Voucher.request_id == request_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return self._snapshot(existing, idempotent=True)

        voucher = FinanceV2Voucher(
            book_id=book_id,
            period_id=period_id,
            voucher_date=voucher_date,
            prepared_by=prepared_by,
            request_id=request_id,
            status="draft",
        )
        self.db.add(voucher)
        await self.db.flush()
        empty_dimension_set_id = await self._empty_dimension_set_id(book_id)
        for line_no, payload in enumerate(entries, start=1):
            self.db.add(
                FinanceV2VoucherLine(
                    voucher_id=voucher.id,
                    line_no=line_no,
                    account_version_id=payload.get("account_version_id"),
                    dimension_set_id=payload.get("dimension_set_id") or empty_dimension_set_id,
                    summary=payload.get("summary") or "",
                    currency_code=payload.get("currency_code") or "CNY",
                    exchange_rate=Decimal(str(payload.get("exchange_rate", "1"))),
                    debit_amount=Decimal(str(payload.get("debit_amount", "0"))),
                    credit_amount=Decimal(str(payload.get("credit_amount", "0"))),
                )
            )
        await self._event(voucher, prepared_by, "voucher.create", None, {"status": "draft"})
        await self.db.flush()
        return self._snapshot(voucher, idempotent=False)

    async def command(
        self,
        *,
        voucher_id: int,
        action: str,
        actor_id: str,
        expected_version: int,
        reason: str | None,
        command_id: str,
    ) -> dict:
        voucher = (
            await self.db.execute(
                select(FinanceV2Voucher)
                .where(FinanceV2Voucher.id == voucher_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if not voucher:
            raise FinanceV2DomainError("voucher not found")
        request_hash = self.command_payload_hash(
            voucher_id=voucher.id,
            action=action,
            actor_id=actor_id,
            expected_version=expected_version,
            reason=reason,
        )
        existing_command = (
            await self.db.execute(
                select(FinanceV2CommandIdempotency)
                .where(
                    FinanceV2CommandIdempotency.book_id == voucher.book_id,
                    FinanceV2CommandIdempotency.command_name == f"voucher.{action}",
                    FinanceV2CommandIdempotency.idempotency_key == command_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing_command:
            if existing_command.request_hash != request_hash:
                raise FinanceV2DomainError("command id was already used with different parameters")
            return {**dict(existing_command.result_payload), "idempotent": True}
        lines = (
            await self.db.execute(
                select(FinanceV2VoucherLine)
                .where(FinanceV2VoucherLine.voucher_id == voucher_id)
                .order_by(FinanceV2VoucherLine.line_no)
            )
        ).scalars().all()
        domain_lines = [
            VoucherLineDraft(
                account_version_id=str(line.account_version_id or ""),
                summary=line.summary,
                debit=Decimal(line.debit_amount),
                credit=Decimal(line.credit_amount),
            )
            for line in lines
        ]
        before = self._snapshot(voucher)
        after = apply_voucher_command(
            VoucherDraft(
                voucher_id=str(voucher.id),
                status=voucher.status,
                version=voucher.version,
                prepared_by=voucher.prepared_by,
                reviewer_id=voucher.reviewer_id,
                posted_by=voucher.posted_by,
            ),
            VoucherCommand(action, actor_id, expected_version, reason),
            domain_lines,
        )
        posting_attempt_id = None
        if action == "post":
            posting_attempt_id = await self._posting_attempt_recorder.start(
                voucher_id=voucher.id,
                command_id=command_id,
            )
        try:
            values = {
                "status": after.status,
                "version": after.version,
                "reviewer_id": after.reviewer_id,
                "posted_by": after.posted_by,
            }
            if action == "approve":
                values["approved_by"] = actor_id
            reservation = None
            if action == "post":
                reservation = await FinanceV2VoucherNumberService(self.db).reserve(
                    book_id=voucher.book_id,
                    period_id=voucher.period_id,
                    voucher_group=voucher.voucher_group,
                    command_id=command_id,
                    voucher_id=voucher.id,
                )
                values["voucher_no"] = reservation.voucher_no
            result = await self.db.execute(
                update(FinanceV2Voucher)
                .where(FinanceV2Voucher.id == voucher_id, FinanceV2Voucher.version == expected_version)
                .values(**values)
            )
            if result.rowcount != 1:
                raise FinanceV2DomainError("version conflict: voucher changed concurrently")
            for key, value in values.items():
                setattr(voucher, key, value)
            if action == "post":
                await FinanceV2LedgerService().rebuild_period(
                    self.db,
                    book_id=voucher.book_id,
                    period_id=voucher.period_id,
                )
                FinanceV2VoucherNumberService.mark_used(reservation)
            result_payload = self._snapshot(voucher)
            if posting_attempt_id is not None:
                result_payload["posting_attempt_id"] = posting_attempt_id
            self.db.add(
                FinanceV2CommandIdempotency(
                    book_id=voucher.book_id,
                    command_name=f"voucher.{action}",
                    idempotency_key=command_id,
                    request_hash=request_hash,
                    result_payload=result_payload,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await self._event(voucher, actor_id, f"voucher.{action}", command_id, reason, before)
            await self.db.flush()
            return result_payload
        except Exception as error:
            if posting_attempt_id is not None:
                await self._posting_attempt_recorder.mark_failed(
                    posting_attempt_id,
                    error_code=type(error).__name__,
                    error_context={"message": str(error), "voucher_id": voucher_id, "command_id": command_id},
                )
            raise

    async def mark_posting_attempt_succeeded(self, attempt_id: int) -> None:
        """Call only after the primary V2 posting transaction has committed."""

        await self._posting_attempt_recorder.mark_succeeded(attempt_id)

    async def mark_posting_attempt_failed(self, attempt_id: int, error: Exception) -> None:
        """Record a primary-transaction commit failure in the independent attempt session."""

        await self._posting_attempt_recorder.mark_failed(
            attempt_id,
            error_code=type(error).__name__,
            error_context={"message": str(error)},
        )

    async def _empty_dimension_set_id(self, book_id: int) -> int:
        stable_hash = canonical_dimension_hash({})
        row = (
            await self.db.execute(
                select(FinanceV2DimensionSet).where(
                    FinanceV2DimensionSet.book_id == book_id,
                    FinanceV2DimensionSet.stable_hash == stable_hash,
                )
            )
        ).scalar_one_or_none()
        if row:
            return row.id
        row = FinanceV2DimensionSet(book_id=book_id, stable_hash=stable_hash)
        self.db.add(row)
        await self.db.flush()
        return row.id

    async def _event(
        self,
        voucher: FinanceV2Voucher,
        actor_id: str,
        action: str,
        command_id: str,
        reason: str | None,
        before: dict | None,
    ) -> None:
        self.db.add(
            FinanceV2OperationEvent(
                book_id=voucher.book_id,
                voucher_id=voucher.id,
                command_id=command_id,
                actor_id=actor_id,
                action=action,
                reason=reason,
                before_data=before,
                after_data=self._snapshot(voucher),
            )
        )

    @staticmethod
    def _snapshot(voucher: FinanceV2Voucher, *, idempotent: bool = False) -> dict:
        return {
            "voucher_id": voucher.id,
            "book_id": voucher.book_id,
            "period_id": voucher.period_id,
            "voucher_no": voucher.voucher_no,
            "status": voucher.status,
            "version": voucher.version,
            "reviewer_id": voucher.reviewer_id,
            "approved_by": voucher.approved_by,
            "posted_by": voucher.posted_by,
            "idempotent": idempotent,
        }

    @staticmethod
    def command_payload_hash(
        *, voucher_id: int, action: str, actor_id: str, expected_version: int, reason: str | None
    ) -> str:
        payload = json.dumps(
            {
                "voucher_id": voucher_id,
                "action": action,
                "actor_id": actor_id,
                "expected_version": expected_version,
                "reason": reason or "",
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode("utf-8")).hexdigest()
