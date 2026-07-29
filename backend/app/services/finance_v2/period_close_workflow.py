"""Database-backed V2 period close and controlled reopen workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance_v2 import (
    FinanceV2CommandIdempotency,
    FinanceV2FiscalPeriod,
    FinanceV2LedgerBalance,
    FinanceV2OperationEvent,
    FinanceV2Voucher,
)
from app.models.finance_v2_period_close import (
    FinanceV2PeriodCloseApproval,
    FinanceV2PeriodCloseBatch,
    FinanceV2ProfitClosingEvidence,
)
from app.services.finance_v2.domain import FinanceV2DomainError
from app.services.finance_v2.period_close_domain import (
    PeriodCloseCheck,
    PeriodCloseError,
    PeriodState,
    approve_reopen,
    begin_close,
    complete_close,
    next_reopen_approval,
    request_reopen,
)


@dataclass(frozen=True)
class PeriodCloseMetrics:
    unposted_voucher_count: int
    unbalanced_voucher_count: int
    source_exception_count: int
    ledger_difference_count: int
    posted_debit: Decimal
    posted_credit: Decimal
    ledger_debit: Decimal
    ledger_credit: Decimal
    profit_closing_evidence_required: bool = False
    profit_closing_evidence_count: int = 0

    @property
    def profit_closing_evidence_missing_count(self) -> int:
        return int(self.profit_closing_evidence_required and self.profit_closing_evidence_count == 0)

    @property
    def ready(self) -> bool:
        return all(
            value == 0
            for value in (
                self.unposted_voucher_count,
                self.unbalanced_voucher_count,
                self.source_exception_count,
                self.ledger_difference_count,
                self.profit_closing_evidence_missing_count,
            )
        )

    def to_period_check(self) -> PeriodCloseCheck:
        return PeriodCloseCheck(
            unposted_voucher_count=self.unposted_voucher_count,
            unbalanced_voucher_count=self.unbalanced_voucher_count,
            source_exception_count=self.source_exception_count,
            ledger_difference_count=self.ledger_difference_count,
            profit_closing_evidence_missing_count=self.profit_closing_evidence_missing_count,
        )

    def to_report(self) -> dict[str, int | str]:
        return {
            "unposted_voucher_count": self.unposted_voucher_count,
            "unbalanced_voucher_count": self.unbalanced_voucher_count,
            "source_exception_count": self.source_exception_count,
            "ledger_difference_count": self.ledger_difference_count,
            "posted_debit": format(self.posted_debit, "f"),
            "posted_credit": format(self.posted_credit, "f"),
            "ledger_debit": format(self.ledger_debit, "f"),
            "ledger_credit": format(self.ledger_credit, "f"),
            "profit_closing_evidence_required": self.profit_closing_evidence_required,
            "profit_closing_evidence_count": self.profit_closing_evidence_count,
            "profit_closing_evidence_missing_count": self.profit_closing_evidence_missing_count,
            "source_exception_scope": "manual-only V2 current account; source inbox is not enabled in V2.0",
        }


class FinanceV2PeriodCloseWorkflow:
    """The only service allowed to change a V2 fiscal period's closing state."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def readiness(self, *, book_id: int, period_id: int) -> dict:
        period = await self._get_period(book_id=book_id, period_id=period_id)
        metrics = await self._metrics(book_id=book_id, period_id=period_id)
        return {
            "book_id": book_id,
            "period_id": period.id,
            "period_code": period.period_code,
            "status": period.status,
            "version": period.version,
            "ready_to_start_close": metrics.ready and period.status == "open",
            "checks": metrics.to_report(),
        }

    async def command(
        self,
        *,
        book_id: int,
        period_id: int,
        action: str,
        actor_id: str,
        expected_version: int,
        command_id: str,
        reason: str | None,
        voucher_id: int | None = None,
    ) -> dict:
        period = await self._get_period(book_id=book_id, period_id=period_id, lock=True)
        request_hash = self.command_payload_hash(
            book_id=book_id,
            period_id=period_id,
            action=action,
            actor_id=actor_id,
            expected_version=expected_version,
            reason=reason,
            voucher_id=voucher_id,
        )
        existing = (
            await self.db.execute(
                select(FinanceV2CommandIdempotency)
                .where(
                    FinanceV2CommandIdempotency.book_id == book_id,
                    FinanceV2CommandIdempotency.command_name == f"period.{action}",
                    FinanceV2CommandIdempotency.idempotency_key == command_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing:
            if existing.request_hash != request_hash:
                raise FinanceV2DomainError("command id was already used with different parameters")
            return {**dict(existing.result_payload), "idempotent": True}
        if period.version != expected_version:
            raise FinanceV2DomainError("version conflict: fiscal period changed concurrently")

        try:
            if action == "start_close":
                result = await self._start_close(period=period, actor_id=actor_id, expected_version=expected_version, command_id=command_id)
            elif action == "register_profit_closing":
                result = await self._register_profit_closing(
                    period=period,
                    actor_id=actor_id,
                    command_id=command_id,
                    reason=reason or "",
                    voucher_id=voucher_id,
                )
            elif action == "complete_close":
                result = await self._complete_close(period=period, actor_id=actor_id, expected_version=expected_version, command_id=command_id)
            elif action == "request_reopen":
                result = await self._request_reopen(
                    period=period,
                    actor_id=actor_id,
                    expected_version=expected_version,
                    command_id=command_id,
                    reason=reason or "",
                )
            elif action == "approve_reopen":
                result = await self._approve_reopen(
                    period=period,
                    actor_id=actor_id,
                    expected_version=expected_version,
                    command_id=command_id,
                    reason=reason or "",
                )
            else:
                raise FinanceV2DomainError(f"unsupported period command: {action}")
        except PeriodCloseError as error:
            raise FinanceV2DomainError(str(error)) from error

        self.db.add(
            FinanceV2CommandIdempotency(
                book_id=book_id,
                command_name=f"period.{action}",
                idempotency_key=command_id,
                request_hash=request_hash,
                result_payload=result,
                completed_at=datetime.now(timezone.utc),
            )
        )
        await self.db.flush()
        return result

    async def _start_close(
        self, *, period: FinanceV2FiscalPeriod, actor_id: str, expected_version: int, command_id: str
    ) -> dict:
        metrics = await self._metrics(book_id=period.book_id, period_id=period.id)
        begin_close(PeriodState(period.status), metrics.to_period_check())
        run_number = int(
            (
                await self.db.execute(
                    select(func.coalesce(func.max(FinanceV2PeriodCloseBatch.run_number), 0)).where(
                        FinanceV2PeriodCloseBatch.period_id == period.id
                    )
                )
            ).scalar_one()
        ) + 1
        batch = FinanceV2PeriodCloseBatch(
            book_id=period.book_id,
            period_id=period.id,
            run_number=run_number,
            close_kind="year" if period.end_date.month == 12 else "month",
            status="running",
            command_id=command_id,
            check_report=metrics.to_report(),
            started_by=actor_id,
        )
        self.db.add(batch)
        await self.db.flush()
        before = await self._set_period_status(period, expected_version=expected_version, status="closing")
        await self._event(
            period,
            actor_id,
            "period.start_close",
            command_id,
            None,
            {"batch_id": batch.id, "checks": metrics.to_report()},
            before=before,
        )
        return self._snapshot(period, batch=batch, metrics=metrics)

    async def _register_profit_closing(
        self,
        *,
        period: FinanceV2FiscalPeriod,
        actor_id: str,
        command_id: str,
        reason: str,
        voucher_id: int | None,
    ) -> dict:
        if period.status != "open":
            raise FinanceV2DomainError("manual profit-closing evidence can only be registered for an open period")
        if not reason.strip():
            raise FinanceV2DomainError("manual profit-closing evidence reason is required")
        if voucher_id is None:
            raise FinanceV2DomainError("manual profit-closing evidence requires a voucher id")
        voucher = (
            await self.db.execute(
                select(FinanceV2Voucher).where(FinanceV2Voucher.id == voucher_id).with_for_update()
            )
        ).scalar_one_or_none()
        if not voucher or voucher.book_id != period.book_id or voucher.period_id != period.id:
            raise FinanceV2DomainError("profit-closing voucher does not belong to the requested fiscal period")
        if voucher.status != "posted" or voucher.source_system != "manual":
            raise FinanceV2DomainError("profit-closing evidence requires a posted manual voucher")
        if Decimal(voucher.total_debit) <= 0 or Decimal(voucher.total_credit) <= 0:
            raise FinanceV2DomainError("profit-closing voucher must contain non-zero balanced amounts")
        existing_evidence = (
            await self.db.execute(
                select(FinanceV2ProfitClosingEvidence)
                .where(FinanceV2ProfitClosingEvidence.period_id == period.id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing_evidence:
            raise FinanceV2DomainError("manual profit-closing evidence is already registered for fiscal period")
        evidence = FinanceV2ProfitClosingEvidence(
            book_id=period.book_id,
            period_id=period.id,
            voucher_id=voucher.id,
            command_id=command_id,
            confirmed_by=actor_id,
            reason=reason.strip(),
        )
        self.db.add(evidence)
        await self.db.flush()
        await self._event(
            period,
            actor_id,
            "period.register_profit_closing",
            command_id,
            reason.strip(),
            {"evidence_id": evidence.id, "voucher_id": voucher.id},
            before=(period.status, period.version),
            voucher_id=voucher.id,
        )
        return {
            "period_id": period.id,
            "book_id": period.book_id,
            "voucher_id": voucher.id,
            "evidence_id": evidence.id,
            "status": "registered",
        }

    async def _complete_close(
        self, *, period: FinanceV2FiscalPeriod, actor_id: str, expected_version: int, command_id: str
    ) -> dict:
        metrics = await self._metrics(book_id=period.book_id, period_id=period.id)
        metrics.to_period_check().assert_clear()
        complete_close(PeriodState(period.status))
        batch = await self._latest_batch(period_id=period.id, status="running")
        if not batch:
            raise FinanceV2DomainError("no running close batch for fiscal period")
        batch.status = "closed"
        batch.closed_by = actor_id
        batch.closed_at = datetime.now(timezone.utc)
        batch.check_report = metrics.to_report()
        before = await self._set_period_status(period, expected_version=expected_version, status="closed")
        await self._event(
            period,
            actor_id,
            "period.complete_close",
            command_id,
            None,
            {"batch_id": batch.id, "checks": metrics.to_report()},
            before=before,
        )
        return self._snapshot(period, batch=batch, metrics=metrics)

    async def _request_reopen(
        self,
        *,
        period: FinanceV2FiscalPeriod,
        actor_id: str,
        expected_version: int,
        command_id: str,
        reason: str,
    ) -> dict:
        request_reopen(PeriodState(period.status), reason=reason, requester=actor_id)
        batch = await self._latest_batch(period_id=period.id, status="closed")
        if not batch:
            raise FinanceV2DomainError("no closed close batch for fiscal period")
        batch.status = "reopen_requested"
        batch.reopen_requested_by = actor_id
        batch.reopen_reason = reason
        batch.reopen_requested_at = datetime.now(timezone.utc)
        before = await self._set_period_status(period, expected_version=expected_version, status="reopening")
        await self._event(
            period,
            actor_id,
            "period.request_reopen",
            command_id,
            reason,
            {"batch_id": batch.id},
            before=before,
        )
        return self._snapshot(period, batch=batch)

    async def _approve_reopen(
        self,
        *,
        period: FinanceV2FiscalPeriod,
        actor_id: str,
        expected_version: int,
        command_id: str,
        reason: str,
    ) -> dict:
        if not reason.strip():
            raise FinanceV2DomainError("reopen approval reason is required")
        if period.status != "reopening":
            raise FinanceV2DomainError("fiscal period is not awaiting reopen approval")
        batch = await self._latest_batch(period_id=period.id, status="reopen_requested")
        if not batch or not batch.reopen_requested_by:
            raise FinanceV2DomainError("no reopen request awaiting approval")
        approvals = (
            await self.db.execute(
                select(FinanceV2PeriodCloseApproval)
                .where(FinanceV2PeriodCloseApproval.batch_id == batch.id)
                .order_by(FinanceV2PeriodCloseApproval.approval_step)
                .with_for_update()
            )
        ).scalars().all()
        step, reopens_period = next_reopen_approval(
            requester=batch.reopen_requested_by,
            existing_approvers=tuple(item.actor_id for item in approvals),
            actor=actor_id,
        )
        self.db.add(
            FinanceV2PeriodCloseApproval(
                batch_id=batch.id,
                approval_step=step,
                actor_id=actor_id,
                command_id=command_id,
                reason=reason,
            )
        )
        before = (period.status, period.version)
        if reopens_period:
            first_approver = approvals[0].actor_id
            approve_reopen(PeriodState(period.status), first_approver=first_approver, second_approver=actor_id)
            batch.status = "reopened"
            before = await self._set_period_status(period, expected_version=expected_version, status="open")
        await self._event(
            period,
            actor_id,
            "period.approve_reopen",
            command_id,
            reason,
            {"batch_id": batch.id, "approval_step": step, "reopened": reopens_period},
            before=before,
        )
        return {**self._snapshot(period, batch=batch), "approval_step": step, "pending_second_approval": not reopens_period}

    async def _get_period(self, *, book_id: int, period_id: int, lock: bool = False) -> FinanceV2FiscalPeriod:
        statement = select(FinanceV2FiscalPeriod).where(
            FinanceV2FiscalPeriod.id == period_id,
            FinanceV2FiscalPeriod.book_id == book_id,
        )
        if lock:
            statement = statement.with_for_update()
        period = (await self.db.execute(statement)).scalar_one_or_none()
        if not period:
            raise FinanceV2DomainError("fiscal period does not belong to the requested book")
        return period

    async def _latest_batch(self, *, period_id: int, status: str) -> FinanceV2PeriodCloseBatch | None:
        return (
            await self.db.execute(
                select(FinanceV2PeriodCloseBatch)
                .where(
                    FinanceV2PeriodCloseBatch.period_id == period_id,
                    FinanceV2PeriodCloseBatch.status == status,
                )
                .order_by(FinanceV2PeriodCloseBatch.run_number.desc())
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def _metrics(self, *, book_id: int, period_id: int) -> PeriodCloseMetrics:
        unposted_voucher_count = int(
            (
                await self.db.execute(
                    select(func.count())
                    .select_from(FinanceV2Voucher)
                    .where(
                        FinanceV2Voucher.book_id == book_id,
                        FinanceV2Voucher.period_id == period_id,
                        FinanceV2Voucher.status.not_in(("posted", "cancelled")),
                    )
                )
            ).scalar_one()
        )
        unbalanced_voucher_count = int(
            (
                await self.db.execute(
                    select(func.count())
                    .select_from(FinanceV2Voucher)
                    .where(
                        FinanceV2Voucher.book_id == book_id,
                        FinanceV2Voucher.period_id == period_id,
                        FinanceV2Voucher.status == "posted",
                        FinanceV2Voucher.total_debit != FinanceV2Voucher.total_credit,
                    )
                )
            ).scalar_one()
        )
        posted_debit, posted_credit = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(FinanceV2Voucher.total_debit), 0),
                    func.coalesce(func.sum(FinanceV2Voucher.total_credit), 0),
                ).where(
                    FinanceV2Voucher.book_id == book_id,
                    FinanceV2Voucher.period_id == period_id,
                    FinanceV2Voucher.status == "posted",
                )
            )
        ).one()
        ledger_debit, ledger_credit = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(FinanceV2LedgerBalance.period_debit), 0),
                    func.coalesce(func.sum(FinanceV2LedgerBalance.period_credit), 0),
                ).where(
                    FinanceV2LedgerBalance.book_id == book_id,
                    FinanceV2LedgerBalance.period_id == period_id,
                )
            )
        ).one()
        profit_closing_evidence_count = int(
            (
                await self.db.execute(
                    select(func.count())
                    .select_from(FinanceV2ProfitClosingEvidence)
                    .where(
                        FinanceV2ProfitClosingEvidence.book_id == book_id,
                        FinanceV2ProfitClosingEvidence.period_id == period_id,
                    )
                )
            ).scalar_one()
        )
        posted_debit = Decimal(posted_debit)
        posted_credit = Decimal(posted_credit)
        ledger_debit = Decimal(ledger_debit)
        ledger_credit = Decimal(ledger_credit)
        return PeriodCloseMetrics(
            unposted_voucher_count=unposted_voucher_count,
            unbalanced_voucher_count=unbalanced_voucher_count,
            source_exception_count=0,
            ledger_difference_count=int((posted_debit, posted_credit) != (ledger_debit, ledger_credit)),
            posted_debit=posted_debit,
            posted_credit=posted_credit,
            ledger_debit=ledger_debit,
            ledger_credit=ledger_credit,
            profit_closing_evidence_required=posted_debit != 0 or posted_credit != 0,
            profit_closing_evidence_count=profit_closing_evidence_count,
        )

    async def _set_period_status(
        self, period: FinanceV2FiscalPeriod, *, expected_version: int, status: str
    ) -> tuple[str, int]:
        before = (period.status, period.version)
        result = await self.db.execute(
            update(FinanceV2FiscalPeriod)
            .where(FinanceV2FiscalPeriod.id == period.id, FinanceV2FiscalPeriod.version == expected_version)
            .values(status=status, version=expected_version + 1)
        )
        if result.rowcount != 1:
            raise FinanceV2DomainError("version conflict: fiscal period changed concurrently")
        period.status = status
        period.version = expected_version + 1
        return before

    async def _event(
        self,
        period: FinanceV2FiscalPeriod,
        actor_id: str,
        action: str,
        command_id: str,
        reason: str | None,
        after_data: dict,
        *,
        before: tuple[str, int],
        voucher_id: int | None = None,
    ) -> None:
        self.db.add(
            FinanceV2OperationEvent(
                book_id=period.book_id,
                voucher_id=voucher_id,
                command_id=command_id,
                actor_id=actor_id,
                action=action,
                reason=reason,
                before_data={"period_id": period.id, "status": before[0], "version": before[1]},
                after_data={"period_id": period.id, "status": period.status, "version": period.version, **after_data},
            )
        )

    @staticmethod
    def _snapshot(period: FinanceV2FiscalPeriod, *, batch: FinanceV2PeriodCloseBatch, metrics: PeriodCloseMetrics | None = None) -> dict:
        payload = {
            "period_id": period.id,
            "book_id": period.book_id,
            "status": period.status,
            "version": period.version,
            "close_batch_id": batch.id,
            "close_batch_status": batch.status,
            "run_number": batch.run_number,
        }
        if metrics:
            payload["checks"] = metrics.to_report()
        return payload

    @staticmethod
    def command_payload_hash(
        *,
        book_id: int,
        period_id: int,
        action: str,
        actor_id: str,
        expected_version: int,
        reason: str | None,
        voucher_id: int | None = None,
    ) -> str:
        payload = json.dumps(
            {
                "book_id": book_id,
                "period_id": period_id,
                "action": action,
                "actor_id": actor_id,
                "expected_version": expected_version,
                "reason": reason or "",
                "voucher_id": voucher_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode("utf-8")).hexdigest()
