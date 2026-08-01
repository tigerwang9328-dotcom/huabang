"""Safety gate for removing a known, mis-archived Kingdee history batch.

The cleanup is intentionally limited to the isolated Mumaren history tables.
It never connects to Kingdee and never addresses legacy Huabang finance data.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mumaren_finance_center import (
    FinanceCenterMumarenBalanceSnapshot,
    FinanceCenterMumarenBook,
    FinanceCenterMumarenHistoryImportBatch,
    FinanceCenterMumarenHistoryVoucher,
    FinanceCenterMumarenKingdeeImportBatch,
    FinanceCenterMumarenVoucher,
    FinanceCenterMumarenVoucherLine,
)


class KingdeeHistoryCleanupError(ValueError):
    pass


# The mistaken archive was created from this canonical snapshot.  These are
# deliberately constants, rather than CLI parameters, so the command cannot
# be repointed at another history batch.
MISARCHIVED_HISTORY_SOURCE_BATCH_KEY = "kingdee-canonical-K3IMPORT_20260719_122445-mumaren-history-v2"
MISARCHIVED_HISTORY_SOURCE_CHECKSUM = "390a3033a00e32cb03534bbf9bb01fc615c0b20c3a1131bba0532a68e4b7b195"

EXPECTED_REPLACEMENT_BOOK_COUNT = 3
EXPECTED_REPLACEMENT_VOUCHER_COUNT = 339
EXPECTED_REPLACEMENT_LINE_COUNT = 4596
EXPECTED_REPLACEMENT_SNAPSHOT_COUNT = 6868
EXPECTED_MISARCHIVED_VOUCHER_COUNT = 339


@dataclass(frozen=True)
class KingdeeHistoryCleanupRequest:
    source_batch_key: str
    source_checksum: str
    kingdee_batch_key: str | None = None
    kingdee_manifest_checksum: str | None = None


@dataclass(frozen=True)
class KingdeeHistoryCleanupResult:
    status: str
    source_batch_key: str
    source_checksum: str
    candidate_voucher_count: int
    deleted_voucher_count: int


async def _validated_three_book_batch(db: AsyncSession, request: KingdeeHistoryCleanupRequest):
    batch = (await db.execute(
        select(FinanceCenterMumarenKingdeeImportBatch).where(
            FinanceCenterMumarenKingdeeImportBatch.batch_key == request.kingdee_batch_key,
            FinanceCenterMumarenKingdeeImportBatch.manifest_checksum == request.kingdee_manifest_checksum,
        )
    )).scalar_one_or_none()
    if batch is None:
        raise KingdeeHistoryCleanupError("未找到校验和匹配的三账套导入批次")
    # ``validated`` is assigned before records are written by the importer.
    # A committed cleanup therefore accepts only the final, persisted state.
    if batch.validation_status != "imported":
        raise KingdeeHistoryCleanupError("三账套导入批次尚未实际导入完成")
    return batch


async def _actual_replacement_counts(db: AsyncSession, batch_key: str) -> tuple[int, int, int, int]:
    """Return persisted migration rows; never trust batch self-reported counts."""
    book_count = (await db.execute(
        select(func.count()).select_from(FinanceCenterMumarenBook).where(
            FinanceCenterMumarenBook.source_system == "kingdee",
            FinanceCenterMumarenBook.import_batch_key == batch_key,
            FinanceCenterMumarenBook.is_readonly.is_(True),
            FinanceCenterMumarenBook.source_database.is_not(None),
        )
    )).scalar_one()
    voucher_count = (await db.execute(
        select(func.count()).select_from(FinanceCenterMumarenVoucher).where(
            FinanceCenterMumarenVoucher.source_system == "kingdee",
            FinanceCenterMumarenVoucher.import_batch_key == batch_key,
            FinanceCenterMumarenVoucher.is_readonly.is_(True),
            FinanceCenterMumarenVoucher.status == "posted",
        )
    )).scalar_one()
    line_count = (await db.execute(
        select(func.count()).select_from(FinanceCenterMumarenVoucherLine).where(
            FinanceCenterMumarenVoucherLine.source_system == "kingdee",
            FinanceCenterMumarenVoucherLine.import_batch_key == batch_key,
            FinanceCenterMumarenVoucherLine.is_readonly.is_(True),
        )
    )).scalar_one()
    snapshot_count = (await db.execute(
        select(func.count()).select_from(FinanceCenterMumarenBalanceSnapshot).where(
            FinanceCenterMumarenBalanceSnapshot.source_system == "kingdee",
            FinanceCenterMumarenBalanceSnapshot.import_batch_key == batch_key,
            FinanceCenterMumarenBalanceSnapshot.is_readonly.is_(True),
        )
    )).scalar_one()
    return int(book_count), int(voucher_count), int(line_count), int(snapshot_count)


async def _require_actual_replacement_data(db: AsyncSession, batch_key: str) -> None:
    actual = await _actual_replacement_counts(db, batch_key)
    expected = (
        EXPECTED_REPLACEMENT_BOOK_COUNT,
        EXPECTED_REPLACEMENT_VOUCHER_COUNT,
        EXPECTED_REPLACEMENT_LINE_COUNT,
        EXPECTED_REPLACEMENT_SNAPSHOT_COUNT,
    )
    if actual != expected:
        raise KingdeeHistoryCleanupError(
            "三账套实际迁移数据未通过核对："
            f"账簿/凭证/分录/快照={actual}，预期={expected}"
        )


def _require_fixed_history_identity(request: KingdeeHistoryCleanupRequest) -> None:
    if (
        request.source_batch_key != MISARCHIVED_HISTORY_SOURCE_BATCH_KEY
        or request.source_checksum != MISARCHIVED_HISTORY_SOURCE_CHECKSUM
    ):
        raise KingdeeHistoryCleanupError("只允许清理固定的已知误归档批次及其固定校验和")


async def cleanup_misarchived_kingdee_history(
    db: AsyncSession,
    request: KingdeeHistoryCleanupRequest,
    *,
    execute: bool = False,
) -> KingdeeHistoryCleanupResult:
    """Preview or precisely delete exactly one isolated history import batch.

    The caller owns the transaction.  A dry run marks it read-only before all
    database access; execution deletes only the exact Kingdee history batch
    after a checksum-matched, validated three-book import gate succeeds.
    """
    _require_fixed_history_identity(request)
    if not execute:
        await db.execute(text("SET TRANSACTION READ ONLY"))
    else:
        if not all((request.kingdee_batch_key, request.kingdee_manifest_checksum)):
            raise KingdeeHistoryCleanupError("--execute 必须提供已验证三账套批次的键及校验和")
        replacement_batch = await _validated_three_book_batch(db, request)
        await _require_actual_replacement_data(db, replacement_batch.batch_key)
    history_batch = (await db.execute(
        select(FinanceCenterMumarenHistoryImportBatch).where(
            FinanceCenterMumarenHistoryImportBatch.source_system == "kingdee",
            FinanceCenterMumarenHistoryImportBatch.source_batch_key == request.source_batch_key,
            FinanceCenterMumarenHistoryImportBatch.source_checksum == request.source_checksum,
        )
    )).scalar_one_or_none()
    if history_batch is None:
        raise KingdeeHistoryCleanupError("未找到 source_batch_key 与校验和同时匹配的误归档批次")

    candidate_count = (await db.execute(
        select(func.count()).select_from(FinanceCenterMumarenHistoryVoucher).where(
            FinanceCenterMumarenHistoryVoucher.import_batch_id == history_batch.id,
            FinanceCenterMumarenHistoryVoucher.source_system == "kingdee",
        )
    )).scalar_one()
    if not execute:
        return KingdeeHistoryCleanupResult("dry_run", request.source_batch_key, request.source_checksum, candidate_count, 0)

    if candidate_count != EXPECTED_MISARCHIVED_VOUCHER_COUNT:
        raise KingdeeHistoryCleanupError(
            f"误归档候选凭证数必须为 {EXPECTED_MISARCHIVED_VOUCHER_COUNT}，实际为 {candidate_count}"
        )

    # The voucher FK cascades to its lines, but the batch FK deliberately does
    # not cascade.  Remove only this batch's vouchers before its exact batch.
    await db.execute(
        delete(FinanceCenterMumarenHistoryVoucher).where(
            FinanceCenterMumarenHistoryVoucher.import_batch_id == history_batch.id,
            FinanceCenterMumarenHistoryVoucher.source_system == "kingdee",
        )
    )
    await db.execute(
        delete(FinanceCenterMumarenHistoryImportBatch).where(
            FinanceCenterMumarenHistoryImportBatch.id == history_batch.id,
            FinanceCenterMumarenHistoryImportBatch.source_system == "kingdee",
            FinanceCenterMumarenHistoryImportBatch.source_batch_key == request.source_batch_key,
            FinanceCenterMumarenHistoryImportBatch.source_checksum == request.source_checksum,
        )
    )
    return KingdeeHistoryCleanupResult("deleted", request.source_batch_key, request.source_checksum, candidate_count, candidate_count)
