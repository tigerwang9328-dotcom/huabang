"""Writable finance-center service built on top of verified Kingdee history."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance_core import (
    FinAccount,
    FinBook,
    FinLedgerBalance,
    FinOperationLog,
    FinPeriod,
    FinSourceLink,
    FinStatementLine,
    FinStatementMapping,
    FinVoucher,
    FinVoucherEntry,
    FinVoucherVersion,
)
from app.models.kingdee_finance import (
    DimFinanceAccount,
    DimLegalEntity,
    DmFinanceStatementMonthly,
    DwdGlBalanceMonthly,
    DwdGlVoucher,
    DwdGlVoucherEntry,
)


class FinanceCenterError(RuntimeError):
    """Raised when a finance-center command would break accounting invariants."""


def _decimal(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.0001"))


def _period_bounds(period: str) -> tuple[int, int, date, date]:
    year, month = (int(part) for part in period.split("-"))
    return year, month, date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _balance_amount(direction: str, debit, credit) -> Decimal:
    debit_amount = _decimal(debit)
    credit_amount = _decimal(credit)
    return debit_amount - credit_amount if direction == "debit" else credit_amount - debit_amount


class FinanceCenterService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def open_period(self, book_id: int, period: str) -> dict:
        existing = (
            await self.db.execute(select(FinPeriod).where(FinPeriod.book_id == book_id, FinPeriod.period == period))
        ).scalar_one_or_none()
        if existing:
            if existing.status != "open":
                existing.status = "open"
                existing.closed_by = None
                existing.closed_at = None
                existing.close_reason = None
                existing.version = int(existing.version or 1) + 1
                await self.db.commit()
            return {"period_id": existing.id, "status": existing.status}
        year, month, start_date, end_date = _period_bounds(period)
        row = FinPeriod(
            book_id=book_id,
            period=period,
            fiscal_year=year,
            fiscal_period=month,
            start_date=start_date,
            end_date=end_date,
            status="open",
        )
        self.db.add(row)
        await self.db.commit()
        return {"period_id": row.id, "status": row.status}

    async def create_voucher(
        self,
        book_id: int,
        period: str,
        voucher_no: str,
        voucher_date: date,
        entries: list[dict],
        actor_name: str,
        reason: str,
        origin_kind: str = "manual",
        reversal_of_id: int | None = None,
    ) -> dict:
        if not reason or not reason.strip():
            raise FinanceCenterError("voucher creation reason is required")
        period_row = (
            await self.db.execute(select(FinPeriod).where(FinPeriod.book_id == book_id, FinPeriod.period == period))
        ).scalar_one_or_none()
        if not period_row:
            raise FinanceCenterError(f"period not found: {period}")
        if period_row.status != "open" and origin_kind != "kingdee_history":
            raise FinanceCenterError(f"period is not open: {period}")
        total_debit, total_credit = self._entry_totals(entries)
        voucher = FinVoucher(
            book_id=book_id,
            period_id=period_row.id,
            voucher_no=voucher_no,
            voucher_group="记",
            voucher_date=voucher_date,
            period=period,
            status="draft",
            origin_kind=origin_kind,
            total_debit=total_debit,
            total_credit=total_credit,
            prepared_name=actor_name,
            reversal_of_id=reversal_of_id,
        )
        self.db.add(voucher)
        await self.db.flush()
        for line_no, entry in enumerate(entries, 1):
            self.db.add(
                FinVoucherEntry(
                    book_id=book_id,
                    voucher_id=voucher.id,
                    line_no=line_no,
                    account_id=entry["account_id"],
                    summary=entry["summary"],
                    debit_amount=_decimal(entry.get("debit_amount")),
                    credit_amount=_decimal(entry.get("credit_amount")),
                    currency_code=entry.get("currency_code") or "CNY",
                    exchange_rate=entry.get("exchange_rate") or Decimal("1"),
                    aux_items=entry.get("aux_items") or {},
                )
            )
        await self.db.flush()
        after = await self._voucher_snapshot(voucher)
        self.db.add(
            FinVoucherVersion(
                book_id=book_id,
                voucher_id=voucher.id,
                version=voucher.version,
                action="create",
                after_snapshot=after,
                actor_name=actor_name,
                reason=reason,
            )
        )
        self.db.add(
            FinOperationLog(
                book_id=book_id,
                actor_name=actor_name,
                action="voucher.create",
                target_type="voucher",
                target_id=str(voucher.id),
                reason=reason,
                after_data=after,
            )
        )
        await self.db.commit()
        return {"status": voucher.status, "voucher_id": voucher.id, "version": voucher.version}

    async def post_voucher(self, voucher_id: int, actor_name: str, reason: str) -> dict:
        if not reason or not reason.strip():
            raise FinanceCenterError("posting reason is required")
        voucher = await self.db.get(FinVoucher, voucher_id)
        if not voucher:
            raise FinanceCenterError(f"voucher not found: {voucher_id}")
        if voucher.status != "draft":
            raise FinanceCenterError(f"only draft vouchers can be posted: {voucher.status}")
        entries = (
            await self.db.execute(select(FinVoucherEntry).where(FinVoucherEntry.voucher_id == voucher.id))
        ).scalars().all()
        total_debit = sum((_decimal(entry.debit_amount) for entry in entries), Decimal("0.0000"))
        total_credit = sum((_decimal(entry.credit_amount) for entry in entries), Decimal("0.0000"))
        if not entries or total_debit != total_credit:
            raise FinanceCenterError("voucher is not balanced")
        period = await self.db.get(FinPeriod, voucher.period_id)
        if period and period.status != "open" and voucher.origin_kind != "kingdee_history":
            raise FinanceCenterError(f"period is not open: {period.period}")
        before = await self._voucher_snapshot(voucher)
        voucher.total_debit = total_debit
        voucher.total_credit = total_credit
        voucher.status = "posted"
        voucher.posted_at = datetime.now(timezone.utc)
        voucher.version = int(voucher.version or 1) + 1
        await self.db.flush()
        await self._recompute_ledger_for_period(voucher.book_id, voucher.period_id)
        after = await self._voucher_snapshot(voucher)
        self.db.add(
            FinVoucherVersion(
                book_id=voucher.book_id,
                voucher_id=voucher.id,
                version=voucher.version,
                action="post",
                before_snapshot=before,
                after_snapshot=after,
                actor_name=actor_name,
                reason=reason,
            )
        )
        self.db.add(
            FinOperationLog(
                book_id=voucher.book_id,
                actor_name=actor_name,
                action="voucher.post",
                target_type="voucher",
                target_id=str(voucher.id),
                reason=reason,
                before_data=before,
                after_data=after,
            )
        )
        await self.db.commit()
        return {"status": voucher.status, "voucher_id": voucher.id, "version": voucher.version}

    async def reverse_voucher(self, voucher_id: int, voucher_no: str, actor_name: str, reason: str) -> dict:
        original = await self.db.get(FinVoucher, voucher_id)
        if not original:
            raise FinanceCenterError(f"voucher not found: {voucher_id}")
        if original.status != "posted":
            raise FinanceCenterError(f"only posted vouchers can be reversed: {original.status}")
        source_entries = (
            await self.db.execute(
                select(FinVoucherEntry).where(FinVoucherEntry.voucher_id == original.id).order_by(FinVoucherEntry.line_no)
            )
        ).scalars().all()
        reversal_entries = [
            {
                "account_id": entry.account_id,
                "summary": f"Reverse: {entry.summary}",
                "debit_amount": entry.credit_amount,
                "credit_amount": entry.debit_amount,
                "currency_code": entry.currency_code,
                "exchange_rate": entry.exchange_rate,
                "aux_items": entry.aux_items,
            }
            for entry in source_entries
        ]
        created = await self.create_voucher(
            original.book_id,
            period=original.period,
            voucher_no=voucher_no,
            voucher_date=original.voucher_date,
            entries=reversal_entries,
            actor_name=actor_name,
            reason=reason,
            origin_kind="reversal",
            reversal_of_id=original.id,
        )
        await self.post_voucher(created["voucher_id"], actor_name=actor_name, reason=reason)
        before = await self._voucher_snapshot(original)
        original.status = "reversed"
        original.reversed_by_id = created["voucher_id"]
        original.version = int(original.version or 1) + 1
        await self.db.flush()
        await self._recompute_ledger_for_period(original.book_id, original.period_id)
        after = await self._voucher_snapshot(original)
        self.db.add(
            FinVoucherVersion(
                book_id=original.book_id,
                voucher_id=original.id,
                version=original.version,
                action="reverse",
                before_snapshot=before,
                after_snapshot=after,
                actor_name=actor_name,
                reason=reason,
            )
        )
        await self.db.commit()
        return {"status": "posted", "voucher_id": created["voucher_id"], "reversal_of_id": original.id}

    async def upsert_statement_line(
        self,
        template_code: str,
        template_version: int,
        statement_type: str,
        line_code: str,
        line_name: str,
        display_order: int,
    ) -> dict:
        row = (
            await self.db.execute(
                select(FinStatementLine).where(
                    FinStatementLine.template_code == template_code,
                    FinStatementLine.template_version == template_version,
                    FinStatementLine.statement_type == statement_type,
                    FinStatementLine.line_code == line_code,
                )
            )
        ).scalar_one_or_none()
        if row:
            row.line_name = line_name
            row.display_order = display_order
        else:
            row = FinStatementLine(
                template_code=template_code,
                template_version=template_version,
                statement_type=statement_type,
                line_code=line_code,
                line_name=line_name,
                display_order=display_order,
            )
            self.db.add(row)
        await self.db.commit()
        return {"statement_line_id": row.id, "line_code": row.line_code}

    async def map_account_to_statement(
        self,
        book_id: int,
        account_id: int,
        statement_line_id: int,
        amount_sign: int,
        actor_name: str,
    ) -> dict:
        line = await self.db.get(FinStatementLine, statement_line_id)
        if not line:
            raise FinanceCenterError(f"statement line not found: {statement_line_id}")
        account = await self.db.get(FinAccount, account_id)
        if not account or account.book_id != book_id:
            raise FinanceCenterError("account does not belong to the requested book")
        mapping = (
            await self.db.execute(
                select(FinStatementMapping).where(
                    FinStatementMapping.book_id == book_id,
                    FinStatementMapping.account_id == account_id,
                    FinStatementMapping.statement_line_id == statement_line_id,
                )
            )
        ).scalar_one_or_none()
        if mapping:
            mapping.amount_sign = amount_sign
            mapping.status = "confirmed"
            mapping.confirmed_at = datetime.now(timezone.utc)
            mapping.version = int(mapping.version or 1) + 1
        else:
            mapping = FinStatementMapping(
                book_id=book_id,
                account_id=account_id,
                statement_line_id=statement_line_id,
                statement_type=line.statement_type,
                amount_sign=amount_sign,
                status="confirmed",
                mapping_source="manual",
                confirmed_at=datetime.now(timezone.utc),
            )
            self.db.add(mapping)
        self.db.add(
            FinOperationLog(
                book_id=book_id,
                actor_name=actor_name,
                action="statement.mapping.confirm",
                target_type="statement_mapping",
                target_id=str(statement_line_id),
                reason="confirmed account statement mapping",
                after_data={
                    "account_id": account_id,
                    "statement_line_id": statement_line_id,
                    "amount_sign": amount_sign,
                },
            )
        )
        await self.db.commit()
        return {"mapping_id": mapping.id, "status": mapping.status}

    async def generate_statement_monthly(self, book_id: int, period: str, statement_type: str) -> dict:
        book = await self.db.get(FinBook, book_id)
        if not book:
            raise FinanceCenterError(f"book not found: {book_id}")
        balance_rows = (
            await self.db.execute(
                select(FinLedgerBalance, FinAccount)
                .join(FinAccount, FinAccount.id == FinLedgerBalance.account_id)
                .where(FinLedgerBalance.book_id == book_id, FinLedgerBalance.period == period)
                .order_by(FinAccount.account_code)
            )
        ).all()
        if not balance_rows:
            return {"status": "pending_data", "items": [], "issues": [{"code": "missing_balances", "period": period}]}
        mapped_account_ids = set(
            (
                await self.db.execute(
                    select(FinStatementMapping.account_id)
                    .where(
                        FinStatementMapping.book_id == book_id,
                        FinStatementMapping.statement_type == statement_type,
                        FinStatementMapping.status == "confirmed",
                    )
                    .distinct()
                )
            ).scalars()
        )
        balance_account_ids = {account.id for _, account in balance_rows}
        missing_accounts = [
            {"code": "unmapped_account", "account_code": account.account_code, "account_name": account.account_name}
            for _, account in balance_rows
            if account.id not in mapped_account_ids
        ]
        if missing_accounts:
            return {"status": "pending_mapping", "items": [], "issues": missing_accounts}

        rows = (
            await self.db.execute(
                select(FinStatementMapping, FinStatementLine, FinLedgerBalance, FinAccount)
                .join(FinStatementLine, FinStatementLine.id == FinStatementMapping.statement_line_id)
                .join(FinLedgerBalance, FinLedgerBalance.account_id == FinStatementMapping.account_id)
                .join(FinAccount, FinAccount.id == FinStatementMapping.account_id)
                .where(
                    FinStatementMapping.book_id == book_id,
                    FinStatementMapping.statement_type == statement_type,
                    FinStatementMapping.status == "confirmed",
                    FinLedgerBalance.book_id == book_id,
                    FinLedgerBalance.period == period,
                    FinStatementMapping.account_id.in_(balance_account_ids),
                )
                .order_by(FinStatementLine.display_order, FinStatementLine.line_code)
            )
        ).all()
        grouped: dict[str, dict] = {}
        for mapping, line, balance, account in rows:
            value = self._statement_amount(statement_type, balance, account) * int(mapping.amount_sign or 1)
            current = grouped.setdefault(
                line.line_code,
                {
                    "line": line,
                    "amount": Decimal("0.0000"),
                },
            )
            current["amount"] += value

        items = []
        for line_code, payload in grouped.items():
            line = payload["line"]
            amount = _decimal(payload["amount"])
            await self._upsert_dm_statement_row(book, period, statement_type, line, amount, "ready", [])
            items.append(
                {
                    "line_code": line_code,
                    "line_name": line.line_name,
                    "current_amount": float(amount),
                    "status": "ready",
                }
            )
        await self.db.commit()
        return {"status": "ready", "items": items, "issues": []}

    async def get_statement_monthly(self, book_id: int, period: str, statement_type: str) -> dict:
        book = await self.db.get(FinBook, book_id)
        if not book:
            raise FinanceCenterError(f"book not found: {book_id}")
        rows = (
            await self.db.execute(
                select(DmFinanceStatementMonthly)
                .where(
                    DmFinanceStatementMonthly.legal_entity_id == book.legal_entity_id,
                    DmFinanceStatementMonthly.period == period,
                    DmFinanceStatementMonthly.statement_type == statement_type,
                    DmFinanceStatementMonthly.source_system == "finance_center",
                )
                .order_by(DmFinanceStatementMonthly.display_order, DmFinanceStatementMonthly.line_code)
            )
        ).scalars().all()
        if not rows:
            return {"status": "pending_data", "items": [], "issues": [{"code": "statement_not_generated"}]}
        status = "ready" if all(row.status == "ready" for row in rows) else "pending_mapping"
        return {
            "status": status,
            "items": [
                {
                    "line_code": row.line_code,
                    "line_name": row.line_name,
                    "current_amount": float(row.current_amount) if row.current_amount is not None else None,
                    "status": row.status,
                }
                for row in rows
            ],
            "issues": [issue for row in rows for issue in (row.quality_issues or [])],
        }

    async def import_kingdee_history_to_formal_ledger(self, account_set_code: str) -> dict:
        entity = (
            await self.db.execute(
                select(DimLegalEntity).where(DimLegalEntity.account_set_code == account_set_code)
            )
        ).scalar_one_or_none()
        if not entity:
            raise FinanceCenterError(f"Kingdee account set not found: {account_set_code}")

        created = {
            "books": 0,
            "periods": 0,
            "accounts": 0,
            "vouchers": 0,
            "voucher_entries": 0,
            "ledger_balances": 0,
        }
        book, was_created = await self._get_or_create_book(entity)
        created["books"] += int(was_created)

        periods = await self._ensure_periods(book.id, account_set_code)
        created["periods"] += periods["created"]
        account_map, account_created = await self._ensure_accounts(book.id, entity.id)
        created["accounts"] += account_created

        voucher_result = await self._ensure_vouchers(book.id, entity.id, account_set_code, account_map)
        created["vouchers"] += voucher_result["vouchers"]
        created["voucher_entries"] += voucher_result["voucher_entries"]

        balance_created = await self._ensure_ledger_balances(book.id, entity.id, account_map)
        created["ledger_balances"] += balance_created

        await self.db.commit()
        return {"status": "ready", "account_set_code": account_set_code, "book_id": book.id, "created": created}

    async def revise_voucher_entries(
        self,
        voucher_id: int,
        entries: list[dict],
        actor_name: str,
        reason: str,
    ) -> dict:
        if not reason or not reason.strip():
            raise FinanceCenterError("revision reason is required")
        voucher = await self.db.get(FinVoucher, voucher_id)
        if not voucher:
            raise FinanceCenterError(f"voucher not found: {voucher_id}")
        if voucher.origin_kind != "kingdee_history":
            raise FinanceCenterError("only Kingdee history vouchers can use the history revision path")
        before = await self._voucher_snapshot(voucher)
        total_debit, total_credit = self._entry_totals(entries)
        if total_debit != total_credit:
            raise FinanceCenterError("voucher entries are not balanced")

        original_status = voucher.status
        voucher.status = "draft"
        voucher.total_debit = total_debit
        voucher.total_credit = total_credit
        await self.db.flush()

        await self.db.execute(delete(FinVoucherEntry).where(FinVoucherEntry.voucher_id == voucher.id))
        for line_no, entry in enumerate(entries, 1):
            self.db.add(
                FinVoucherEntry(
                    book_id=voucher.book_id,
                    voucher_id=voucher.id,
                    line_no=line_no,
                    account_id=entry["account_id"],
                    summary=entry["summary"],
                    debit_amount=_decimal(entry.get("debit_amount")),
                    credit_amount=_decimal(entry.get("credit_amount")),
                    currency_code=entry.get("currency_code") or "CNY",
                    exchange_rate=entry.get("exchange_rate") or Decimal("1"),
                    aux_items=entry.get("aux_items") or {},
                )
            )
        voucher.version = int(voucher.version or 1) + 1
        now = datetime.now(timezone.utc)
        await self.db.flush()

        voucher.status = original_status if original_status in {"reviewed", "posted"} else "posted"
        voucher.reviewed_at = voucher.reviewed_at or now
        voucher.posted_at = now if voucher.status == "posted" else voucher.posted_at
        await self.db.flush()

        await self._recompute_ledger_for_period(voucher.book_id, voucher.period_id)
        after = await self._voucher_snapshot(voucher)
        self.db.add(
            FinVoucherVersion(
                book_id=voucher.book_id,
                voucher_id=voucher.id,
                version=voucher.version,
                action="revise",
                before_snapshot=before,
                after_snapshot=after,
                actor_name=actor_name,
                reason=reason,
            )
        )
        self.db.add(
            FinOperationLog(
                book_id=voucher.book_id,
                actor_name=actor_name,
                action="voucher.revise",
                target_type="voucher",
                target_id=str(voucher.id),
                reason=reason,
                before_data=before,
                after_data=after,
            )
        )
        await self.db.commit()
        return {"status": voucher.status, "voucher_id": voucher.id, "version": voucher.version}

    async def _get_or_create_book(self, entity: DimLegalEntity) -> tuple[FinBook, bool]:
        existing = (
            await self.db.execute(select(FinBook).where(FinBook.legal_entity_id == entity.id))
        ).scalar_one_or_none()
        if existing:
            return existing, False
        book = FinBook(
            legal_entity_id=entity.id,
            book_code=entity.account_set_code,
            book_name=entity.entity_name,
            short_name=entity.short_name,
            start_period=entity.start_period or "1900-01",
            current_period=entity.current_period or entity.start_period or "1900-01",
            status=entity.status or "active",
            source_system="kingdee",
            source_database=entity.source_database,
            source_pk=entity.source_pk,
            import_batch_id=entity.import_batch_id,
            source_updated_at=entity.source_updated_at,
        )
        self.db.add(book)
        await self.db.flush()
        await self._ensure_source_link(
            book.id,
            "book",
            book.id,
            entity.source_database,
            entity.source_pk,
            entity.import_batch_id,
            {"dim_legal_entity_id": entity.id},
        )
        return book, True

    async def _ensure_periods(self, book_id: int, account_set_code: str) -> dict:
        period_values = set(
            (
                await self.db.execute(
                    select(DwdGlBalanceMonthly.period)
                    .where(DwdGlBalanceMonthly.source_database == account_set_code)
                    .distinct()
                )
            ).scalars()
        )
        voucher_periods = (
            await self.db.execute(
                select(DwdGlVoucher.fiscal_year, DwdGlVoucher.fiscal_period)
                .where(DwdGlVoucher.source_database == account_set_code)
                .distinct()
            )
        ).all()
        period_values.update(f"{year:04d}-{period:02d}" for year, period in voucher_periods)
        created = 0
        for period in sorted(period_values):
            existing = (
                await self.db.execute(
                    select(FinPeriod).where(FinPeriod.book_id == book_id, FinPeriod.period == period)
                )
            ).scalar_one_or_none()
            if existing:
                continue
            year, month, start_date, end_date = _period_bounds(period)
            self.db.add(
                FinPeriod(
                    book_id=book_id,
                    period=period,
                    fiscal_year=year,
                    fiscal_period=month,
                    start_date=start_date,
                    end_date=end_date,
                    status="closed",
                    close_reason="Imported closed Kingdee historical period",
                )
            )
            created += 1
        await self.db.flush()
        return {"created": created}

    async def _ensure_accounts(self, book_id: int, legal_entity_id: int) -> tuple[dict[int, int], int]:
        source_rows = (
            await self.db.execute(
                select(DimFinanceAccount)
                .where(DimFinanceAccount.legal_entity_id == legal_entity_id)
                .order_by(DimFinanceAccount.account_code)
            )
        ).scalars().all()
        created = 0
        result: dict[int, int] = {}
        for row in source_rows:
            account = (
                await self.db.execute(
                    select(FinAccount).where(FinAccount.book_id == book_id, FinAccount.source_pk == row.source_pk)
                )
            ).scalar_one_or_none()
            if not account:
                account = FinAccount(
                    book_id=book_id,
                    account_code=row.account_code,
                    account_name=row.account_name,
                    account_level=row.account_level or 1,
                    account_type=row.account_type or "unknown",
                    balance_direction=row.balance_direction or "debit",
                    is_detail=True,
                    is_cash=row.is_cash,
                    is_bank=row.is_bank,
                    is_active=row.is_active,
                    source_system=row.source_system,
                    source_database=row.source_database,
                    source_pk=row.source_pk,
                    import_batch_id=row.import_batch_id,
                    source_updated_at=row.source_updated_at,
                )
                self.db.add(account)
                await self.db.flush()
                await self._ensure_source_link(
                    book_id,
                    "account",
                    account.id,
                    row.source_database,
                    row.source_pk,
                    row.import_batch_id,
                    {"dim_finance_account_id": row.id},
                )
                created += 1
            result[row.id] = account.id
        return result, created

    async def _ensure_vouchers(
        self,
        book_id: int,
        legal_entity_id: int,
        account_set_code: str,
        account_map: dict[int, int],
    ) -> dict:
        period_map = {
            row.period: row.id
            for row in (
                await self.db.execute(select(FinPeriod).where(FinPeriod.book_id == book_id))
            ).scalars()
        }
        source_vouchers = (
            await self.db.execute(
                select(DwdGlVoucher)
                .where(DwdGlVoucher.legal_entity_id == legal_entity_id)
                .order_by(DwdGlVoucher.voucher_date, DwdGlVoucher.id)
            )
        ).scalars().all()
        created_vouchers = 0
        created_entries = 0
        for row in source_vouchers:
            existing = (
                await self.db.execute(
                    select(FinVoucher).where(FinVoucher.book_id == book_id, FinVoucher.source_pk == row.source_pk)
                )
            ).scalar_one_or_none()
            if existing:
                continue
            period = f"{row.fiscal_year:04d}-{row.fiscal_period:02d}"
            voucher = FinVoucher(
                book_id=book_id,
                period_id=period_map[period],
                voucher_no=row.voucher_no or f"{account_set_code}-{row.id}",
                voucher_group=row.voucher_group or "记",
                voucher_date=row.voucher_date,
                period=period,
                status="draft",
                origin_kind="kingdee_history",
                source_status=row.source_status,
                total_debit=_decimal(row.total_debit),
                total_credit=_decimal(row.total_credit),
                prepared_name=row.preparer_name,
                source_system=row.source_system,
                source_database=row.source_database,
                source_pk=row.source_pk,
                import_batch_id=row.import_batch_id,
                source_updated_at=row.source_updated_at,
            )
            self.db.add(voucher)
            await self.db.flush()
            await self._ensure_source_link(
                book_id,
                "voucher",
                voucher.id,
                row.source_database,
                row.source_pk,
                row.import_batch_id,
                {"dwd_gl_voucher_id": row.id},
            )
            entries = (
                await self.db.execute(
                    select(DwdGlVoucherEntry)
                    .where(DwdGlVoucherEntry.voucher_id == row.id)
                    .order_by(DwdGlVoucherEntry.line_no, DwdGlVoucherEntry.id)
                )
            ).scalars().all()
            for line_no, entry in enumerate(entries, 1):
                formal_entry = FinVoucherEntry(
                    book_id=book_id,
                    voucher_id=voucher.id,
                    line_no=line_no,
                    account_id=account_map[entry.finance_account_id],
                    summary=entry.summary or "",
                    debit_amount=_decimal(entry.debit_amount),
                    credit_amount=_decimal(entry.credit_amount),
                    currency_code=entry.currency_code or "CNY",
                    exchange_rate=entry.exchange_rate or Decimal("1"),
                    quantity=entry.quantity,
                    aux_items={"kingdee_detail_id": entry.auxiliary_detail_id} if entry.auxiliary_detail_id else {},
                )
                self.db.add(formal_entry)
                await self.db.flush()
                await self._ensure_source_link(
                    book_id,
                    "voucher_entry",
                    formal_entry.id,
                    entry.source_database,
                    entry.source_pk,
                    entry.import_batch_id,
                    {"dwd_gl_voucher_entry_id": entry.id},
                )
                created_entries += 1
            voucher.status = "posted" if row.is_posted else "reviewed" if row.is_checked else "draft"
            voucher.reviewed_at = datetime.now(timezone.utc) if voucher.status in {"reviewed", "posted"} else None
            voucher.posted_at = datetime.now(timezone.utc) if voucher.status == "posted" else None
            created_vouchers += 1
        await self.db.flush()
        return {"vouchers": created_vouchers, "voucher_entries": created_entries}

    async def _ensure_ledger_balances(self, book_id: int, legal_entity_id: int, account_map: dict[int, int]) -> int:
        period_map = {
            row.period: row.id
            for row in (
                await self.db.execute(select(FinPeriod).where(FinPeriod.book_id == book_id))
            ).scalars()
        }
        account_direction = {
            row.id: row.balance_direction
            for row in (
                await self.db.execute(select(FinAccount).where(FinAccount.book_id == book_id))
            ).scalars()
        }
        source_balances = (
            await self.db.execute(
                select(DwdGlBalanceMonthly)
                .where(DwdGlBalanceMonthly.legal_entity_id == legal_entity_id)
                .order_by(DwdGlBalanceMonthly.period, DwdGlBalanceMonthly.id)
            )
        ).scalars().all()
        created = 0
        for row in source_balances:
            account_id = account_map[row.finance_account_id]
            existing = (
                await self.db.execute(
                    select(FinLedgerBalance).where(
                        FinLedgerBalance.book_id == book_id,
                        FinLedgerBalance.account_id == account_id,
                        FinLedgerBalance.period == row.period,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue
            direction = account_direction[account_id]
            balance = FinLedgerBalance(
                book_id=book_id,
                account_id=account_id,
                period_id=period_map[row.period],
                period=row.period,
                balance_direction=direction,
                opening_amount=_balance_amount(direction, row.opening_debit, row.opening_credit),
                period_debit=_decimal(row.period_debit),
                period_credit=_decimal(row.period_credit),
                closing_amount=_balance_amount(direction, row.closing_debit, row.closing_credit),
            )
            self.db.add(balance)
            await self.db.flush()
            await self._ensure_source_link(
                book_id,
                "ledger_balance",
                balance.id,
                row.source_database,
                row.source_pk,
                row.import_batch_id,
                {"dwd_gl_balance_monthly_id": row.id},
            )
            created += 1
        return created

    async def _ensure_source_link(
        self,
        book_id: int,
        target_type: str,
        target_id: int,
        source_database: str,
        source_pk: str,
        import_batch_id: str | None,
        metadata: dict,
    ) -> None:
        exists_row = (
            await self.db.execute(
                select(FinSourceLink.id).where(
                    FinSourceLink.book_id == book_id,
                    FinSourceLink.source_system == "kingdee",
                    FinSourceLink.source_database == source_database,
                    FinSourceLink.source_pk == source_pk,
                )
            )
        ).scalar_one_or_none()
        if exists_row:
            return
        self.db.add(
            FinSourceLink(
                book_id=book_id,
                target_type=target_type,
                target_id=target_id,
                source_system="kingdee",
                source_database=source_database,
                source_pk=source_pk,
                import_batch_id=import_batch_id or "kingdee-history",
                metadata_json=metadata,
            )
        )

    def _entry_totals(self, entries: Iterable[dict]) -> tuple[Decimal, Decimal]:
        total_debit = Decimal("0.0000")
        total_credit = Decimal("0.0000")
        for entry in entries:
            debit = _decimal(entry.get("debit_amount"))
            credit = _decimal(entry.get("credit_amount"))
            if (debit > 0 and credit > 0) or (debit == 0 and credit == 0):
                raise FinanceCenterError("each voucher entry must have exactly one debit or credit amount")
            total_debit += debit
            total_credit += credit
        return total_debit, total_credit

    async def _voucher_snapshot(self, voucher: FinVoucher) -> dict:
        entries = (
            await self.db.execute(
                select(FinVoucherEntry).where(FinVoucherEntry.voucher_id == voucher.id).order_by(FinVoucherEntry.line_no)
            )
        ).scalars().all()
        return {
            "id": voucher.id,
            "voucher_no": voucher.voucher_no,
            "status": voucher.status,
            "version": voucher.version,
            "total_debit": str(voucher.total_debit),
            "total_credit": str(voucher.total_credit),
            "entries": [
                {
                    "line_no": entry.line_no,
                    "account_id": entry.account_id,
                    "summary": entry.summary,
                    "debit_amount": str(entry.debit_amount),
                    "credit_amount": str(entry.credit_amount),
                }
                for entry in entries
            ],
        }

    async def _recompute_ledger_for_period(self, book_id: int, period_id: int) -> None:
        period = await self.db.get(FinPeriod, period_id)
        if not period:
            raise FinanceCenterError(f"period not found: {period_id}")
        active_account_ids = set(
            (
                await self.db.execute(
                    select(FinVoucherEntry.account_id)
                    .join(FinVoucher, FinVoucher.id == FinVoucherEntry.voucher_id)
                    .where(
                        FinVoucherEntry.book_id == book_id,
                        FinVoucher.period_id == period_id,
                        FinVoucher.status.in_(("posted", "reversed")),
                    )
                    .distinct()
                )
            ).scalars()
        )
        existing_account_ids = set(
            (
                await self.db.execute(
                    select(FinLedgerBalance.account_id).where(
                        FinLedgerBalance.book_id == book_id,
                        FinLedgerBalance.period_id == period_id,
                    )
                )
            ).scalars()
        )
        if missing_account_ids := active_account_ids - existing_account_ids:
            accounts = (
                await self.db.execute(
                    select(FinAccount).where(FinAccount.book_id == book_id, FinAccount.id.in_(missing_account_ids))
                )
            ).scalars().all()
            for account in accounts:
                self.db.add(
                    FinLedgerBalance(
                        book_id=book_id,
                        account_id=account.id,
                        period_id=period_id,
                        period=period.period,
                        balance_direction=account.balance_direction,
                        opening_amount=Decimal("0.0000"),
                        period_debit=Decimal("0.0000"),
                        period_credit=Decimal("0.0000"),
                        closing_amount=Decimal("0.0000"),
                    )
                )
            await self.db.flush()
        balances = (
            await self.db.execute(
                select(FinLedgerBalance).where(FinLedgerBalance.book_id == book_id, FinLedgerBalance.period_id == period_id)
            )
        ).scalars().all()
        for balance in balances:
            totals = (
                await self.db.execute(
                    select(
                        func.coalesce(func.sum(FinVoucherEntry.debit_amount), 0),
                        func.coalesce(func.sum(FinVoucherEntry.credit_amount), 0),
                    )
                    .join(FinVoucher, FinVoucher.id == FinVoucherEntry.voucher_id)
                    .where(
                        FinVoucherEntry.book_id == book_id,
                        FinVoucherEntry.account_id == balance.account_id,
                        FinVoucher.period_id == period_id,
                        FinVoucher.status.in_(("posted", "reversed")),
                    )
                )
            ).one()
            balance.period_debit = _decimal(totals[0])
            balance.period_credit = _decimal(totals[1])
            if balance.balance_direction == "debit":
                balance.closing_amount = balance.opening_amount + balance.period_debit - balance.period_credit
            else:
                balance.closing_amount = balance.opening_amount + balance.period_credit - balance.period_debit
            balance.version = int(balance.version or 1) + 1

    def _statement_amount(self, statement_type: str, balance: FinLedgerBalance, account: FinAccount) -> Decimal:
        if statement_type == "balance_sheet":
            return _decimal(balance.closing_amount)
        if account.balance_direction == "debit":
            return _decimal(balance.period_debit) - _decimal(balance.period_credit)
        return _decimal(balance.period_credit) - _decimal(balance.period_debit)

    async def _upsert_dm_statement_row(
        self,
        book: FinBook,
        period: str,
        statement_type: str,
        line: FinStatementLine,
        amount: Decimal,
        status: str,
        issues: list[dict],
    ) -> None:
        row = (
            await self.db.execute(
                select(DmFinanceStatementMonthly).where(
                    DmFinanceStatementMonthly.legal_entity_id == book.legal_entity_id,
                    DmFinanceStatementMonthly.period == period,
                    DmFinanceStatementMonthly.statement_type == statement_type,
                    DmFinanceStatementMonthly.line_code == line.line_code,
                )
            )
        ).scalar_one_or_none()
        values = {
            "line_name": line.line_name,
            "display_order": line.display_order,
            "current_amount": amount,
            "year_to_date_amount": amount,
            "status": status,
            "quality_issues": issues,
            "import_batch_id": "finance-center",
            "source_system": "finance_center",
            "source_database": book.book_code,
            "source_pk": f"fin:{book.id}:{period}:{statement_type}:{line.line_code}",
            "source_updated_at": datetime.now(timezone.utc),
        }
        if row:
            for key, value in values.items():
                setattr(row, key, value)
        else:
            self.db.add(
                DmFinanceStatementMonthly(
                    legal_entity_id=book.legal_entity_id,
                    period=period,
                    statement_type=statement_type,
                    line_code=line.line_code,
                    **values,
                )
            )
