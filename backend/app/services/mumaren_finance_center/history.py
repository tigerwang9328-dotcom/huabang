"""Kingdee snapshot import for the isolated Mumaren finance history area.

The importer accepts an explicit JSON manifest only.  It never opens a
Kingdee/ODS/DWD connection and only inserts records into the new
``finance_center_mumaren`` history tables when the caller explicitly requests
execution.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mumaren_finance_center import (
    FinanceCenterMumarenHistoryImportBatch,
    FinanceCenterMumarenHistoryVoucher,
    FinanceCenterMumarenHistoryVoucherLine,
)


class HistoryImportError(ValueError):
    """The supplied immutable history manifest is unsafe to import."""


@dataclass(frozen=True)
class HistoryLinePlan:
    source_system: str
    source_key: str
    line_no: int
    account_code: str | None
    account_name: str | None
    summary: str | None
    debit_amount: str
    credit_amount: str


@dataclass(frozen=True)
class HistoryVoucherPlan:
    source_system: str
    source_key: str
    record_type: str
    is_readonly: bool
    voucher_no: str
    voucher_date: date
    summary: str | None
    lines: tuple[HistoryLinePlan, ...]
    source_payload: dict[str, Any]


@dataclass(frozen=True)
class HistoryImportPlan:
    source_system: str
    source_batch_key: str
    source_checksum: str
    vouchers: tuple[HistoryVoucherPlan, ...]

    @property
    def record_count(self) -> int:
        return len(self.vouchers)


@dataclass(frozen=True)
class HistoryImportResult:
    mode: str
    source_batch_key: str
    record_count: int
    inserted_vouchers: int
    skipped_vouchers: int


_MONEY_QUANTUM = Decimal("0.01")


def _required_string(value: Any, field: str, context: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise HistoryImportError(f"{context}: 缺少 {field}")
    return text


def _optional_string(value: Any) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


def _amount(value: Any, field: str, context: str) -> str:
    try:
        amount = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, ValueError) as exc:
        raise HistoryImportError(f"{context}: {field} 金额非法") from exc
    if not amount.is_finite() or amount < 0 or amount.quantize(_MONEY_QUANTUM) != amount:
        raise HistoryImportError(f"{context}: {field} 必须是非负且最多两位小数")
    return f"{amount:.2f}"


def _line_from_payload(payload: Any, context: str) -> HistoryLinePlan:
    if not isinstance(payload, dict):
        raise HistoryImportError(f"{context}: 分录必须是对象")
    source_key = _required_string(payload.get("source_key"), "source_key", context)
    try:
        line_no = int(payload.get("line_no"))
    except (TypeError, ValueError) as exc:
        raise HistoryImportError(f"{context}: line_no 必须是正整数") from exc
    if line_no <= 0:
        raise HistoryImportError(f"{context}: line_no 必须是正整数")
    debit = _amount(payload.get("debit_amount"), "debit_amount", context)
    credit = _amount(payload.get("credit_amount"), "credit_amount", context)
    if (Decimal(debit) > 0) == (Decimal(credit) > 0):
        raise HistoryImportError(f"{context}: 每条分录必须且只能填写借方或贷方金额")
    return HistoryLinePlan(
        source_system="kingdee",
        source_key=source_key,
        line_no=line_no,
        account_code=_optional_string(payload.get("account_code")),
        account_name=_optional_string(payload.get("account_name")),
        summary=_optional_string(payload.get("summary")),
        debit_amount=debit,
        credit_amount=credit,
    )


def plan_history_import(manifest_path: Path) -> HistoryImportPlan:
    """Validate a local, explicit Kingdee history JSON manifest without database IO."""
    try:
        raw = manifest_path.read_bytes()
        payload = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HistoryImportError("无法读取历史金蝶 JSON manifest") from exc
    if not isinstance(payload, dict):
        raise HistoryImportError("历史金蝶 manifest 必须是对象")
    if payload.get("source_system") != "kingdee":
        raise HistoryImportError("历史导入仅接受 source_system=kingdee")
    batch_key = _required_string(payload.get("source_batch_key"), "source_batch_key", "manifest")
    raw_vouchers = payload.get("vouchers")
    if not isinstance(raw_vouchers, list) or not raw_vouchers:
        raise HistoryImportError("manifest: vouchers 必须是非空数组")

    vouchers: list[HistoryVoucherPlan] = []
    source_keys: set[str] = set()
    for voucher_index, raw_voucher in enumerate(raw_vouchers, start=1):
        context = f"voucher[{voucher_index}]"
        if not isinstance(raw_voucher, dict):
            raise HistoryImportError(f"{context}: 凭证必须是对象")
        source_key = _required_string(raw_voucher.get("source_key"), "source_key", context)
        if source_key in source_keys:
            raise HistoryImportError(f"{context}: 重复的 source_key")
        source_keys.add(source_key)
        voucher_no = _required_string(raw_voucher.get("voucher_no"), "voucher_no", context)
        try:
            voucher_date = date.fromisoformat(_required_string(raw_voucher.get("voucher_date"), "voucher_date", context)[:10])
        except ValueError as exc:
            raise HistoryImportError(f"{context}: voucher_date 非法") from exc
        raw_lines = raw_voucher.get("lines")
        if not isinstance(raw_lines, list) or not raw_lines:
            raise HistoryImportError(f"{context}: lines 必须是非空数组")
        lines = tuple(_line_from_payload(line, f"{context}.line[{index}]") for index, line in enumerate(raw_lines, start=1))
        if len({line.source_key for line in lines}) != len(lines):
            raise HistoryImportError(f"{context}: 存在重复分录 source_key")
        if len({line.line_no for line in lines}) != len(lines):
            raise HistoryImportError(f"{context}: 存在重复 line_no")
        debit_total = sum((Decimal(line.debit_amount) for line in lines), Decimal("0"))
        credit_total = sum((Decimal(line.credit_amount) for line in lines), Decimal("0"))
        if debit_total != credit_total:
            raise HistoryImportError(f"{context}: 借贷不平衡")
        vouchers.append(HistoryVoucherPlan(
            source_system="kingdee",
            source_key=source_key,
            record_type="historical",
            is_readonly=True,
            voucher_no=voucher_no,
            voucher_date=voucher_date,
            summary=_optional_string(raw_voucher.get("summary")),
            lines=lines,
            source_payload=raw_voucher,
        ))
    return HistoryImportPlan(
        source_system="kingdee",
        source_batch_key=batch_key,
        source_checksum=hashlib.sha256(raw).hexdigest(),
        vouchers=tuple(vouchers),
    )


async def import_history_manifest(
    db: AsyncSession,
    manifest_path: Path,
    *,
    execute: bool = False,
    imported_by: int | None = None,
) -> HistoryImportResult:
    """Dry-run by default; persist only to isolated history tables when execute is true."""
    plan = plan_history_import(manifest_path)
    if not execute:
        return HistoryImportResult("dry_run", plan.source_batch_key, plan.record_count, 0, 0)

    batch = (await db.execute(
        select(FinanceCenterMumarenHistoryImportBatch).where(
            FinanceCenterMumarenHistoryImportBatch.source_system == "kingdee",
            FinanceCenterMumarenHistoryImportBatch.source_batch_key == plan.source_batch_key,
        )
    )).scalar_one_or_none()
    if batch is not None and batch.source_checksum != plan.source_checksum:
        raise HistoryImportError("同一 source_batch_key 的 manifest 校验和不一致")
    if batch is None:
        batch = FinanceCenterMumarenHistoryImportBatch(
            source_system="kingdee",
            source_batch_key=plan.source_batch_key,
            source_checksum=plan.source_checksum,
            imported_by=imported_by,
            record_count=plan.record_count,
            metadata_json={"record_type": "historical", "is_readonly": True},
        )
        db.add(batch)
        await db.flush()

    inserted = 0
    skipped = 0
    for voucher_plan in plan.vouchers:
        existing = (await db.execute(
            select(FinanceCenterMumarenHistoryVoucher).where(
                FinanceCenterMumarenHistoryVoucher.source_system == "kingdee",
                FinanceCenterMumarenHistoryVoucher.source_key == voucher_plan.source_key,
            )
        )).scalar_one_or_none()
        if existing is not None:
            skipped += 1
            continue
        voucher = FinanceCenterMumarenHistoryVoucher(
            import_batch_id=batch.id,
            source_system="kingdee",
            source_key=voucher_plan.source_key,
            record_type="historical",
            is_readonly=True,
            voucher_no=voucher_plan.voucher_no,
            voucher_date=voucher_plan.voucher_date,
            summary=voucher_plan.summary,
            source_payload=voucher_plan.source_payload,
        )
        db.add(voucher)
        await db.flush()
        for line_plan in voucher_plan.lines:
            db.add(FinanceCenterMumarenHistoryVoucherLine(
                history_voucher_id=voucher.id,
                source_system="kingdee",
                source_key=line_plan.source_key,
                line_no=line_plan.line_no,
                account_code=line_plan.account_code,
                account_name=line_plan.account_name,
                summary=line_plan.summary,
                debit_amount=line_plan.debit_amount,
                credit_amount=line_plan.credit_amount,
            ))
        inserted += 1
    return HistoryImportResult("executed", plan.source_batch_key, plan.record_count, inserted, skipped)
