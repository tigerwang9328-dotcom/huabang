"""Transactional staging, validation, and immutable publication for Finance V2 history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance_v2_history import (
    FinanceV2HistoryBatch,
    FinanceV2HistorySourceLink,
    FinanceV2HistoryStagingVoucher,
    FinanceV2HistoryVoucher,
    FinanceV2HistoryVoucherLine,
)
from app.services.finance_v2.history_domain import HistoryBatchError, HistoryBatchState, transition_history_batch
from app.services.finance_v2.history_import_plan import HistoryPublicationError, plan_history_import
from app.services.finance_v2.kingdee_history_loader import KingdeeHistoryRecord, _source_hash


@dataclass(frozen=True)
class HistoryStageResult:
    batch_id: int | None
    status: str
    new_record_count: int
    idempotent_source_pks: tuple[str, ...]
    conflicts: tuple[tuple[str, str, str], ...]

def _advance(batch: FinanceV2HistoryBatch, action: str) -> None:
    batch.status = transition_history_batch(HistoryBatchState(str(batch.status)), action).status


def _record_payload(record: KingdeeHistoryRecord) -> dict:
    return {
        "source_system": record.source_system,
        "source_database": record.source_database,
        "source_pk": record.source_pk,
        "source_hash": record.source_hash,
        "voucher_no": record.voucher_no,
        "voucher_group": record.voucher_group,
        "voucher_date": record.voucher_date.isoformat(),
        "fiscal_year": record.fiscal_year,
        "fiscal_period": record.fiscal_period,
        "source_status": record.source_status,
        "total_debit": record.total_debit,
        "total_credit": record.total_credit,
        "lines": [
            {
                "source_pk": line.source_pk,
                "line_no": line.line_no,
                "account_code": line.account_code,
                "summary": line.summary,
                "currency_code": line.currency_code,
                "exchange_rate": line.exchange_rate,
                "debit_amount": line.debit_amount,
                "credit_amount": line.credit_amount,
                "raw_dimensions": line.raw_dimensions,
            }
            for line in record.lines
        ],
        "raw_payload": record.raw_payload,
    }


def _validate_staging_payload(payload: object, expected_hash: str) -> list[str]:
    if not isinstance(payload, dict):
        return ["staging payload is not an object"]
    raw_payload = payload.get("raw_payload")
    if not isinstance(raw_payload, dict):
        return ["staging payload has no raw source payload"]
    header = raw_payload.get("header")
    entries = raw_payload.get("entries")
    if not isinstance(header, dict) or not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        return ["staging payload raw source shape is invalid"]
    errors: list[str] = []
    account_codes = raw_payload.get("account_codes")
    if not isinstance(account_codes, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in account_codes.items()):
        errors.append("staging payload account code mapping is invalid")
    elif _source_hash(header, entries, account_codes) != expected_hash:
        errors.append("staging payload source hash does not match raw source")
    lines = payload.get("lines")
    if not isinstance(lines, list) or not lines:
        return [*errors, "staging payload has no transformed lines"]
    try:
        debit = sum(Decimal(str(line.get("debit_amount"))) for line in lines if isinstance(line, dict))
        credit = sum(Decimal(str(line.get("credit_amount"))) for line in lines if isinstance(line, dict))
        expected_debit = Decimal(str(payload.get("total_debit")))
        expected_credit = Decimal(str(payload.get("total_credit")))
    except (InvalidOperation, ValueError, TypeError):
        return [*errors, "staging payload has invalid monetary values"]
    if debit != credit:
        errors.append("staging voucher is not balanced")
    if (debit, credit) != (expected_debit, expected_credit):
        errors.append("staging voucher totals do not match transformed lines")
    return errors


class FinanceV2HistoryImportService:
    """The only Finance V2 service allowed to publish historical facts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def stage(self, *, batch_code: str, source_database: str, records: Sequence[KingdeeHistoryRecord]) -> HistoryStageResult:
        if not records:
            raise HistoryPublicationError("history stage requires at least one record")
        if any(record.source_system != "kingdee" or record.source_database != source_database for record in records):
            raise HistoryPublicationError("history batch mixes source systems or source databases")
        existing_batch = await self.db.scalar(
            select(FinanceV2HistoryBatch).where(FinanceV2HistoryBatch.batch_code == batch_code).with_for_update()
        )
        if existing_batch is not None:
            return HistoryStageResult(
                batch_id=int(existing_batch.id),
                status=str(existing_batch.status),
                new_record_count=0,
                idempotent_source_pks=(),
                conflicts=(),
            )
        source_keys = [record.source_pk for record in records]
        source_rows = (
            await self.db.execute(
                select(FinanceV2HistorySourceLink.source_pk, FinanceV2HistorySourceLink.source_hash).where(
                    FinanceV2HistorySourceLink.source_system == "kingdee",
                    FinanceV2HistorySourceLink.source_database == source_database,
                    FinanceV2HistorySourceLink.source_pk.in_(source_keys),
                )
            )
        ).all()
        plan = plan_history_import(records, {str(source_pk): str(source_hash) for source_pk, source_hash in source_rows})
        if not plan.new_records and not plan.conflicts:
            return HistoryStageResult(None, "idempotent", 0, plan.idempotent_source_pks, ())

        batch = FinanceV2HistoryBatch(
            batch_code=batch_code,
            source_system="kingdee",
            source_database=source_database,
            status="created",
            expected_counts={"vouchers": len(records), "entries": sum(len(record.lines) for record in records)},
            actual_counts={"vouchers": 0, "entries": 0, "idempotent_vouchers": len(plan.idempotent_source_pks)},
            validation_report={},
        )
        self.db.add(batch)
        await self.db.flush()
        if plan.conflicts:
            _advance(batch, "start_loading")
            _advance(batch, "mark_loaded")
            _advance(batch, "start_validation")
            _advance(batch, "conflict")
            batch.validation_report = {
                "status": "conflicted",
                "conflicts": [
                    {"source_pk": source_pk, "existing_hash": existing_hash, "incoming_hash": incoming_hash}
                    for source_pk, existing_hash, incoming_hash in plan.conflicts
                ],
            }
            return HistoryStageResult(int(batch.id), "conflicted", 0, plan.idempotent_source_pks, plan.conflicts)

        _advance(batch, "start_loading")
        for record in plan.new_records:
            self.db.add(
                FinanceV2HistoryStagingVoucher(
                    batch_id=batch.id,
                    source_system=record.source_system,
                    source_database=record.source_database,
                    source_pk=record.source_pk,
                    source_hash=record.source_hash,
                    payload=_record_payload(record),
                    status="loaded",
                )
            )
        # The session factory disables autoflush.  Validation and publication
        # run in this same outer transaction, so make every staged record
        # visible before either method queries the staging table.
        await self.db.flush()
        batch.actual_counts = {
            "vouchers": len(plan.new_records),
            "entries": sum(len(record.lines) for record in plan.new_records),
            "idempotent_vouchers": len(plan.idempotent_source_pks),
        }
        _advance(batch, "mark_loaded")
        return HistoryStageResult(int(batch.id), str(batch.status), len(plan.new_records), plan.idempotent_source_pks, ())

    async def validate(self, batch_id: int) -> dict:
        batch = await self.db.get(FinanceV2HistoryBatch, batch_id, with_for_update=True)
        if batch is None:
            raise HistoryPublicationError("history batch does not exist")
        staged = list(
            (
                await self.db.execute(
                    select(FinanceV2HistoryStagingVoucher)
                    .where(FinanceV2HistoryStagingVoucher.batch_id == batch_id)
                    .order_by(FinanceV2HistoryStagingVoucher.id)
                )
            ).scalars().all()
        )
        if not staged:
            raise HistoryPublicationError("history validation requires at least one staged voucher")
        try:
            _advance(batch, "start_validation")
        except HistoryBatchError as exc:
            raise HistoryPublicationError(str(exc)) from exc
        errors = [
            {"source_pk": row.source_pk, "errors": _validate_staging_payload(row.payload, row.source_hash)}
            for row in staged
        ]
        errors = [item for item in errors if item["errors"]]
        if errors:
            _advance(batch, "fail")
            batch.validation_report = {"status": "failed", "errors": errors}
            return batch.validation_report
        _advance(batch, "mark_validated")
        batch.validation_report = {"status": "validated", "validated_vouchers": len(staged)}
        return batch.validation_report

    async def publish(self, batch_id: int) -> dict:
        batch = await self.db.get(FinanceV2HistoryBatch, batch_id, with_for_update=True)
        if batch is None:
            raise HistoryPublicationError("history batch does not exist")
        if batch.status != "validated":
            raise HistoryPublicationError(f"history batch must be validated before publication, got {batch.status}")
        staged = list(
            (
                await self.db.execute(
                    select(FinanceV2HistoryStagingVoucher)
                    .where(FinanceV2HistoryStagingVoucher.batch_id == batch_id)
                    .order_by(FinanceV2HistoryStagingVoucher.id)
                )
            ).scalars().all()
        )
        if not staged:
            raise HistoryPublicationError("history publication requires at least one staged voucher")
        for row in staged:
            errors = _validate_staging_payload(row.payload, row.source_hash)
            if errors:
                raise HistoryPublicationError(f"refusing invalid staged source {row.source_pk}: {'; '.join(errors)}")
            payload = row.payload
            voucher = FinanceV2HistoryVoucher(
                batch_id=batch.id,
                source_system=str(payload["source_system"]),
                source_database=str(payload["source_database"]),
                source_pk=str(payload["source_pk"]),
                source_hash=str(payload["source_hash"]),
                voucher_no=payload.get("voucher_no"),
                voucher_group=payload.get("voucher_group"),
                voucher_date=date.fromisoformat(str(payload["voucher_date"])),
                fiscal_year=int(payload["fiscal_year"]),
                fiscal_period=int(payload["fiscal_period"]),
                source_status=str(payload["source_status"]),
                total_debit=Decimal(str(payload["total_debit"])),
                total_credit=Decimal(str(payload["total_credit"])),
                is_historical=True,
            )
            self.db.add(voucher)
            await self.db.flush()
            for line in payload["lines"]:
                self.db.add(
                    FinanceV2HistoryVoucherLine(
                        voucher_id=voucher.id,
                        line_no=int(line["line_no"]),
                        source_pk=str(line["source_pk"]),
                        account_code=line.get("account_code"),
                        summary=line.get("summary"),
                        currency_code=str(line["currency_code"]),
                        exchange_rate=Decimal(str(line["exchange_rate"])),
                        debit_amount=Decimal(str(line["debit_amount"])),
                        credit_amount=Decimal(str(line["credit_amount"])),
                        raw_dimensions=dict(line.get("raw_dimensions") or {}),
                    )
                )
            self.db.add(
                FinanceV2HistorySourceLink(
                    batch_id=batch.id,
                    history_voucher_id=voucher.id,
                    source_system=voucher.source_system,
                    source_database=voucher.source_database,
                    source_pk=voucher.source_pk,
                    source_hash=voucher.source_hash,
                )
            )
        _advance(batch, "publish")
        batch.published_at = datetime.now(timezone.utc)
        return {"status": "published", "batch_id": int(batch.id), "published_vouchers": len(staged)}
