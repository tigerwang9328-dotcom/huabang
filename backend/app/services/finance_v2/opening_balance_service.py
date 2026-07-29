"""Runtime enforcement for the Finance V2.0 opening-balance cutover boundary."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance_v2 import FinanceV2AccountingBook, FinanceV2CommandIdempotency, FinanceV2OperationEvent
from app.models.finance_v2_opening import FinanceV2CoverageGap, FinanceV2OpeningBalanceApproval, FinanceV2OpeningBalanceBatch, FinanceV2OpeningBalanceLine
from app.services.finance_v2.opening_balance_domain import (
    OpeningBalanceError,
    OpeningBalanceLine,
    OpeningBalanceState,
    approve_opening_balance,
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

    async def create_batch(
        self,
        *,
        book_id: int,
        batch_kind: str,
        history_coverage_end_date,
        go_live_date,
        coverage_continuous: bool,
        actor_id: str,
        command_id: str,
        lines: list[dict],
    ) -> dict:
        """Create a non-operative provisional/final opening-balance draft.

        Draft creation does not change the accounting book's go-live boundary;
        only a later, controlled final-lock command may do that.  This keeps
        rehearsal data observable without making it accounting-effective.
        """

        if batch_kind not in {"provisional", "final"}:
            raise OpeningBalanceError("opening balance batch kind is invalid")
        if not actor_id.strip() or not command_id.strip():
            raise OpeningBalanceError("opening balance actor and command id are required")
        if history_coverage_end_date >= go_live_date:
            raise OpeningBalanceError("opening balance go-live date must be after history coverage")
        if not lines:
            raise OpeningBalanceError("opening balance has no lines")
        self._validate_draft_lines(lines)
        book = await self.db.get(FinanceV2AccountingBook, book_id)
        if not book:
            raise OpeningBalanceError("opening balance book was not found")

        request_hash = self._payload_hash(
            {
                "book_id": book_id,
                "batch_kind": batch_kind,
                "history_coverage_end_date": str(history_coverage_end_date),
                "go_live_date": str(go_live_date),
                "coverage_continuous": bool(coverage_continuous),
                "actor_id": actor_id,
                "lines": lines,
            }
        )
        existing_command = (
            await self.db.execute(
                select(FinanceV2CommandIdempotency).where(
                    FinanceV2CommandIdempotency.book_id == book_id,
                    FinanceV2CommandIdempotency.command_name == "opening.create",
                    FinanceV2CommandIdempotency.idempotency_key == command_id,
                )
            )
        ).scalar_one_or_none()
        if existing_command:
            if existing_command.request_hash != request_hash:
                raise OpeningBalanceError("opening balance command id was already used with different parameters")
            return {**dict(existing_command.result_payload), "idempotent": True}

        batch = FinanceV2OpeningBalanceBatch(
            book_id=book_id,
            batch_kind=batch_kind,
            status="draft",
            history_coverage_end_date=history_coverage_end_date,
            go_live_date=go_live_date,
            coverage_continuous=coverage_continuous,
        )
        self.db.add(batch)
        await self.db.flush()
        for payload in lines:
            source_system = str(payload.get("source_system") or "").strip()
            if not source_system:
                raise OpeningBalanceError("opening balance source is required")
            self.db.add(
                FinanceV2OpeningBalanceLine(
                    batch_id=batch.id,
                    account_version_id=payload.get("account_version_id"),
                    dimension_set_id=payload.get("dimension_set_id"),
                    currency_code=payload.get("currency_code") or "CNY",
                    debit_amount=payload.get("debit_amount", 0),
                    credit_amount=payload.get("credit_amount", 0),
                    source_system=source_system,
                    source_reference=payload.get("source_reference"),
                )
            )
        result = {"batch_id": batch.id, "book_id": book_id, "batch_kind": batch_kind, "status": "draft"}
        self.db.add(
            FinanceV2CommandIdempotency(
                book_id=book_id,
                command_name="opening.create",
                idempotency_key=command_id,
                request_hash=request_hash,
                result_payload=result,
            )
        )
        self.db.add(
            FinanceV2OperationEvent(
                book_id=book_id,
                command_id=command_id,
                actor_id=actor_id,
                action="opening.create",
                before_data={"status": "new"},
                after_data={"batch_id": batch.id, "status": "draft", "batch_kind": batch_kind},
            )
        )
        await self.db.flush()
        return result

    async def lock_batch(
        self,
        *,
        book_id: int,
        batch_id: int,
        actor_id: str,
        expected_version: int,
        command_id: str,
        reason: str | None,
    ) -> dict:
        book = await self.db.get(FinanceV2AccountingBook, book_id)
        if not book:
            raise OpeningBalanceError("opening balance book was not found")
        batch = (
            await self.db.execute(
                select(FinanceV2OpeningBalanceBatch)
                .where(FinanceV2OpeningBalanceBatch.id == batch_id, FinanceV2OpeningBalanceBatch.book_id == book_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if not batch:
            raise OpeningBalanceError("opening balance batch was not found")
        if batch.version != expected_version:
            raise OpeningBalanceError("version conflict: opening balance batch changed concurrently")
        request_hash = self._payload_hash({"batch_id": batch_id, "actor_id": actor_id, "expected_version": expected_version, "reason": reason})
        existing = (
            await self.db.execute(
                select(FinanceV2CommandIdempotency).where(
                    FinanceV2CommandIdempotency.book_id == book_id,
                    FinanceV2CommandIdempotency.command_name == "opening.lock",
                    FinanceV2CommandIdempotency.idempotency_key == command_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            if existing.request_hash != request_hash:
                raise OpeningBalanceError("opening balance command id was already used with different parameters")
            return {**dict(existing.result_payload), "idempotent": True}
        rows = (
            await self.db.execute(
                select(FinanceV2OpeningBalanceLine)
                .where(FinanceV2OpeningBalanceLine.batch_id == batch_id)
                .order_by(FinanceV2OpeningBalanceLine.id)
            )
        ).scalars().all()
        approved = approve_opening_balance(
            OpeningBalanceState(batch.batch_kind, batch.status, bool(batch.coverage_continuous)),
            [OpeningBalanceLine(str(row.account_version_id), str(row.dimension_set_id), row.currency_code, Decimal(row.debit_amount), Decimal(row.credit_amount), row.source_system) for row in rows],
            approver=actor_id,
        )
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(FinanceV2OpeningBalanceBatch)
            .where(FinanceV2OpeningBalanceBatch.id == batch_id, FinanceV2OpeningBalanceBatch.version == expected_version)
            .values(status=approved.status, approved_by=actor_id, approved_at=now, locked_at=now, version=expected_version + 1)
        )
        if result.rowcount != 1:
            raise OpeningBalanceError("version conflict: opening balance batch changed concurrently")
        batch.status, batch.approved_by, batch.version = approved.status, actor_id, expected_version + 1
        if batch.batch_kind == "final":
            book.history_coverage_end_date = batch.history_coverage_end_date
            book.current_book_go_live_date = batch.go_live_date
            book.formal_report_blocked = not bool(batch.coverage_continuous)
        payload = {"batch_id": batch_id, "book_id": book_id, "status": approved.status, "version": batch.version}
        self.db.add(FinanceV2OpeningBalanceApproval(batch_id=batch_id, actor_id=actor_id, command_id=command_id, reason=reason))
        self.db.add(FinanceV2CommandIdempotency(book_id=book_id, command_name="opening.lock", idempotency_key=command_id, request_hash=request_hash, result_payload=payload, completed_at=now))
        self.db.add(FinanceV2OperationEvent(book_id=book_id, command_id=command_id, actor_id=actor_id, action="opening.lock", reason=reason, before_data={"status": "validated", "version": expected_version}, after_data=payload))
        await self.db.flush()
        return payload

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

        coverage_gap_approved = False
        if batch.history_coverage_end_date + timedelta(days=1) != batch.go_live_date:
            coverage_gap_id = getattr(batch, "coverage_gap_id", None)
            if not coverage_gap_id:
                raise OpeningBalanceError("history coverage gap is not approved for the current go-live boundary")
            gap = await self.db.get(FinanceV2CoverageGap, coverage_gap_id)
            expected_start = batch.history_coverage_end_date + timedelta(days=1)
            expected_end = batch.go_live_date - timedelta(days=1)
            coverage_gap_approved = bool(
                gap
                and gap.status == "approved"
                and gap.gap_start_date == expected_start
                and gap.gap_end_date == expected_end
            )
            if not coverage_gap_approved:
                raise OpeningBalanceError("history coverage gap is not approved for the current go-live boundary")

        assert_current_writes_allowed(
            OpeningBalanceState(
                batch_kind=batch.batch_kind,
                status=batch.status,
                coverage_continuous=bool(batch.coverage_continuous),
                approved_by=batch.approved_by,
                coverage_gap_approved=coverage_gap_approved,
                formal_report_blocked=bool(getattr(book, "formal_report_blocked", False)),
            )
        )

    @staticmethod
    def _payload_hash(payload: dict) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_draft_lines(lines: list[dict]) -> None:
        for payload in lines:
            if not payload.get("account_version_id") or not payload.get("dimension_set_id"):
                raise OpeningBalanceError("opening balance line account and dimension are required")
            debit = Decimal(str(payload.get("debit_amount", 0)))
            credit = Decimal(str(payload.get("credit_amount", 0)))
            if debit < 0 or credit < 0 or (debit > 0 and credit > 0):
                raise OpeningBalanceError("opening balance line must have one nonnegative debit or credit amount")
            if not str(payload.get("source_system") or "").strip():
                raise OpeningBalanceError("opening balance source is required")
