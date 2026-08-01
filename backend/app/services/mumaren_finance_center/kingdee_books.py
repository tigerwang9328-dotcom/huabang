"""Read-only planner for importing canonical Kingdee account sets as finance books."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mumaren_finance_center import (
    FinanceCenterMumarenAccount,
    FinanceCenterMumarenBalanceSnapshot,
    FinanceCenterMumarenBook,
    FinanceCenterMumarenFiscalPeriod,
    FinanceCenterMumarenKingdeeImportBatch,
    FinanceCenterMumarenVoucher,
    FinanceCenterMumarenVoucherLine,
)


class KingdeeBooksImportError(ValueError):
    pass


def _money(value: Any) -> Decimal:
    return Decimal(str(value if value is not None else 0)).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class PlannedLine:
    account_code: str
    account_name: str
    debit_amount: str
    credit_amount: str
    source_payload: dict[str, Any]


@dataclass(frozen=True)
class PlannedVoucher:
    source_key: str
    voucher_no: str
    voucher_date: date
    summary: str | None
    status: str
    lines: tuple[PlannedLine, ...]
    normalized_negative_line_count: int
    is_normalized: bool
    source_payload: dict[str, Any]


@dataclass(frozen=True)
class PlannedAccount:
    source_key: str
    account_code: str
    account_name: str
    direction: str
    level: int
    source_payload: dict[str, Any]


@dataclass(frozen=True)
class PlannedPeriod:
    period_code: str
    start_date: date
    end_date: date
    source_payload: dict[str, Any]


@dataclass(frozen=True)
class PlannedBalanceSnapshot:
    account_source_key: str
    account_code: str
    period_code: str
    opening_amount: str
    period_debit: str
    period_credit: str
    closing_amount: str
    source_key: str
    source_payload: dict[str, Any]


@dataclass(frozen=True)
class PlannedBook:
    book_code: str
    book_name: str
    company_name: str
    source_company_name: str
    source_database: str
    is_readonly: bool
    accounts: tuple[PlannedAccount, ...]
    periods: tuple[PlannedPeriod, ...]
    balance_snapshots: tuple[PlannedBalanceSnapshot, ...]
    vouchers: tuple[PlannedVoucher, ...]


@dataclass(frozen=True)
class KingdeeBooksImportPlan:
    books: tuple[PlannedBook, ...]
    balance_count: int

    @property
    def book_count(self) -> int: return len(self.books)
    @property
    def voucher_count(self) -> int: return sum(len(book.vouchers) for book in self.books)
    @property
    def line_count(self) -> int: return sum(len(voucher.lines) for book in self.books for voucher in book.vouchers)


@dataclass(frozen=True)
class KingdeeImportResult:
    status: str
    batch_key: str
    book_count: int
    voucher_count: int
    line_count: int
    balance_count: int


def _rows(root: Path, relative: str, expected: str) -> list[dict[str, Any]]:
    path = root / relative
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise KingdeeBooksImportError(f"来源文件校验和不一致: {relative}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def _persistent_voucher_no(source_key: str) -> str:
    """Fit a source-primary-key-derived number into the current 64-char column."""
    candidate = f"K3-{source_key}"
    return candidate if len(candidate) <= 64 else f"K3-{hashlib.sha256(source_key.encode()).hexdigest()[:61]}"


def _balance_source_key(balance: dict[str, Any]) -> str:
    """Use the canonical Kingdee balance grain, including detail and currency."""
    fields = ("FAccountID", "FYear", "FPeriod", "FDetailID", "FCurrencyID")
    missing = [field for field in fields if field not in balance or balance[field] is None]
    if missing:
        raise KingdeeBooksImportError(f"余额来源主键字段缺失: {', '.join(missing)}")
    return "|".join(f"{field}={balance[field]}" for field in fields)


def plan_kingdee_books_import(manifest_path: Path) -> KingdeeBooksImportPlan:
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    checksums = {item["path"]: item["sha256"] for item in manifest.get("files", [])}
    books: list[PlannedBook] = []
    balance_count = 0
    for account_set in manifest.get("account_sets", []):
        tables = account_set["tables"]
        accounts = _rows(root, tables["accounts"], checksums[tables["accounts"]])
        headers = _rows(root, tables["vouchers"], checksums[tables["vouchers"]])
        entries = _rows(root, tables["voucher_entries"], checksums[tables["voucher_entries"]])
        balances = _rows(root, tables["balances"], checksums[tables["balances"]])
        balance_count += len(balances)
        by_account = {str(row["FAccountID"]): row for row in accounts}
        planned_accounts = tuple(
            PlannedAccount(
                source_key=str(account["FAccountID"]),
                account_code=str(account["FNumber"]),
                account_name=str(account["FName"]),
                direction="debit" if int(account.get("FDC") or 1) == 1 else "credit",
                level=int(account.get("FLevel") or 1),
                source_payload={**account, "source_account": account, "source_checksum": checksums[tables["accounts"]]},
            )
            for account in accounts
        )
        periods: dict[str, PlannedPeriod] = {}
        snapshots: list[PlannedBalanceSnapshot] = []
        snapshot_source_keys: set[str] = set()
        for balance in balances:
            account_source_key = str(balance["FAccountID"])
            account = by_account.get(account_source_key)
            if account is None:
                raise KingdeeBooksImportError(f"余额 {account_source_key}: 科目不存在")
            year, period = int(balance["FYear"]), int(balance["FPeriod"])
            if not 1 <= period <= 12:
                raise KingdeeBooksImportError(f"余额 {account_source_key}: 非法会计期间")
            period_code = f"{year:04d}-{period:02d}"
            if period_code not in periods:
                periods[period_code] = PlannedPeriod(
                    period_code=period_code,
                    start_date=date(year, period, 1),
                    end_date=date(year, period, monthrange(year, period)[1]),
                    source_payload={"source_year": year, "source_period": period, "source_checksum": checksums[tables["balances"]]},
                )
            source_key = _balance_source_key(balance)
            if source_key in snapshot_source_keys:
                raise KingdeeBooksImportError(f"余额来源主键重复: {source_key}")
            snapshot_source_keys.add(source_key)
            snapshots.append(PlannedBalanceSnapshot(
                account_source_key=account_source_key,
                account_code=str(account["FNumber"]),
                period_code=period_code,
                opening_amount=f"{_money(balance.get('FBeginBalance')):.2f}",
                period_debit=f"{_money(balance.get('FDebit')):.2f}",
                period_credit=f"{_money(balance.get('FCredit')):.2f}",
                closing_amount=f"{_money(balance.get('FEndBalance')):.2f}",
                source_key=source_key,
                source_payload={**balance, "source_balance": balance, "source_checksum": checksums[tables["balances"]]},
            ))
        headers_by_voucher: dict[str, dict[str, Any]] = {}
        for header in headers:
            key = str(header["FVoucherID"])
            if key in headers_by_voucher:
                raise KingdeeBooksImportError(f"{key}: 重复凭证主键")
            headers_by_voucher[key] = header
        by_voucher: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entry in entries:
            by_voucher[str(entry["FVoucherID"])].append(entry)
        header_keys, entry_keys = set(headers_by_voucher), set(by_voucher)
        if header_keys != entry_keys:
            missing_entries = sorted(header_keys - entry_keys)
            orphan_entries = sorted(entry_keys - header_keys)
            raise KingdeeBooksImportError(
                f"凭证头与分录集合不一致: 缺少分录={missing_entries}, 孤立分录={orphan_entries}"
            )
        vouchers: list[PlannedVoucher] = []
        for header in headers:
            key = str(header["FVoucherID"]); lines: list[PlannedLine] = []; negatives = 0
            voucher_entries = sorted(by_voucher[key], key=lambda row: int(row["FEntryID"]))
            if int(header.get("FEntryCount") or 0) != len(voucher_entries):
                raise KingdeeBooksImportError(f"{key}: 分录数量与凭证头不一致")
            source_debit = source_credit = Decimal("0.00")
            debit_total = credit_total = Decimal("0.00")
            for entry in voucher_entries:
                account = by_account.get(str(entry["FAccountID"]))
                if account is None: raise KingdeeBooksImportError(f"{key}: 科目不存在")
                value = _money(entry["FAmount"]); direction = int(entry["FDC"])
                if direction not in (0, 1) or value == 0: raise KingdeeBooksImportError(f"{key}: 非法分录")
                if direction == 1:
                    source_debit += value
                else:
                    source_credit += value
                source_payload = {
                    **entry,
                    "source_entry": entry,
                    "source_checksum": checksums[tables["voucher_entries"]],
                }
                if value < 0:
                    direction = 1 - direction; value = -value; negatives += 1
                    source_payload["normalization_rule"] = "flip_direction_and_abs_amount"
                debit, credit = (value, Decimal("0")) if direction == 1 else (Decimal("0"), value)
                debit_total += debit; credit_total += credit
                lines.append(PlannedLine(str(account["FNumber"]), str(account["FName"]), f"{debit:.2f}", f"{credit:.2f}", source_payload))
            if source_debit != _money(header.get("FDebitTotal")):
                raise KingdeeBooksImportError(f"{key}: 借方合计与凭证头不一致")
            if source_credit != _money(header.get("FCreditTotal")):
                raise KingdeeBooksImportError(f"{key}: 贷方合计与凭证头不一致")
            if not lines or debit_total != credit_total:
                raise KingdeeBooksImportError(f"{key}: 借贷不平衡")
            vouchers.append(PlannedVoucher(
                source_key=key,
                voucher_no=_persistent_voucher_no(key),
                voucher_date=date.fromisoformat(str(header["FDate"])[:10]),
                summary=str(header["FExplanation"]) if header.get("FExplanation") is not None else None,
                status="posted",
                lines=tuple(lines),
                normalized_negative_line_count=negatives,
                is_normalized=negatives > 0,
                source_payload={
                    "source_type": "kingdee_history",
                    "source_header": header,
                    "source_voucher_no": str(header.get("FNumber") or ""),
                    "source_group_id": header.get("FGroupID"),
                    "source_explanation": header.get("FExplanation"),
                    "source_debit_total": f"{source_debit:.2f}",
                    "source_credit_total": f"{source_credit:.2f}",
                    "normalized_debit_total": f"{debit_total:.2f}",
                    "normalized_credit_total": f"{credit_total:.2f}",
                    "normalized_negative_line_count": negatives,
                    "source_checksum": checksums[tables["vouchers"]],
                },
            ))
        database = str(account_set["database"])
        source_company = str(account_set["company_name"])
        display_names = {
            "AIS20251127140257": "贵州黔台源庄酒业有限公司（新）",
            "AIS20260305112309": "贵阳市雅斯贸易有限公司",
        }
        company = display_names.get(database, str(account_set.get("short_name") or source_company))
        books.append(PlannedBook(
            f"K3-{database}", company, company, source_company, database, True,
            planned_accounts, tuple(periods.values()), tuple(snapshots), tuple(vouchers),
        ))
    if not books: raise KingdeeBooksImportError("未发现账套")
    return KingdeeBooksImportPlan(tuple(books), balance_count)


async def import_kingdee_books(
    db: AsyncSession | None,
    manifest_path: Path,
    *,
    execute: bool = False,
    batch_key: str | None = None,
) -> KingdeeImportResult:
    """Import the validated canonical snapshot only when explicitly requested.

    This command deliberately has no Kingdee connection.  Database callers must
    wrap it in one transaction so any validation/import failure rolls back.
    """
    plan = plan_kingdee_books_import(manifest_path)
    manifest_checksum = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    resolved_batch_key = batch_key or f"kingdee-canonical-{manifest_checksum[:16]}"
    result = KingdeeImportResult(
        status="dry_run" if not execute else "imported",
        batch_key=resolved_batch_key,
        book_count=plan.book_count,
        voucher_count=plan.voucher_count,
        line_count=plan.line_count,
        balance_count=plan.balance_count,
    )
    if not execute:
        return result
    if db is None:
        raise KingdeeBooksImportError("执行导入必须提供数据库会话")

    # The PostgreSQL migration trigger allows writes to readonly books only in
    # this transaction-scoped import mode.
    await db.execute(text("SET LOCAL app.mumaren_kingdee_import = 'on'"))
    existing_batch = (await db.execute(
        select(FinanceCenterMumarenKingdeeImportBatch).where(
            FinanceCenterMumarenKingdeeImportBatch.batch_key == resolved_batch_key
        )
    )).scalar_one_or_none()
    if existing_batch is not None:
        if existing_batch.manifest_checksum != manifest_checksum:
            raise KingdeeBooksImportError("同一导入批次的来源校验和已变化")
        return KingdeeImportResult("already_imported", resolved_batch_key, plan.book_count, plan.voucher_count, plan.line_count, plan.balance_count)

    existing_batch = FinanceCenterMumarenKingdeeImportBatch(
        batch_key=resolved_batch_key,
        source_system="kingdee_history",
        manifest_checksum=manifest_checksum,
        validation_status="validated",
        expected_book_count=plan.book_count,
        expected_voucher_count=plan.voucher_count,
        expected_line_count=plan.line_count,
        expected_balance_snapshot_count=plan.balance_count,
        validation_payload={"source": str(manifest_path), "dry_run_validated": True},
    )
    db.add(existing_batch)
    await db.flush()
    for planned_book in plan.books:
        book = (await db.execute(select(FinanceCenterMumarenBook).where(
            FinanceCenterMumarenBook.source_system == "kingdee_history",
            FinanceCenterMumarenBook.source_database == planned_book.source_database,
            FinanceCenterMumarenBook.source_key == planned_book.source_database,
        ))).scalar_one_or_none()
        if book is None:
            book = FinanceCenterMumarenBook(
                book_code=planned_book.book_code,
                book_name=planned_book.book_name,
                company_name=planned_book.company_name,
                source_system="kingdee_history",
                source_database=planned_book.source_database,
                source_company_name=planned_book.source_company_name,
                source_key=planned_book.source_database,
                source_checksum=manifest_checksum,
                import_batch_key=resolved_batch_key,
                is_readonly=True,
            )
            db.add(book)
            await db.flush()
        elif book.source_checksum != manifest_checksum:
            raise KingdeeBooksImportError(f"账套 {planned_book.source_database} 的来源校验和已变化")

        existing_accounts = (await db.execute(select(FinanceCenterMumarenAccount).where(
            FinanceCenterMumarenAccount.book_id == book.id,
            FinanceCenterMumarenAccount.source_system == "kingdee_history",
        ))).scalars().all()
        accounts_by_source_key = {str(account.source_key): account for account in existing_accounts}
        for planned_account in planned_book.accounts:
            account = accounts_by_source_key.get(planned_account.source_key)
            if account is None:
                account = FinanceCenterMumarenAccount(
                    book_id=book.id, account_code=planned_account.account_code, account_name=planned_account.account_name,
                    account_type="unclassified", direction=planned_account.direction, level=planned_account.level,
                    source_system="kingdee_history", source_key=planned_account.source_key, source_checksum=manifest_checksum,
                    import_batch_key=resolved_batch_key, is_readonly=True,
                    source_payload={**planned_account.source_payload, "mapping_status": "pending_mapping"},
                )
                db.add(account)
                accounts_by_source_key[planned_account.source_key] = account
            elif account.source_checksum != manifest_checksum:
                raise KingdeeBooksImportError(f"科目 {planned_account.source_key} 的来源校验和已变化")
        await db.flush()

        existing_periods = (await db.execute(select(FinanceCenterMumarenFiscalPeriod).where(
            FinanceCenterMumarenFiscalPeriod.book_id == book.id,
            FinanceCenterMumarenFiscalPeriod.source_system == "kingdee_history",
        ))).scalars().all()
        periods_by_source_key = {str(period.source_key): period for period in existing_periods}
        for period in planned_book.periods:
            stored_period = periods_by_source_key.get(period.period_code)
            if stored_period is None:
                stored_period = FinanceCenterMumarenFiscalPeriod(
                    book_id=book.id, period_code=period.period_code, start_date=period.start_date, end_date=period.end_date,
                    status="closed", source_system="kingdee_history", source_key=period.period_code,
                    source_checksum=manifest_checksum, import_batch_key=resolved_batch_key, is_readonly=True,
                    source_payload=period.source_payload,
                )
                db.add(stored_period)
                periods_by_source_key[period.period_code] = stored_period
            elif stored_period.source_checksum != manifest_checksum:
                raise KingdeeBooksImportError(f"会计期间 {period.period_code} 的来源校验和已变化")
        await db.flush()

        existing_snapshots = (await db.execute(select(FinanceCenterMumarenBalanceSnapshot).where(
            FinanceCenterMumarenBalanceSnapshot.book_id == book.id,
        ))).scalars().all()
        snapshots_by_key = {str(snapshot.source_key): snapshot for snapshot in existing_snapshots}
        for snapshot in planned_book.balance_snapshots:
            account = accounts_by_source_key[snapshot.account_source_key]
            stored_snapshot = snapshots_by_key.get(snapshot.source_key)
            if stored_snapshot is None:
                stored_snapshot = FinanceCenterMumarenBalanceSnapshot(
                    book_id=book.id, account_id=account.id, period_code=snapshot.period_code,
                    source_system="kingdee_history", source_database=planned_book.source_database, source_key=snapshot.source_key,
                    source_checksum=manifest_checksum, import_batch_key=resolved_batch_key, is_readonly=True,
                    opening_amount=Decimal(snapshot.opening_amount), period_debit=Decimal(snapshot.period_debit),
                    period_credit=Decimal(snapshot.period_credit), closing_amount=Decimal(snapshot.closing_amount),
                    source_payload=snapshot.source_payload,
                )
                db.add(stored_snapshot)
                snapshots_by_key[snapshot.source_key] = stored_snapshot
            elif stored_snapshot.source_checksum != manifest_checksum:
                raise KingdeeBooksImportError(f"余额快照 {snapshot.source_key} 的来源校验和已变化")
        await db.flush()
        existing_vouchers = (await db.execute(select(FinanceCenterMumarenVoucher).where(
            FinanceCenterMumarenVoucher.book_id == book.id,
            FinanceCenterMumarenVoucher.source_system == "kingdee_history",
        ))).scalars().all()
        vouchers_by_source_key = {str(voucher.source_key): voucher for voucher in existing_vouchers}
        new_vouchers: list[tuple[PlannedVoucher, FinanceCenterMumarenVoucher]] = []
        for voucher in planned_book.vouchers:
            stored = vouchers_by_source_key.get(voucher.source_key)
            if stored is not None:
                if stored.source_checksum != manifest_checksum:
                    raise KingdeeBooksImportError(f"凭证 {voucher.source_key} 的来源校验和已变化")
                continue
            debit = sum(Decimal(line.debit_amount) for line in voucher.lines)
            credit = sum(Decimal(line.credit_amount) for line in voucher.lines)
            stored = FinanceCenterMumarenVoucher(
                book_id=book.id, voucher_no=voucher.voucher_no, voucher_date=voucher.voucher_date, summary=voucher.summary,
                status="posted", total_debit=debit, total_credit=credit,
                source_system="kingdee_history", source_database=planned_book.source_database,
                source_key=voucher.source_key, source_checksum=manifest_checksum,
                import_batch_key=resolved_batch_key, is_readonly=True,
                is_normalized=voucher.is_normalized,
                source_payload=voucher.source_payload,
            )
            db.add(stored)
            vouchers_by_source_key[voucher.source_key] = stored
            new_vouchers.append((voucher, stored))
        await db.flush()
        for voucher, stored in new_vouchers:
            for line_no, line in enumerate(voucher.lines, start=1):
                db.add(FinanceCenterMumarenVoucherLine(
                    voucher_id=stored.id, line_no=line_no, account_id=accounts_by_source_key[str(line.source_payload["FAccountID"])].id,
                    debit_amount=Decimal(line.debit_amount), credit_amount=Decimal(line.credit_amount),
                    source_system="kingdee_history", source_key=f"{voucher.source_key}:{line.source_payload['FEntryID']}",
                    source_checksum=manifest_checksum, import_batch_key=resolved_batch_key,
                    is_readonly=True, source_payload=line.source_payload,
                ))
    await db.flush()
    existing_batch.validation_status = "imported"
    existing_batch.imported_at = datetime.now(timezone.utc)
    return result
