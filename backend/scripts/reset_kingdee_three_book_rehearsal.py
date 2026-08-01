"""Reset only the isolated Kingdee three-book rehearsal database.

This utility never reads Kingdee and has three independent safeguards before it
can mutate data: an exact approved rehearsal database name, the configured
database name, and PostgreSQL's actual current database name. Its default mode
is a read-only count preview.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import and_, delete, func, select, text

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EXPECTED_BOOK_COUNT = 3
APPROVED_REHEARSAL_DATABASES = frozenset({"huabang_ai_finance_drill_20260729_r2"})


class RehearsalResetError(RuntimeError):
    """A safety condition prevented mutation of the rehearsal database."""


@dataclass(frozen=True)
class RehearsalResetResult:
    status: str
    database_name: str
    book_count: int
    account_count: int
    period_count: int
    voucher_count: int
    voucher_line_count: int
    balance_snapshot_count: int
    audit_log_count: int
    import_batch_count: int


def _assert_rehearsal_database_name(database_name: str) -> None:
    if database_name not in APPROVED_REHEARSAL_DATABASES:
        raise RehearsalResetError("只允许本次批准的专用演练库")


async def _scalar_count(db, statement) -> int:
    return int((await db.execute(statement)).scalar_one())


async def reset_kingdee_three_book_rehearsal(db, *, database_name: str, execute: bool) -> RehearsalResetResult:
    """Preview or remove exactly the three readonly Kingdee books in one test DB transaction."""
    _assert_rehearsal_database_name(database_name)

    from app.core.config import settings
    from app.models.mumaren_finance_center import (
        FinanceCenterMumarenAccount,
        FinanceCenterMumarenAuditLog,
        FinanceCenterMumarenBalanceSnapshot,
        FinanceCenterMumarenBook,
        FinanceCenterMumarenFiscalPeriod,
        FinanceCenterMumarenKingdeeImportBatch,
        FinanceCenterMumarenVoucher,
        FinanceCenterMumarenVoucherLine,
    )

    if settings.APP_ENV.lower() in {"production", "prod"}:
        raise RehearsalResetError("生产环境拒绝运行演练库重置工具")
    if settings.DB_NAME != database_name:
        raise RehearsalResetError("DB_NAME 与 --database-name 不一致，拒绝连接")

    if not execute:
        await db.execute(text("SET TRANSACTION READ ONLY"))

    actual_database_name = (await db.execute(text("SELECT current_database()"))).scalar_one()
    if actual_database_name != database_name:
        raise RehearsalResetError("PostgreSQL 当前数据库与 --database-name 不一致，拒绝连接")

    readonly_kingdee_books = and_(
        FinanceCenterMumarenBook.source_system == "kingdee_history",
        FinanceCenterMumarenBook.is_readonly.is_(True),
    )
    book_rows = (await db.execute(
        select(FinanceCenterMumarenBook.id, FinanceCenterMumarenBook.import_batch_key)
        .where(readonly_kingdee_books)
        .order_by(FinanceCenterMumarenBook.id)
    )).all()
    book_ids = [row.id for row in book_rows]
    if len(book_ids) != EXPECTED_BOOK_COUNT:
        raise RehearsalResetError(f"仅允许重置恰好 {EXPECTED_BOOK_COUNT} 个只读金蝶账簿，实际为 {len(book_ids)}")
    if any(not row.import_batch_key for row in book_rows):
        raise RehearsalResetError("存在没有 import_batch_key 的金蝶账簿，无法确认精确导入批次")
    batch_keys = sorted({row.import_batch_key for row in book_rows})
    if len(batch_keys) != 1:
        raise RehearsalResetError("三本演练账簿未指向同一导入批次，拒绝跨批次重置")

    voucher_ids = select(FinanceCenterMumarenVoucher.id).where(
        FinanceCenterMumarenVoucher.book_id.in_(book_ids)
    )
    result = RehearsalResetResult(
        status="deleted" if execute else "dry_run",
        database_name=database_name,
        book_count=len(book_ids),
        account_count=await _scalar_count(db, select(func.count()).select_from(FinanceCenterMumarenAccount).where(FinanceCenterMumarenAccount.book_id.in_(book_ids))),
        period_count=await _scalar_count(db, select(func.count()).select_from(FinanceCenterMumarenFiscalPeriod).where(FinanceCenterMumarenFiscalPeriod.book_id.in_(book_ids))),
        voucher_count=await _scalar_count(db, select(func.count()).select_from(FinanceCenterMumarenVoucher).where(FinanceCenterMumarenVoucher.book_id.in_(book_ids))),
        voucher_line_count=await _scalar_count(db, select(func.count()).select_from(FinanceCenterMumarenVoucherLine).where(FinanceCenterMumarenVoucherLine.voucher_id.in_(voucher_ids))),
        balance_snapshot_count=await _scalar_count(db, select(func.count()).select_from(FinanceCenterMumarenBalanceSnapshot).where(FinanceCenterMumarenBalanceSnapshot.book_id.in_(book_ids))),
        audit_log_count=await _scalar_count(db, select(func.count()).select_from(FinanceCenterMumarenAuditLog).where(FinanceCenterMumarenAuditLog.book_id.in_(book_ids))),
        import_batch_count=await _scalar_count(db, select(func.count()).select_from(FinanceCenterMumarenKingdeeImportBatch).where(
            FinanceCenterMumarenKingdeeImportBatch.source_system == "kingdee_history",
            FinanceCenterMumarenKingdeeImportBatch.batch_key.in_(batch_keys),
        )),
    )
    if not execute:
        return result

    # The migration's DB trigger allows the dedicated import GUC.  It is set
    # locally in this one transaction so regular application writes remain blocked.
    await db.execute(text("SET LOCAL app.mumaren_kingdee_import = 'on'"))
    await db.execute(delete(FinanceCenterMumarenBalanceSnapshot).where(FinanceCenterMumarenBalanceSnapshot.book_id.in_(book_ids)))
    await db.execute(delete(FinanceCenterMumarenVoucherLine).where(FinanceCenterMumarenVoucherLine.voucher_id.in_(voucher_ids)))
    await db.execute(delete(FinanceCenterMumarenVoucher).where(FinanceCenterMumarenVoucher.book_id.in_(book_ids)))
    await db.execute(delete(FinanceCenterMumarenFiscalPeriod).where(FinanceCenterMumarenFiscalPeriod.book_id.in_(book_ids)))
    await db.execute(delete(FinanceCenterMumarenAccount).where(FinanceCenterMumarenAccount.book_id.in_(book_ids)))
    await db.execute(delete(FinanceCenterMumarenAuditLog).where(FinanceCenterMumarenAuditLog.book_id.in_(book_ids)))
    await db.execute(delete(FinanceCenterMumarenBook).where(FinanceCenterMumarenBook.id.in_(book_ids)))
    await db.execute(delete(FinanceCenterMumarenKingdeeImportBatch).where(
        FinanceCenterMumarenKingdeeImportBatch.source_system == "kingdee_history",
        FinanceCenterMumarenKingdeeImportBatch.batch_key.in_(batch_keys),
    ))
    return result


async def _run(database_name: str, *, execute: bool) -> RehearsalResetResult:
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        async with db.begin():
            return await reset_kingdee_three_book_rehearsal(db, database_name=database_name, execute=execute)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset only the isolated Kingdee three-book rehearsal database")
    parser.add_argument("--database-name", required=True, help="must be the exact approved rehearsal database")
    parser.add_argument("--execute", action="store_true", help="without this flag the command is read-only")
    args = parser.parse_args()
    try:
        _assert_rehearsal_database_name(args.database_name)
        print(json.dumps(asdict(asyncio.run(_run(args.database_name, execute=args.execute))), ensure_ascii=False, sort_keys=True))
        return 0
    except RehearsalResetError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
