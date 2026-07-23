"""Finance-center operational services mirroring the Mu Ma Ren finance module.

This module extends :class:`app.services.finance_center_service.FinanceCenterService`
with auxiliary accounting, ledger queries, voucher review/unpost, period
close/reopen, receivable/payable, cashier, fixed asset, invoice, payroll,
tax, auto-entry and operation-log capabilities. All write operations remain
draft-first and require manual review before they affect the ledger.
"""

from __future__ import annotations

import calendar
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance_core import (
    FinAccount,
    FinAuxCategory,
    FinAuxItem,
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
from app.models.finance_operations import (
    FinAutoEntryRule,
    FinAutoEntryRun,
    FinBankTransaction,
    FinCashAccount,
    FinDepreciation,
    FinFixedAsset,
    FinInvoice,
    FinPayable,
    FinPayroll,
    FinReceivable,
    FinReconciliation,
    FinSettlement,
    FinTaxRecord,
)
from app.services.finance_center_service import (
    FinanceCenterError,
    FinanceCenterService,
    _balance_amount,
    _decimal,
    _period_bounds,
)


def _actor_name(user) -> str:
    return str(getattr(user, "username", None) or getattr(user, "name", None) or getattr(user, "id", "system"))


def _hash_payload(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class FinanceCenterOpsService:
    """Operational extensions on top of :class:`FinanceCenterService`."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.core = FinanceCenterService(db)

    # ------------------------------------------------------------------ #
    # Books / periods                                                     #
    # ------------------------------------------------------------------ #

    async def list_books(self) -> list[dict]:
        rows = (await self.db.execute(select(FinBook).order_by(FinBook.book_code))).scalars().all()
        return [self._book_dict(row) for row in rows]

    async def get_book(self, book_id: int) -> dict:
        book = await self._require_book(book_id)
        return self._book_dict(book)

    async def list_periods(self, book_id: int) -> list[dict]:
        await self._require_book(book_id)
        rows = (
            await self.db.execute(
                select(FinPeriod).where(FinPeriod.book_id == book_id).order_by(FinPeriod.period.desc())
            )
        ).scalars().all()
        return [
            {
                "period_id": row.id,
                "period": row.period,
                "fiscal_year": row.fiscal_year,
                "fiscal_period": row.fiscal_period,
                "status": row.status,
                "closed_at": row.closed_at.isoformat() if row.closed_at else None,
                "close_reason": row.close_reason,
                "version": row.version,
            }
            for row in rows
        ]

    async def close_period(self, book_id: int, period: str, actor_name: str, reason: str) -> dict:
        if not reason or not reason.strip():
            raise FinanceCenterError("close period reason is required")
        book = await self._require_book(book_id)
        period_row = await self._get_period(book_id, period)
        if period_row.status == "closed":
            return {"period_id": period_row.id, "status": "closed"}
        # trial balance check: every posted voucher in this period must be balanced
        imbalanced = await self._find_imbalanced_vouchers(book_id, period_row.id)
        if imbalanced:
            raise FinanceCenterError(
                f"cannot close period with unbalanced vouchers: {[v['voucher_no'] for v in imbalanced]}"
            )
        # ensure all accounts with movement have ledger balances
        await self.core._recompute_ledger_for_period(book_id, period_row.id)
        period_row.status = "closed"
        period_row.closed_at = datetime.now(timezone.utc)
        period_row.close_reason = reason
        period_row.version = int(period_row.version or 1) + 1
        if book.current_period == period:
            # advance book current_period to the next calendar month if it exists
            next_period = self._next_period(period)
            existing = await self._get_period(book_id, next_period)
            if existing and existing.status == "open":
                book.current_period = next_period
                book.version = int(book.version or 1) + 1
        self.db.add(
            FinOperationLog(
                book_id=book_id,
                actor_name=actor_name,
                action="period.close",
                target_type="period",
                target_id=str(period_row.id),
                reason=reason,
                after_data={"period": period, "status": "closed"},
            )
        )
        await self.db.commit()
        return {"period_id": period_row.id, "status": period_row.status}

    async def reopen_period(self, book_id: int, period: str, actor_name: str, reason: str) -> dict:
        if not reason or not reason.strip():
            raise FinanceCenterError("reopen period reason is required")
        period_row = await self._get_period(book_id, period)
        if period_row.status != "closed":
            raise FinanceCenterError(f"period is not closed: {period}")
        # ensure no later period is already closed (must reopen in reverse order)
        later = (
            await self.db.execute(
                select(FinPeriod)
                .where(FinPeriod.book_id == book_id, FinPeriod.period > period, FinPeriod.status == "closed")
                .order_by(FinPeriod.period)
            )
        ).scalars().first()
        if later:
            raise FinanceCenterError(
                f"must reopen later period first: {later.period}"
            )
        period_row.status = "open"
        period_row.closed_at = None
        period_row.close_reason = None
        period_row.version = int(period_row.version or 1) + 1
        self.db.add(
            FinOperationLog(
                book_id=book_id,
                actor_name=actor_name,
                action="period.reopen",
                target_type="period",
                target_id=str(period_row.id),
                reason=reason,
                after_data={"period": period, "status": "open"},
            )
        )
        await self.db.commit()
        return {"period_id": period_row.id, "status": period_row.status}

    # ------------------------------------------------------------------ #
    # Accounts / auxiliary                                                #
    # ------------------------------------------------------------------ #

    async def list_accounts(self, book_id: int, parent_id: int | None = None, only_active: bool = True) -> list[dict]:
        await self._require_book(book_id)
        stmt = select(FinAccount).where(FinAccount.book_id == book_id)
        if parent_id is not None:
            stmt = stmt.where(FinAccount.parent_id == parent_id)
        else:
            stmt = stmt.where(FinAccount.parent_id.is_(None))
        if only_active:
            stmt = stmt.where(FinAccount.is_active.is_(True))
        stmt = stmt.order_by(FinAccount.account_code)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [self._account_dict(row) for row in rows]

    async def list_aux_categories(self, book_id: int) -> list[dict]:
        await self._require_book(book_id)
        rows = (
            await self.db.execute(
                select(FinAuxCategory).where(FinAuxCategory.book_id == book_id).order_by(FinAuxCategory.category_code)
            )
        ).scalars().all()
        return [
            {
                "id": row.id,
                "category_code": row.category_code,
                "category_name": row.category_name,
                "status": row.status,
            }
            for row in rows
        ]

    async def upsert_aux_category(self, book_id: int, category_code: str, category_name: str, status: str = "active") -> dict:
        await self._require_book(book_id)
        row = (
            await self.db.execute(
                select(FinAuxCategory).where(
                    FinAuxCategory.book_id == book_id, FinAuxCategory.category_code == category_code
                )
            )
        ).scalar_one_or_none()
        if row:
            row.category_name = category_name
            row.status = status
        else:
            row = FinAuxCategory(
                book_id=book_id,
                category_code=category_code,
                category_name=category_name,
                status=status,
            )
            self.db.add(row)
        await self.db.commit()
        return {"category_id": row.id, "category_code": row.category_code}

    async def list_aux_items(self, book_id: int, category_id: int | None = None) -> list[dict]:
        await self._require_book(book_id)
        stmt = select(FinAuxItem).where(FinAuxItem.book_id == book_id)
        if category_id is not None:
            stmt = stmt.where(FinAuxItem.category_id == category_id)
        stmt = stmt.order_by(FinAuxItem.item_code)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            {
                "id": row.id,
                "category_id": row.category_id,
                "item_code": row.item_code,
                "item_name": row.item_name,
                "target_type": row.target_type,
                "target_code": row.target_code,
                "status": row.status,
            }
            for row in rows
        ]

    async def upsert_aux_item(
        self,
        book_id: int,
        category_id: int,
        item_code: str,
        item_name: str,
        target_type: str | None = None,
        target_code: str | None = None,
    ) -> dict:
        await self._require_book(book_id)
        category = await self.db.get(FinAuxCategory, category_id)
        if not category or category.book_id != book_id:
            raise FinanceCenterError(f"aux category not found: {category_id}")
        row = (
            await self.db.execute(
                select(FinAuxItem).where(
                    FinAuxItem.book_id == book_id,
                    FinAuxItem.category_id == category_id,
                    FinAuxItem.item_code == item_code,
                )
            )
        ).scalar_one_or_none()
        if row:
            row.item_name = item_name
            row.target_type = target_type
            row.target_code = target_code
            row.status = "active"
        else:
            row = FinAuxItem(
                book_id=book_id,
                category_id=category_id,
                item_code=item_code,
                item_name=item_name,
                target_type=target_type,
                target_code=target_code,
            )
            self.db.add(row)
        await self.db.commit()
        return {"aux_item_id": row.id, "item_code": row.item_code}

    # ------------------------------------------------------------------ #
    # Voucher lifecycle: review / unpost / delete / list / get            #
    # ------------------------------------------------------------------ #

    async def review_voucher(self, voucher_id: int, actor_name: str, reason: str) -> dict:
        if not reason or not reason.strip():
            raise FinanceCenterError("review reason is required")
        voucher = await self._require_voucher(voucher_id)
        if voucher.status != "draft":
            raise FinanceCenterError(f"only draft vouchers can be reviewed: {voucher.status}")
        entries = await self._voucher_entries(voucher.id)
        total_debit, total_credit = self._entry_totals_from_rows(entries)
        if not entries or total_debit != total_credit:
            raise FinanceCenterError("voucher is not balanced")
        before = await self.core._voucher_snapshot(voucher)
        voucher.status = "reviewed"
        voucher.reviewed_at = datetime.now(timezone.utc)
        voucher.version = int(voucher.version or 1) + 1
        await self.db.flush()
        after = await self.core._voucher_snapshot(voucher)
        self.db.add(
            FinVoucherVersion(
                book_id=voucher.book_id,
                voucher_id=voucher.id,
                version=voucher.version,
                action="review",
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
                action="voucher.review",
                target_type="voucher",
                target_id=str(voucher.id),
                reason=reason,
                before_data=before,
                after_data=after,
            )
        )
        await self.db.commit()
        return {"status": voucher.status, "voucher_id": voucher.id, "version": voucher.version}

    async def unpost_voucher(self, voucher_id: int, actor_name: str, reason: str) -> dict:
        if not reason or not reason.strip():
            raise FinanceCenterError("unpost reason is required")
        voucher = await self._require_voucher(voucher_id)
        if voucher.status != "posted":
            raise FinanceCenterError(f"only posted vouchers can be unposted: {voucher.status}")
        if voucher.origin_kind == "kingdee_history":
            raise FinanceCenterError("kingdee history vouchers cannot be unposted")
        period = await self.db.get(FinPeriod, voucher.period_id)
        if period and period.status == "closed":
            raise FinanceCenterError(f"period is closed: {period.period}")
        before = await self.core._voucher_snapshot(voucher)
        voucher.status = "draft"
        voucher.posted_at = None
        voucher.version = int(voucher.version or 1) + 1
        await self.db.flush()
        await self.core._recompute_ledger_for_period(voucher.book_id, voucher.period_id)
        after = await self.core._voucher_snapshot(voucher)
        self.db.add(
            FinVoucherVersion(
                book_id=voucher.book_id,
                voucher_id=voucher.id,
                version=voucher.version,
                action="unpost",
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
                action="voucher.unpost",
                target_type="voucher",
                target_id=str(voucher.id),
                reason=reason,
                before_data=before,
                after_data=after,
            )
        )
        await self.db.commit()
        return {"status": voucher.status, "voucher_id": voucher.id, "version": voucher.version}

    async def delete_voucher(self, voucher_id: int, actor_name: str, reason: str) -> dict:
        if not reason or not reason.strip():
            raise FinanceCenterError("delete reason is required")
        voucher = await self._require_voucher(voucher_id)
        if voucher.status != "draft":
            raise FinanceCenterError(f"only draft vouchers can be deleted: {voucher.status}")
        if voucher.origin_kind == "kingdee_history":
            raise FinanceCenterError("kingdee history vouchers cannot be deleted")
        before = await self.core._voucher_snapshot(voucher)
        await self.db.execute(delete(FinVoucherEntry).where(FinVoucherEntry.voucher_id == voucher.id))
        await self.db.execute(delete(FinVoucherVersion).where(FinVoucherVersion.voucher_id == voucher.id))
        await self.db.delete(voucher)
        self.db.add(
            FinOperationLog(
                book_id=voucher.book_id,
                actor_name=actor_name,
                action="voucher.delete",
                target_type="voucher",
                target_id=str(voucher.id),
                reason=reason,
                before_data=before,
            )
        )
        await self.db.commit()
        return {"deleted": True, "voucher_id": voucher_id}

    async def list_vouchers(
        self,
        book_id: int,
        period: str | None = None,
        status: str | None = None,
        origin_kind: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        await self._require_book(book_id)
        stmt = select(FinVoucher).where(FinVoucher.book_id == book_id)
        if period:
            stmt = stmt.where(FinVoucher.period == period)
        if status:
            stmt = stmt.where(FinVoucher.status == status)
        if origin_kind:
            stmt = stmt.where(FinVoucher.origin_kind == origin_kind)
        total = (
            await self.db.execute(
                select(func.count()).select_from(stmt.subquery())
            )
        ).scalar_one()
        rows = (
            await self.db.execute(
                stmt.order_by(FinVoucher.voucher_date.desc(), FinVoucher.id.desc())
                .offset(max(page - 1, 0) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return {
            "items": [self._voucher_summary(row) for row in rows],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    async def get_voucher(self, voucher_id: int) -> dict:
        voucher = await self._require_voucher(voucher_id)
        entries = await self._voucher_entries(voucher.id)
        account_map = await self._account_map(voucher.book_id, [e.account_id for e in entries])
        return {
            **self._voucher_summary(voucher),
            "entries": [
                {
                    "line_no": e.line_no,
                    "account_id": e.account_id,
                    "account_code": account_map.get(e.account_id, {}).get("account_code"),
                    "account_name": account_map.get(e.account_id, {}).get("account_name"),
                    "summary": e.summary,
                    "debit_amount": float(e.debit_amount or 0),
                    "credit_amount": float(e.credit_amount or 0),
                    "currency_code": e.currency_code,
                    "aux_items": e.aux_items or {},
                }
                for e in entries
            ],
        }

    # ------------------------------------------------------------------ #
    # Ledger queries                                                     #
    # ------------------------------------------------------------------ #

    async def list_ledger_balances(self, book_id: int, period: str, account_id: int | None = None) -> list[dict]:
        await self._require_book(book_id)
        stmt = (
            select(FinLedgerBalance, FinAccount)
            .join(FinAccount, FinAccount.id == FinLedgerBalance.account_id)
            .where(FinLedgerBalance.book_id == book_id, FinLedgerBalance.period == period)
        )
        if account_id is not None:
            stmt = stmt.where(FinLedgerBalance.account_id == account_id)
        stmt = stmt.order_by(FinAccount.account_code)
        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "account_id": balance.account_id,
                "account_code": account.account_code,
                "account_name": account.account_name,
                "balance_direction": balance.balance_direction,
                "opening_amount": float(balance.opening_amount or 0),
                "period_debit": float(balance.period_debit or 0),
                "period_credit": float(balance.period_credit or 0),
                "closing_amount": float(balance.closing_amount or 0),
            }
            for balance, account in rows
        ]

    async def general_ledger(
        self,
        book_id: int,
        account_id: int,
        start_period: str,
        end_period: str,
    ) -> dict:
        await self._require_book(book_id)
        account = await self._require_account(book_id, account_id)
        balances = (
            await self.db.execute(
                select(FinLedgerBalance)
                .where(
                    FinLedgerBalance.book_id == book_id,
                    FinLedgerBalance.account_id == account_id,
                    FinLedgerBalance.period >= start_period,
                    FinLedgerBalance.period <= end_period,
                )
                .order_by(FinLedgerBalance.period)
            )
        ).scalars().all()
        period_ids = [b.period_id for b in balances]
        vouchers: list[FinVoucher] = []
        entries: list[FinVoucherEntry] = []
        if period_ids:
            voucher_rows = (
                await self.db.execute(
                    select(FinVoucher)
                    .where(
                        FinVoucher.book_id == book_id,
                        FinVoucher.period_id.in_(period_ids),
                        FinVoucher.status.in_(("posted", "reversed")),
                    )
                    .order_by(FinVoucher.voucher_date, FinVoucher.id)
                )
            ).scalars().all()
            vouchers = list(voucher_rows)
            if vouchers:
                entries = list(
                    (
                        await self.db.execute(
                            select(FinVoucherEntry)
                            .where(
                                FinVoucherEntry.account_id == account_id,
                                FinVoucherEntry.voucher_id.in_([v.id for v in vouchers]),
                            )
                            .order_by(FinVoucherEntry.line_no)
                        )
                    ).scalars()
                )
        by_voucher = {e.voucher_id: e for e in entries}
        lines = []
        running = Decimal("0.0000")
        for balance in balances:
            running = _decimal(balance.closing_amount)
            lines.append(
                {
                    "period": balance.period,
                    "kind": "balance",
                    "opening_amount": float(balance.opening_amount or 0),
                    "period_debit": float(balance.period_debit or 0),
                    "period_credit": float(balance.period_credit or 0),
                    "closing_amount": float(balance.closing_amount or 0),
                }
            )
            for voucher in [v for v in vouchers if v.period_id == balance.period_id]:
                entry = by_voucher.get(voucher.id)
                if not entry:
                    continue
                lines.append(
                    {
                        "period": balance.period,
                        "kind": "voucher",
                        "voucher_id": voucher.id,
                        "voucher_no": voucher.voucher_no,
                        "voucher_date": voucher.voucher_date.isoformat() if voucher.voucher_date else None,
                        "summary": entry.summary,
                        "debit_amount": float(entry.debit_amount or 0),
                        "credit_amount": float(entry.credit_amount or 0),
                    }
                )
        return {
            "account_id": account.id,
            "account_code": account.account_code,
            "account_name": account.account_name,
            "balance_direction": account.balance_direction,
            "lines": lines,
            "final_closing_amount": float(running),
        }

    async def subsidiary_ledger(
        self,
        book_id: int,
        account_id: int,
        start_period: str,
        end_period: str,
    ) -> dict:
        # subsidiary ledger uses voucher entries filtered by account; aux_items carries the counterparty
        result = await self.general_ledger(book_id, account_id, start_period, end_period)
        result["entries"] = [line for line in result["lines"] if line["kind"] == "voucher"]
        return result

    async def trial_balance(self, book_id: int, period: str) -> dict:
        await self._require_book(book_id)
        balances = await self.list_ledger_balances(book_id, period)
        debit_total = sum(Decimal(str(b["opening_amount"])) for b in balances if b["balance_direction"] == "debit")
        credit_total = sum(Decimal(str(b["opening_amount"])) for b in balances if b["balance_direction"] == "credit")
        period_debit = sum(Decimal(str(b["period_debit"])) for b in balances)
        period_credit = sum(Decimal(str(b["period_credit"])) for b in balances)
        closing_debit = sum(Decimal(str(b["closing_amount"])) for b in balances if b["balance_direction"] == "debit")
        closing_credit = sum(Decimal(str(b["closing_amount"])) for b in balances if b["balance_direction"] == "credit")
        return {
            "period": period,
            "items": balances,
            "totals": {
                "opening_debit": float(debit_total),
                "opening_credit": float(credit_total),
                "period_debit": float(period_debit),
                "period_credit": float(period_credit),
                "closing_debit": float(closing_debit),
                "closing_credit": float(closing_credit),
                "balanced": debit_total == credit_total
                and period_debit == period_credit
                and closing_debit == closing_credit,
            },
        }

    async def profit_loss_carryover(self, book_id: int, period: str, actor_name: str, reason: str) -> dict:
        """Close revenue/expense accounts to retained earnings for the period."""
        if not reason or not reason.strip():
            raise FinanceCenterError("profit/loss carryover reason is required")
        book = await self._require_book(book_id)
        period_row = await self._get_period(book_id, period)
        if period_row.status != "open":
            raise FinanceCenterError(f"period must be open to carryover: {period}")
        accounts = (
            await self.db.execute(
                select(FinAccount).where(
                    FinAccount.book_id == book_id,
                    FinAccount.account_type.in_(("revenue", "expense")),
                    FinAccount.is_active.is_(True),
                )
            )
        ).scalars().all()
        if not accounts:
            return {"status": "no_action", "items": []}
        balances = (
            await self.db.execute(
                select(FinLedgerBalance).where(
                    FinLedgerBalance.book_id == book_id,
                    FinLedgerBalance.period == period,
                    FinLedgerBalance.account_id.in_([a.id for a in accounts]),
                )
            )
        ).scalars().all()
        lines = []
        net = Decimal("0.0000")
        for account, balance in zip(accounts, balances):
            closing = _decimal(balance.closing_amount)
            if closing == 0:
                continue
            debit = closing if account.balance_direction == "credit" else Decimal("0.0000")
            credit = closing if account.balance_direction == "debit" else Decimal("0.0000")
            # revenue (credit direction) -> debit closing to zero it out
            # expense (debit direction) -> credit closing to zero it out
            lines.append(
                {
                    "account_id": account.id,
                    "account_code": account.account_code,
                    "account_name": account.account_name,
                    "debit_amount": float(debit),
                    "credit_amount": float(credit),
                    "summary": f"期末损益结转 - {account.account_name}",
                }
            )
            net += closing if account.account_type == "revenue" else -closing
        if not lines:
            return {"status": "no_action", "items": []}
        # locate retained earnings account (profit_undistributed) - skip if not mapped
        ret_account = (
            await self.db.execute(
                select(FinAccount)
                .where(
                    FinAccount.book_id == book_id,
                    FinAccount.account_type == "equity",
                    FinAccount.account_code.like("4104%"),
                )
                .order_by(FinAccount.account_code)
                .limit(1)
            )
        ).scalar_one_or_none()
        if not ret_account:
            raise FinanceCenterError("retained earnings account (4104*) not configured for this book")
        if net > 0:
            lines.append(
                {
                    "account_id": ret_account.id,
                    "account_code": ret_account.account_code,
                    "account_name": ret_account.account_name,
                    "debit_amount": 0,
                    "credit_amount": float(net),
                    "summary": "期末损益结转 - 净利润转入未分配利润",
                }
            )
        elif net < 0:
            lines.append(
                {
                    "account_id": ret_account.id,
                    "account_code": ret_account.account_code,
                    "account_name": ret_account.account_name,
                    "debit_amount": float(-net),
                    "credit_amount": 0,
                    "summary": "期末损益结转 - 净亏损转入未分配利润",
                }
            )
        voucher_no = f"PLC-{period}-{book.book_code}"
        existing = (
            await self.db.execute(
                select(FinVoucher).where(
                    FinVoucher.book_id == book_id,
                    FinVoucher.voucher_no == voucher_no,
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise FinanceCenterError(f"carryover voucher already exists: {voucher_no}")
        result = await self.core.create_voucher(
            book_id=book_id,
            period=period,
            voucher_no=voucher_no,
            voucher_date=period_row.end_date,
            entries=lines,
            actor_name=actor_name,
            reason=reason,
            origin_kind="period_carryover",
        )
        await self.core.post_voucher(result["voucher_id"], actor_name=actor_name, reason=reason)
        return {"status": "posted", "voucher_id": result["voucher_id"], "net": float(net)}

    # ------------------------------------------------------------------ #
    # Receivables / payables / settlements                               #
    # ------------------------------------------------------------------ #

    async def create_receivable(
        self,
        book_id: int,
        document_no: str,
        counterparty_aux_id: int,
        business_date: date,
        original_amount: Decimal,
        currency_code: str = "CNY",
        due_date: date | None = None,
        actor_name: str = "system",
        source_system: str = "manual",
        source_database: str = "",
        source_pk: str | None = None,
    ) -> dict:
        book = await self._require_book(book_id)
        if _decimal(original_amount) <= 0:
            raise FinanceCenterError("original_amount must be positive")
        await self._require_aux_item(book_id, counterparty_aux_id)
        draft = await self.core.create_voucher(
            book_id=book_id,
            period=self._period_for_date(business_date),
            voucher_no=f"AR-{document_no}",
            voucher_date=business_date,
            entries=[
                {
                    "account_id": await self._account_id_by_code(book_id, "1122"),
                    "summary": f"应收账款 - {document_no}",
                    "debit_amount": original_amount,
                    "credit_amount": 0,
                    "aux_items": {"counterparty_aux_id": counterparty_aux_id},
                },
                {
                    "account_id": await self._account_id_by_code(book_id, "6001"),
                    "summary": f"主营业务收入 - {document_no}",
                    "debit_amount": 0,
                    "credit_amount": original_amount,
                    "aux_items": {"counterparty_aux_id": counterparty_aux_id},
                },
            ],
            actor_name=actor_name,
            reason=f"create receivable {document_no}",
            origin_kind="receivable_draft",
        )
        row = FinReceivable(
            book_id=book_id,
            draft_voucher_id=draft["voucher_id"],
            document_no=document_no,
            counterparty_aux_id=counterparty_aux_id,
            business_date=business_date,
            due_date=due_date,
            currency_code=currency_code,
            original_amount=_decimal(original_amount),
            settled_amount=Decimal("0.0000"),
            outstanding_amount=_decimal(original_amount),
            status="open",
            source_system=source_system,
            source_database=source_database,
            source_pk=source_pk or f"manual:{document_no}",
        )
        self.db.add(row)
        await self.db.flush()
        await self._ensure_source_link(book_id, "receivable", row.id, source_database, source_pk or f"manual:{document_no}", "manual")
        await self.db.commit()
        return {"receivable_id": row.id, "voucher_id": draft["voucher_id"], "outstanding": float(row.outstanding_amount)}

    async def list_receivables(
        self,
        book_id: int,
        status: str | None = None,
        counterparty_aux_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        await self._require_book(book_id)
        stmt = select(FinReceivable).where(FinReceivable.book_id == book_id)
        if status:
            stmt = stmt.where(FinReceivable.status == status)
        if counterparty_aux_id:
            stmt = stmt.where(FinReceivable.counterparty_aux_id == counterparty_aux_id)
        total = (await self.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (
            await self.db.execute(
                stmt.order_by(FinReceivable.business_date.desc(), FinReceivable.id.desc())
                .offset(max(page - 1, 0) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return {
            "items": [self._receivable_dict(r) for r in rows],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    async def create_payable(
        self,
        book_id: int,
        document_no: str,
        counterparty_aux_id: int,
        business_date: date,
        original_amount: Decimal,
        currency_code: str = "CNY",
        due_date: date | None = None,
        actor_name: str = "system",
        source_system: str = "manual",
        source_database: str = "",
        source_pk: str | None = None,
    ) -> dict:
        await self._require_book(book_id)
        if _decimal(original_amount) <= 0:
            raise FinanceCenterError("original_amount must be positive")
        await self._require_aux_item(book_id, counterparty_aux_id)
        draft = await self.core.create_voucher(
            book_id=book_id,
            period=self._period_for_date(business_date),
            voucher_no=f"AP-{document_no}",
            voucher_date=business_date,
            entries=[
                {
                    "account_id": await self._account_id_by_code(book_id, "6601"),
                    "summary": f"采购成本 - {document_no}",
                    "debit_amount": original_amount,
                    "credit_amount": 0,
                    "aux_items": {"counterparty_aux_id": counterparty_aux_id},
                },
                {
                    "account_id": await self._account_id_by_code(book_id, "2202"),
                    "summary": f"应付账款 - {document_no}",
                    "debit_amount": 0,
                    "credit_amount": original_amount,
                    "aux_items": {"counterparty_aux_id": counterparty_aux_id},
                },
            ],
            actor_name=actor_name,
            reason=f"create payable {document_no}",
            origin_kind="payable_draft",
        )
        row = FinPayable(
            book_id=book_id,
            draft_voucher_id=draft["voucher_id"],
            document_no=document_no,
            counterparty_aux_id=counterparty_aux_id,
            business_date=business_date,
            due_date=due_date,
            currency_code=currency_code,
            original_amount=_decimal(original_amount),
            settled_amount=Decimal("0.0000"),
            outstanding_amount=_decimal(original_amount),
            status="open",
            source_system=source_system,
            source_database=source_database,
            source_pk=source_pk or f"manual:{document_no}",
        )
        self.db.add(row)
        await self.db.flush()
        await self._ensure_source_link(book_id, "payable", row.id, source_database, source_pk or f"manual:{document_no}", "manual")
        await self.db.commit()
        return {"payable_id": row.id, "voucher_id": draft["voucher_id"], "outstanding": float(row.outstanding_amount)}

    async def list_payables(
        self,
        book_id: int,
        status: str | None = None,
        counterparty_aux_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        await self._require_book(book_id)
        stmt = select(FinPayable).where(FinPayable.book_id == book_id)
        if status:
            stmt = stmt.where(FinPayable.status == status)
        if counterparty_aux_id:
            stmt = stmt.where(FinPayable.counterparty_aux_id == counterparty_aux_id)
        total = (await self.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (
            await self.db.execute(
                stmt.order_by(FinPayable.business_date.desc(), FinPayable.id.desc())
                .offset(max(page - 1, 0) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return {
            "items": [self._payable_dict(r) for r in rows],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    async def create_settlement(
        self,
        book_id: int,
        settlement_type: str,
        receivable_id: int | None,
        payable_id: int | None,
        settlement_date: date,
        amount: Decimal,
        actor_name: str,
        reason: str,
    ) -> dict:
        if not reason or not reason.strip():
            raise FinanceCenterError("settlement reason is required")
        if (receivable_id is None) == (payable_id is None):
            raise FinanceCenterError("must specify exactly one of receivable_id or payable_id")
        if _decimal(amount) <= 0:
            raise FinanceCenterError("settlement amount must be positive")
        await self._require_book(book_id)
        target: FinReceivable | FinPayable | None = None
        if receivable_id:
            target = await self.db.get(FinReceivable, receivable_id)
            if not target or target.book_id != book_id:
                raise FinanceCenterError(f"receivable not found: {receivable_id}")
            if _decimal(amount) > _decimal(target.outstanding_amount):
                raise FinanceCenterError("settlement amount exceeds outstanding receivable")
        else:
            target = await self.db.get(FinPayable, payable_id)
            if not target or target.book_id != book_id:
                raise FinanceCenterError(f"payable not found: {payable_id}")
            if _decimal(amount) > _decimal(target.outstanding_amount):
                raise FinanceCenterError("settlement amount exceeds outstanding payable")
        settlement_no = f"ST-{settlement_date.strftime('%Y%m%d')}-{(receivable_id or payable_id)}"
        row = FinSettlement(
            book_id=book_id,
            settlement_no=settlement_no,
            settlement_type=settlement_type,
            receivable_id=receivable_id,
            payable_id=payable_id,
            settlement_date=settlement_date,
            amount=_decimal(amount),
            status="active",
            actor_id=None,
            reason=reason,
        )
        self.db.add(row)
        target.settled_amount = _decimal(target.settled_amount) + _decimal(amount)
        target.outstanding_amount = _decimal(target.outstanding_amount) - _decimal(amount)
        if _decimal(target.outstanding_amount) == 0:
            target.status = "settled"
        target.version = int(target.version or 1) + 1
        await self.db.flush()
        self.db.add(
            FinOperationLog(
                book_id=book_id,
                actor_name=actor_name,
                action="settlement.create",
                target_type="settlement",
                target_id=str(row.id),
                reason=reason,
                after_data={
                    "settlement_no": settlement_no,
                    "receivable_id": receivable_id,
                    "payable_id": payable_id,
                    "amount": float(amount),
                },
            )
        )
        await self.db.commit()
        return {"settlement_id": row.id, "settlement_no": settlement_no, "outstanding": float(target.outstanding_amount)}

    async def list_settlements(self, book_id: int, page: int = 1, page_size: int = 20) -> dict:
        await self._require_book(book_id)
        stmt = select(FinSettlement).where(FinSettlement.book_id == book_id)
        total = (await self.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (
            await self.db.execute(
                stmt.order_by(FinSettlement.settlement_date.desc(), FinSettlement.id.desc())
                .offset(max(page - 1, 0) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return {
            "items": [
                {
                    "id": r.id,
                    "settlement_no": r.settlement_no,
                    "settlement_type": r.settlement_type,
                    "receivable_id": r.receivable_id,
                    "payable_id": r.payable_id,
                    "settlement_date": r.settlement_date.isoformat() if r.settlement_date else None,
                    "amount": float(r.amount or 0),
                    "status": r.status,
                    "reason": r.reason,
                }
                for r in rows
            ],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    async def aging_analysis(self, book_id: int, as_of: date | None = None, kind: str = "receivable") -> dict:
        await self._require_book(book_id)
        if kind not in {"receivable", "payable"}:
            raise FinanceCenterError("kind must be receivable or payable")
        model = FinReceivable if kind == "receivable" else FinPayable
        rows = (
            await self.db.execute(
                select(model).where(model.book_id == book_id, model.status == "open")
            )
        ).scalars().all()
        as_of = as_of or date.today()
        buckets = {"current": Decimal("0"), "1_30": Decimal("0"), "31_60": Decimal("0"), "61_90": Decimal("0"), "90+": Decimal("0")}
        for r in rows:
            outstanding = _decimal(r.outstanding_amount)
            if outstanding == 0:
                continue
            due = r.due_date
            if not due:
                buckets["current"] += outstanding
                continue
            days = (as_of - due).days
            if days <= 0:
                buckets["current"] += outstanding
            elif days <= 30:
                buckets["1_30"] += outstanding
            elif days <= 60:
                buckets["31_60"] += outstanding
            elif days <= 90:
                buckets["61_90"] += outstanding
            else:
                buckets["90+"] += outstanding
        return {
            "as_of": as_of.isoformat(),
            "kind": kind,
            "buckets": {k: float(v) for k, v in buckets.items()},
            "total": float(sum(buckets.values(), Decimal("0"))),
        }

    # ------------------------------------------------------------------ #
    # Cashier                                                            #
    # ------------------------------------------------------------------ #

    async def list_cash_accounts(self, book_id: int) -> list[dict]:
        await self._require_book(book_id)
        rows = (
            await self.db.execute(
                select(FinCashAccount).where(FinCashAccount.book_id == book_id).order_by(FinCashAccount.account_code)
            )
        ).scalars().all()
        return [self._cash_account_dict(r) for r in rows]

    async def upsert_cash_account(
        self,
        book_id: int,
        account_code: str,
        account_name: str,
        account_type: str,
        ledger_account_id: int,
        bank_name: str | None = None,
        bank_account_masked: str | None = None,
        currency_code: str = "CNY",
    ) -> dict:
        await self._require_book(book_id)
        await self._require_account(book_id, ledger_account_id)
        row = (
            await self.db.execute(
                select(FinCashAccount).where(
                    FinCashAccount.book_id == book_id, FinCashAccount.account_code == account_code
                )
            )
        ).scalar_one_or_none()
        if row:
            row.account_name = account_name
            row.account_type = account_type
            row.ledger_account_id = ledger_account_id
            row.bank_name = bank_name
            row.bank_account_masked = bank_account_masked
            row.currency_code = currency_code
            row.status = "active"
        else:
            row = FinCashAccount(
                book_id=book_id,
                account_code=account_code,
                account_name=account_name,
                account_type=account_type,
                ledger_account_id=ledger_account_id,
                bank_name=bank_name,
                bank_account_masked=bank_account_masked,
                currency_code=currency_code,
            )
            self.db.add(row)
        await self.db.commit()
        return {"cash_account_id": row.id, "account_code": row.account_code}

    async def create_bank_transaction(
        self,
        book_id: int,
        cash_account_id: int,
        transaction_date: date,
        amount: Decimal,
        direction: str,
        counterparty_name: str | None = None,
        reference_no: str | None = None,
        summary: str | None = None,
        actor_name: str = "system",
        source_system: str = "manual",
        source_database: str = "",
        source_pk: str | None = None,
    ) -> dict:
        await self._require_book(book_id)
        cash = await self._require_cash_account(book_id, cash_account_id)
        if direction not in {"in", "out"}:
            raise FinanceCenterError("direction must be 'in' or 'out'")
        if _decimal(amount) <= 0:
            raise FinanceCenterError("amount must be positive")
        statement_hash = _hash_payload(
            {
                "cash_account_id": cash_account_id,
                "transaction_date": transaction_date.isoformat(),
                "amount": str(amount),
                "direction": direction,
                "reference_no": reference_no or "",
            }
        )
        existing = (
            await self.db.execute(
                select(FinBankTransaction).where(FinBankTransaction.statement_hash == statement_hash)
            )
        ).scalar_one_or_none()
        if existing:
            return {"bank_transaction_id": existing.id, "deduplicated": True}
        bank_code = cash.ledger_account_id
        offset_code = "1001" if direction == "in" and cash.account_type != "cash" else "1002"
        debit_amount = amount if direction == "in" else Decimal("0")
        credit_amount = amount if direction == "out" else Decimal("0")
        draft = await self.core.create_voucher(
            book_id=book_id,
            period=self._period_for_date(transaction_date),
            voucher_no=f"BT-{transaction_date.strftime('%Y%m%d')}-{statement_hash[:8]}",
            voucher_date=transaction_date,
            entries=[
                {
                    "account_id": bank_code,
                    "summary": summary or f"银行流水 - {direction}",
                    "debit_amount": debit_amount,
                    "credit_amount": credit_amount,
                    "aux_items": {"cash_account_id": cash_account_id},
                },
                {
                    "account_id": await self._account_id_by_code(book_id, offset_code),
                    "summary": summary or f"银行流水对手 - {direction}",
                    "debit_amount": credit_amount,
                    "credit_amount": debit_amount,
                },
            ],
            actor_name=actor_name,
            reason=f"bank transaction {reference_no or statement_hash[:8]}",
            origin_kind="bank_transaction_draft",
        )
        row = FinBankTransaction(
            book_id=book_id,
            draft_voucher_id=draft["voucher_id"],
            cash_account_id=cash_account_id,
            transaction_date=transaction_date,
            amount=_decimal(amount),
            direction=direction,
            counterparty_name=counterparty_name,
            reference_no=reference_no,
            summary=summary,
            statement_hash=statement_hash,
            status="unreconciled",
            source_system=source_system,
            source_database=source_database,
            source_pk=source_pk or f"manual:{statement_hash[:16]}",
        )
        self.db.add(row)
        await self.db.commit()
        return {"bank_transaction_id": row.id, "voucher_id": draft["voucher_id"]}

    async def list_bank_transactions(
        self,
        book_id: int,
        cash_account_id: int | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        await self._require_book(book_id)
        stmt = select(FinBankTransaction).where(FinBankTransaction.book_id == book_id)
        if cash_account_id:
            stmt = stmt.where(FinBankTransaction.cash_account_id == cash_account_id)
        if status:
            stmt = stmt.where(FinBankTransaction.status == status)
        total = (await self.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (
            await self.db.execute(
                stmt.order_by(FinBankTransaction.transaction_date.desc(), FinBankTransaction.id.desc())
                .offset(max(page - 1, 0) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return {
            "items": [
                {
                    "id": r.id,
                    "cash_account_id": r.cash_account_id,
                    "transaction_date": r.transaction_date.isoformat() if r.transaction_date else None,
                    "amount": float(r.amount or 0),
                    "direction": r.direction,
                    "counterparty_name": r.counterparty_name,
                    "reference_no": r.reference_no,
                    "summary": r.summary,
                    "status": r.status,
                }
                for r in rows
            ],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    async def create_reconciliation(
        self,
        book_id: int,
        cash_account_id: int,
        period: str,
        statement_balance: Decimal,
        ledger_balance: Decimal,
        matched_transaction_ids: list[int] | None = None,
        actor_name: str = "system",
    ) -> dict:
        await self._require_book(book_id)
        await self._require_cash_account(book_id, cash_account_id)
        difference = _decimal(statement_balance) - _decimal(ledger_balance)
        reconciliation_no = f"RC-{period}-{cash_account_id}"
        existing = (
            await self.db.execute(
                select(FinReconciliation).where(
                    FinReconciliation.book_id == book_id, FinReconciliation.reconciliation_no == reconciliation_no
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.statement_balance = _decimal(statement_balance)
            existing.ledger_balance = _decimal(ledger_balance)
            existing.difference = difference
            existing.matched_transaction_ids = matched_transaction_ids or []
            existing.status = "draft"
            existing.reviewed_at = None
            row = existing
        else:
            row = FinReconciliation(
                book_id=book_id,
                reconciliation_no=reconciliation_no,
                cash_account_id=cash_account_id,
                period=period,
                statement_balance=_decimal(statement_balance),
                ledger_balance=_decimal(ledger_balance),
                difference=difference,
                matched_transaction_ids=matched_transaction_ids or [],
                status="draft",
            )
            self.db.add(row)
        self.db.add(
            FinOperationLog(
                book_id=book_id,
                actor_name=actor_name,
                action="reconciliation.create",
                target_type="reconciliation",
                target_id=str(row.id or 0),
                reason="bank reconciliation draft",
                after_data={"difference": float(difference), "period": period},
            )
        )
        await self.db.commit()
        return {"reconciliation_id": row.id, "difference": float(difference)}

    # ------------------------------------------------------------------ #
    # Fixed assets / depreciation                                        #
    # ------------------------------------------------------------------ #

    async def list_fixed_assets(self, book_id: int, status: str | None = None) -> list[dict]:
        await self._require_book(book_id)
        stmt = select(FinFixedAsset).where(FinFixedAsset.book_id == book_id)
        if status:
            stmt = stmt.where(FinFixedAsset.status == status)
        rows = (await self.db.execute(stmt.order_by(FinFixedAsset.asset_code))).scalars().all()
        return [self._fixed_asset_dict(r) for r in rows]

    async def create_fixed_asset(
        self,
        book_id: int,
        asset_code: str,
        asset_name: str,
        category: str,
        acquisition_date: date,
        in_service_date: date,
        original_cost: Decimal,
        useful_life_months: int,
        residual_rate: Decimal = Decimal("0"),
        department_aux_id: int | None = None,
        expense_account_id: int | None = None,
        accumulated_account_id: int | None = None,
        actor_name: str = "system",
    ) -> dict:
        await self._require_book(book_id)
        if _decimal(original_cost) <= 0 or useful_life_months <= 0:
            raise FinanceCenterError("original_cost and useful_life_months must be positive")
        if not expense_account_id:
            expense_account_id = await self._account_id_by_code(book_id, "6601")
        if not accumulated_account_id:
            accumulated_account_id = await self._account_id_by_code(book_id, "1602")
        await self._require_account(book_id, expense_account_id)
        await self._require_account(book_id, accumulated_account_id)
        existing = (
            await self.db.execute(
                select(FinFixedAsset).where(
                    FinFixedAsset.book_id == book_id, FinFixedAsset.asset_code == asset_code
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise FinanceCenterError(f"asset already exists: {asset_code}")
        row = FinFixedAsset(
            book_id=book_id,
            asset_code=asset_code,
            asset_name=asset_name,
            category=category,
            acquisition_date=acquisition_date,
            in_service_date=in_service_date,
            original_cost=_decimal(original_cost),
            residual_rate=Decimal(str(residual_rate)),
            useful_life_months=useful_life_months,
            accumulated_depreciation=Decimal("0.0000"),
            status="active",
            department_aux_id=department_aux_id,
            expense_account_id=expense_account_id,
            accumulated_account_id=accumulated_account_id,
        )
        self.db.add(row)
        self.db.add(
            FinOperationLog(
                book_id=book_id,
                actor_name=actor_name,
                action="fixed_asset.create",
                target_type="fixed_asset",
                target_id=str(row.id or 0),
                reason=f"create fixed asset {asset_code}",
            )
        )
        await self.db.commit()
        return {"fixed_asset_id": row.id, "asset_code": row.asset_code}

    async def calculate_depreciation(self, fixed_asset_id: int, period: str, actor_name: str) -> dict:
        asset = await self.db.get(FinFixedAsset, fixed_asset_id)
        if not asset:
            raise FinanceCenterError(f"fixed asset not found: {fixed_asset_id}")
        if asset.status != "active":
            raise FinanceCenterError(f"asset is not active: {asset.status}")
        existing = (
            await self.db.execute(
                select(FinDepreciation).where(
                    FinDepreciation.fixed_asset_id == fixed_asset_id, FinDepreciation.period == period
                )
            )
        ).scalar_one_or_none()
        if existing:
            return {"depreciation_id": existing.id, "amount": float(existing.amount), "deduplicated": True}
        year, month, _, end_date = _period_bounds(period)
        depreciation_date = end_date
        depreciable_base = _decimal(asset.original_cost) * (Decimal("1") - Decimal(str(asset.residual_rate or 0)))
        monthly = (depreciable_base / Decimal(int(asset.useful_life_months))).quantize(Decimal("0.0001"))
        accumulated = _decimal(asset.accumulated_depreciation) + monthly
        if accumulated > _decimal(asset.original_cost):
            monthly = _decimal(asset.original_cost) - _decimal(asset.accumulated_depreciation)
            accumulated = _decimal(asset.original_cost)
        if monthly <= 0:
            return {"status": "fully_depreciated", "amount": 0}
        row = FinDepreciation(
            book_id=asset.book_id,
            fixed_asset_id=fixed_asset_id,
            period=period,
            depreciation_date=depreciation_date,
            amount=monthly,
            accumulated_amount=accumulated,
            status="scheduled",
        )
        self.db.add(row)
        asset.accumulated_depreciation = accumulated
        if accumulated >= _decimal(asset.original_cost):
            asset.status = "fully_depreciated"
        asset.version = int(asset.version or 1) + 1
        await self.db.flush()
        # draft voucher: debit expense, credit accumulated depreciation
        draft = await self.core.create_voucher(
            book_id=asset.book_id,
            period=period,
            voucher_no=f"DP-{period}-{asset.asset_code}",
            voucher_date=depreciation_date,
            entries=[
                {
                    "account_id": asset.expense_account_id,
                    "summary": f"折旧费用 - {asset.asset_name}",
                    "debit_amount": monthly,
                    "credit_amount": 0,
                    "aux_items": {"fixed_asset_id": asset.id, "department_aux_id": asset.department_aux_id},
                },
                {
                    "account_id": asset.accumulated_account_id,
                    "summary": f"累计折旧 - {asset.asset_name}",
                    "debit_amount": 0,
                    "credit_amount": monthly,
                    "aux_items": {"fixed_asset_id": asset.id},
                },
            ],
            actor_name=actor_name,
            reason=f"monthly depreciation {asset.asset_code} {period}",
            origin_kind="depreciation_draft",
        )
        row.draft_voucher_id = draft["voucher_id"]
        row.status = "drafted"
        await self.db.commit()
        return {"depreciation_id": row.id, "voucher_id": draft["voucher_id"], "amount": float(monthly)}

    async def list_depreciations(self, book_id: int, fixed_asset_id: int | None = None, period: str | None = None) -> list[dict]:
        await self._require_book(book_id)
        stmt = select(FinDepreciation).where(FinDepreciation.book_id == book_id)
        if fixed_asset_id:
            stmt = stmt.where(FinDepreciation.fixed_asset_id == fixed_asset_id)
        if period:
            stmt = stmt.where(FinDepreciation.period == period)
        rows = (await self.db.execute(stmt.order_by(FinDepreciation.period.desc()))).scalars().all()
        return [
            {
                "id": r.id,
                "fixed_asset_id": r.fixed_asset_id,
                "period": r.period,
                "depreciation_date": r.depreciation_date.isoformat() if r.depreciation_date else None,
                "amount": float(r.amount or 0),
                "accumulated_amount": float(r.accumulated_amount or 0),
                "status": r.status,
                "draft_voucher_id": r.draft_voucher_id,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------ #
    # Invoices                                                           #
    # ------------------------------------------------------------------ #

    async def list_invoices(self, book_id: int, direction: str | None = None, status: str | None = None, page: int = 1, page_size: int = 20) -> dict:
        await self._require_book(book_id)
        stmt = select(FinInvoice).where(FinInvoice.book_id == book_id)
        if direction:
            stmt = stmt.where(FinInvoice.direction == direction)
        if status:
            stmt = stmt.where(FinInvoice.status == status)
        total = (await self.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (
            await self.db.execute(
                stmt.order_by(FinInvoice.invoice_date.desc(), FinInvoice.id.desc())
                .offset(max(page - 1, 0) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return {
            "items": [
                {
                    "id": r.id,
                    "invoice_code": r.invoice_code,
                    "invoice_no": r.invoice_no,
                    "invoice_type": r.invoice_type,
                    "direction": r.direction,
                    "invoice_date": r.invoice_date.isoformat() if r.invoice_date else None,
                    "counterparty_aux_id": r.counterparty_aux_id,
                    "amount_excluding_tax": float(r.amount_excluding_tax or 0),
                    "tax_amount": float(r.tax_amount or 0),
                    "total_amount": float(r.total_amount or 0),
                    "currency_code": r.currency_code,
                    "status": r.status,
                }
                for r in rows
            ],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    async def create_invoice(
        self,
        book_id: int,
        invoice_code: str,
        invoice_no: str,
        invoice_type: str,
        direction: str,
        invoice_date: date,
        amount_excluding_tax: Decimal,
        tax_amount: Decimal,
        counterparty_aux_id: int | None = None,
        currency_code: str = "CNY",
        actor_name: str = "system",
        source_system: str = "manual",
        source_database: str = "",
        source_pk: str | None = None,
    ) -> dict:
        await self._require_book(book_id)
        if direction not in {"in", "out"}:
            raise FinanceCenterError("direction must be 'in' or 'out'")
        amount_ex = _decimal(amount_excluding_tax)
        tax = _decimal(tax_amount)
        if amount_ex < 0 or tax < 0:
            raise FinanceCenterError("amounts cannot be negative")
        if counterparty_aux_id:
            await self._require_aux_item(book_id, counterparty_aux_id)
        existing = (
            await self.db.execute(
                select(FinInvoice).where(
                    FinInvoice.book_id == book_id,
                    FinInvoice.invoice_code == invoice_code,
                    FinInvoice.invoice_no == invoice_no,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return {"invoice_id": existing.id, "deduplicated": True}
        row = FinInvoice(
            book_id=book_id,
            invoice_code=invoice_code,
            invoice_no=invoice_no,
            invoice_type=invoice_type,
            direction=direction,
            invoice_date=invoice_date,
            counterparty_aux_id=counterparty_aux_id,
            amount_excluding_tax=amount_ex,
            tax_amount=tax,
            total_amount=amount_ex + tax,
            currency_code=currency_code,
            status="registered",
            source_system=source_system,
            source_database=source_database,
            source_pk=source_pk or f"manual:{invoice_code}-{invoice_no}",
        )
        self.db.add(row)
        await self.db.flush()
        await self._ensure_source_link(book_id, "invoice", row.id, source_database, source_pk or f"manual:{invoice_code}-{invoice_no}", "manual")
        self.db.add(
            FinOperationLog(
                book_id=book_id,
                actor_name=actor_name,
                action="invoice.register",
                target_type="invoice",
                target_id=str(row.id),
                reason=f"register invoice {invoice_no}",
            )
        )
        await self.db.commit()
        return {"invoice_id": row.id, "total_amount": float(row.total_amount)}

    # ------------------------------------------------------------------ #
    # Payroll                                                            #
    # ------------------------------------------------------------------ #

    async def list_payrolls(self, book_id: int, period: str | None = None, employee_aux_id: int | None = None) -> list[dict]:
        await self._require_book(book_id)
        stmt = select(FinPayroll).where(FinPayroll.book_id == book_id)
        if period:
            stmt = stmt.where(FinPayroll.period == period)
        if employee_aux_id:
            stmt = stmt.where(FinPayroll.employee_aux_id == employee_aux_id)
        rows = (await self.db.execute(stmt.order_by(FinPayroll.period.desc(), FinPayroll.id.desc()))).scalars().all()
        return [
            {
                "id": r.id,
                "period": r.period,
                "employee_aux_id": r.employee_aux_id,
                "department_aux_id": r.department_aux_id,
                "gross_amount": float(r.gross_amount or 0),
                "social_security_amount": float(r.social_security_amount or 0),
                "housing_fund_amount": float(r.housing_fund_amount or 0),
                "tax_amount": float(r.tax_amount or 0),
                "other_deduction": float(r.other_deduction or 0),
                "net_amount": float(r.net_amount or 0),
                "status": r.status,
            }
            for r in rows
        ]

    async def create_payroll(
        self,
        book_id: int,
        period: str,
        employee_aux_id: int,
        gross_amount: Decimal,
        social_security_amount: Decimal = Decimal("0"),
        housing_fund_amount: Decimal = Decimal("0"),
        tax_amount: Decimal = Decimal("0"),
        other_deduction: Decimal = Decimal("0"),
        department_aux_id: int | None = None,
        actor_name: str = "system",
        source_system: str = "manual",
        source_database: str = "",
        source_pk: str | None = None,
    ) -> dict:
        await self._require_book(book_id)
        await self._require_aux_item(book_id, employee_aux_id)
        if department_aux_id:
            await self._require_aux_item(book_id, department_aux_id)
        gross = _decimal(gross_amount)
        deductions = (
            _decimal(social_security_amount) + _decimal(housing_fund_amount) + _decimal(tax_amount) + _decimal(other_deduction)
        )
        net = gross - deductions
        if net < 0:
            raise FinanceCenterError("net amount cannot be negative")
        existing = (
            await self.db.execute(
                select(FinPayroll).where(
                    FinPayroll.book_id == book_id,
                    FinPayroll.period == period,
                    FinPayroll.employee_aux_id == employee_aux_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise FinanceCenterError(f"payroll already exists for employee {employee_aux_id} period {period}")
        row = FinPayroll(
            book_id=book_id,
            period=period,
            employee_aux_id=employee_aux_id,
            department_aux_id=department_aux_id,
            gross_amount=gross,
            social_security_amount=_decimal(social_security_amount),
            housing_fund_amount=_decimal(housing_fund_amount),
            tax_amount=_decimal(tax_amount),
            other_deduction=_decimal(other_deduction),
            net_amount=net,
            status="draft",
            source_system=source_system,
            source_database=source_database,
            source_pk=source_pk or f"manual:{period}:{employee_aux_id}",
        )
        self.db.add(row)
        await self.db.flush()
        await self._ensure_source_link(book_id, "payroll", row.id, source_database, source_pk or f"manual:{period}:{employee_aux_id}", "manual")
        self.db.add(
            FinOperationLog(
                book_id=book_id,
                actor_name=actor_name,
                action="payroll.create",
                target_type="payroll",
                target_id=str(row.id),
                reason=f"create payroll {period} employee {employee_aux_id}",
            )
        )
        await self.db.commit()
        return {"payroll_id": row.id, "net_amount": float(net)}

    # ------------------------------------------------------------------ #
    # Tax                                                                #
    # ------------------------------------------------------------------ #

    async def list_tax_records(self, book_id: int, period: str | None = None) -> list[dict]:
        await self._require_book(book_id)
        stmt = select(FinTaxRecord).where(FinTaxRecord.book_id == book_id)
        if period:
            stmt = stmt.where(FinTaxRecord.period == period)
        rows = (await self.db.execute(stmt.order_by(FinTaxRecord.period.desc()))).scalars().all()
        return [
            {
                "id": r.id,
                "tax_type": r.tax_type,
                "period": r.period,
                "taxable_amount": float(r.taxable_amount or 0),
                "tax_amount": float(r.tax_amount or 0),
                "paid_amount": float(r.paid_amount or 0),
                "due_date": r.due_date.isoformat() if r.due_date else None,
                "paid_date": r.paid_date.isoformat() if r.paid_date else None,
                "status": r.status,
            }
            for r in rows
        ]

    async def create_tax_record(
        self,
        book_id: int,
        tax_type: str,
        period: str,
        tax_amount: Decimal,
        taxable_amount: Decimal = Decimal("0"),
        due_date: date | None = None,
        actor_name: str = "system",
        source_system: str = "manual",
        source_database: str = "",
        source_pk: str | None = None,
    ) -> dict:
        await self._require_book(book_id)
        if _decimal(tax_amount) < 0:
            raise FinanceCenterError("tax_amount cannot be negative")
        existing = (
            await self.db.execute(
                select(FinTaxRecord).where(
                    FinTaxRecord.book_id == book_id,
                    FinTaxRecord.tax_type == tax_type,
                    FinTaxRecord.period == period,
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise FinanceCenterError(f"tax record already exists for {tax_type} {period}")
        row = FinTaxRecord(
            book_id=book_id,
            tax_type=tax_type,
            period=period,
            taxable_amount=_decimal(taxable_amount),
            tax_amount=_decimal(tax_amount),
            paid_amount=Decimal("0.0000"),
            due_date=due_date,
            status="unpaid",
            source_system=source_system,
            source_database=source_database,
            source_pk=source_pk or f"manual:{tax_type}:{period}",
        )
        self.db.add(row)
        await self.db.flush()
        await self._ensure_source_link(book_id, "tax_record", row.id, source_database, source_pk or f"manual:{tax_type}:{period}", "manual")
        self.db.add(
            FinOperationLog(
                book_id=book_id,
                actor_name=actor_name,
                action="tax.create",
                target_type="tax_record",
                target_id=str(row.id),
                reason=f"create tax {tax_type} {period}",
            )
        )
        await self.db.commit()
        return {"tax_record_id": row.id, "status": row.status}

    async def mark_tax_paid(self, tax_record_id: int, paid_date: date, actor_name: str, reason: str) -> dict:
        if not reason or not reason.strip():
            raise FinanceCenterError("mark_tax_paid reason is required")
        row = await self.db.get(FinTaxRecord, tax_record_id)
        if not row:
            raise FinanceCenterError(f"tax record not found: {tax_record_id}")
        if row.status == "paid":
            return {"tax_record_id": row.id, "status": "paid", "deduplicated": True}
        row.paid_amount = _decimal(row.tax_amount)
        row.paid_date = paid_date
        row.status = "paid"
        row.version = int(row.version or 1) + 1
        self.db.add(
            FinOperationLog(
                book_id=row.book_id,
                actor_name=actor_name,
                action="tax.mark_paid",
                target_type="tax_record",
                target_id=str(row.id),
                reason=reason,
                after_data={"paid_amount": float(row.paid_amount), "paid_date": paid_date.isoformat()},
            )
        )
        await self.db.commit()
        return {"tax_record_id": row.id, "status": row.status}

    # ------------------------------------------------------------------ #
    # Auto entry rules / runs                                            #
    # ------------------------------------------------------------------ #

    async def list_auto_entry_rules(self, book_id: int, status: str | None = None) -> list[dict]:
        await self._require_book(book_id)
        stmt = select(FinAutoEntryRule).where(FinAutoEntryRule.book_id == book_id)
        if status:
            stmt = stmt.where(FinAutoEntryRule.status == status)
        rows = (await self.db.execute(stmt.order_by(FinAutoEntryRule.priority, FinAutoEntryRule.rule_name))).scalars().all()
        return [
            {
                "id": r.id,
                "rule_name": r.rule_name,
                "business_type": r.business_type,
                "source_system": r.source_system,
                "effective_from": r.effective_from,
                "effective_to": r.effective_to,
                "priority": r.priority,
                "conditions": r.conditions,
                "entry_template": r.entry_template,
                "status": r.status,
            }
            for r in rows
        ]

    async def upsert_auto_entry_rule(
        self,
        book_id: int,
        rule_name: str,
        business_type: str,
        source_system: str,
        entry_template: dict,
        effective_from: str,
        effective_to: str | None = None,
        priority: int = 100,
        conditions: dict | None = None,
        status: str = "active",
    ) -> dict:
        await self._require_book(book_id)
        if not entry_template or "entries" not in entry_template:
            raise FinanceCenterError("entry_template.entries is required")
        existing = (
            await self.db.execute(
                select(FinAutoEntryRule).where(
                    FinAutoEntryRule.book_id == book_id,
                    FinAutoEntryRule.business_type == business_type,
                    FinAutoEntryRule.effective_from == effective_from,
                    FinAutoEntryRule.priority == priority,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.rule_name = rule_name
            existing.source_system = source_system
            existing.entry_template = entry_template
            existing.effective_to = effective_to
            existing.conditions = conditions or {}
            existing.status = status
            row = existing
        else:
            row = FinAutoEntryRule(
                book_id=book_id,
                rule_name=rule_name,
                business_type=business_type,
                source_system=source_system,
                effective_from=effective_from,
                effective_to=effective_to,
                priority=priority,
                conditions=conditions or {},
                entry_template=entry_template,
                status=status,
            )
            self.db.add(row)
        await self.db.commit()
        return {"rule_id": row.id, "rule_name": row.rule_name}

    async def run_auto_entry(
        self,
        rule_id: int,
        source_data: list[dict],
        period: str,
        actor_name: str,
        mode: str = "preview",
    ) -> dict:
        if mode not in {"preview", "draft"}:
            raise FinanceCenterError("mode must be preview or draft")
        rule = await self.db.get(FinAutoEntryRule, rule_id)
        if not rule:
            raise FinanceCenterError(f"rule not found: {rule_id}")
        if rule.status != "active":
            raise FinanceCenterError(f"rule is not active: {rule.status}")
        if period < rule.effective_from or (rule.effective_to and period > rule.effective_to):
            raise FinanceCenterError(f"period {period} is outside rule effective range")
        input_hash = _hash_payload({"rule_id": rule_id, "period": period, "source_data": source_data})
        run_key = f"{rule.business_type}:{period}:{input_hash[:16]}"
        existing = (
            await self.db.execute(
                select(FinAutoEntryRun).where(FinAutoEntryRun.book_id == rule.book_id, FinAutoEntryRun.run_key == run_key)
            )
        ).scalar_one_or_none()
        if existing:
            return {
                "run_id": existing.id,
                "status": existing.status,
                "draft_count": existing.draft_count,
                "exception_count": existing.exception_count,
                "deduplicated": True,
            }
        template = rule.entry_template or {}
        entries_template = template.get("entries") or []
        if not entries_template:
            raise FinanceCenterError("entry_template.entries is empty")
        exceptions = []
        draft_count = 0
        for idx, source in enumerate(source_data):
            try:
                entries = self._render_entries(entries_template, source)
                if mode == "draft":
                    await self.core.create_voucher(
                        book_id=rule.book_id,
                        period=period,
                        voucher_no=f"AUTO-{rule.business_type}-{period}-{idx + 1}",
                        voucher_date=date.today(),
                        entries=entries,
                        actor_name=actor_name,
                        reason=f"auto entry from rule {rule.rule_name}",
                        origin_kind=f"auto_entry:{rule.business_type}",
                    )
                    draft_count += 1
                else:
                    draft_count += 1
            except Exception as exc:
                exceptions.append({"index": idx, "source": source, "error": str(exc)})
        run = FinAutoEntryRun(
            book_id=rule.book_id,
            run_key=run_key,
            source_system=rule.source_system,
            business_type=rule.business_type,
            mode=mode,
            status="completed" if not exceptions else "completed_with_exceptions",
            source_count=len(source_data),
            draft_count=draft_count,
            exception_count=len(exceptions),
            input_hash=input_hash,
            result={"drafts": draft_count, "exceptions": exceptions[:20]},
            error_message=None,
            completed_at=datetime.now(timezone.utc),
        )
        self.db.add(run)
        self.db.add(
            FinOperationLog(
                book_id=rule.book_id,
                actor_name=actor_name,
                action="auto_entry.run",
                target_type="auto_entry_rule",
                target_id=str(rule.id),
                reason=f"run {rule.rule_name} for {period}",
                after_data={"mode": mode, "draft_count": draft_count, "exception_count": len(exceptions)},
            )
        )
        await self.db.commit()
        return {
            "run_id": run.id,
            "status": run.status,
            "draft_count": draft_count,
            "exception_count": len(exceptions),
            "exceptions": exceptions[:20],
        }

    async def list_auto_entry_runs(self, book_id: int, page: int = 1, page_size: int = 20) -> dict:
        await self._require_book(book_id)
        stmt = select(FinAutoEntryRun).where(FinAutoEntryRun.book_id == book_id)
        total = (await self.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (
            await self.db.execute(
                stmt.order_by(FinAutoEntryRun.started_at.desc(), FinAutoEntryRun.id.desc())
                .offset(max(page - 1, 0) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return {
            "items": [
                {
                    "id": r.id,
                    "run_key": r.run_key,
                    "source_system": r.source_system,
                    "business_type": r.business_type,
                    "mode": r.mode,
                    "status": r.status,
                    "source_count": r.source_count,
                    "draft_count": r.draft_count,
                    "exception_count": r.exception_count,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                }
                for r in rows
            ],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    # ------------------------------------------------------------------ #
    # Operation logs                                                     #
    # ------------------------------------------------------------------ #

    async def list_operation_logs(
        self,
        book_id: int,
        target_type: str | None = None,
        action: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        await self._require_book(book_id)
        stmt = select(FinOperationLog).where(FinOperationLog.book_id == book_id)
        if target_type:
            stmt = stmt.where(FinOperationLog.target_type == target_type)
        if action:
            stmt = stmt.where(FinOperationLog.action == action)
        total = (await self.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (
            await self.db.execute(
                stmt.order_by(FinOperationLog.id.desc())
                .offset(max(page - 1, 0) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return {
            "items": [
                {
                    "id": r.id,
                    "actor_name": r.actor_name,
                    "action": r.action,
                    "target_type": r.target_type,
                    "target_id": r.target_id,
                    "reason": r.reason,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    async def _require_book(self, book_id: int) -> FinBook:
        book = await self.db.get(FinBook, book_id)
        if not book:
            raise FinanceCenterError(f"book not found: {book_id}")
        return book

    async def _get_period(self, book_id: int, period: str) -> FinPeriod:
        row = (
            await self.db.execute(
                select(FinPeriod).where(FinPeriod.book_id == book_id, FinPeriod.period == period)
            )
        ).scalar_one_or_none()
        if not row:
            raise FinanceCenterError(f"period not found: {period}")
        return row

    async def _require_voucher(self, voucher_id: int) -> FinVoucher:
        voucher = await self.db.get(FinVoucher, voucher_id)
        if not voucher:
            raise FinanceCenterError(f"voucher not found: {voucher_id}")
        return voucher

    async def _require_account(self, book_id: int, account_id: int) -> FinAccount:
        account = await self.db.get(FinAccount, account_id)
        if not account or account.book_id != book_id:
            raise FinanceCenterError(f"account not found: {account_id}")
        return account

    async def _require_aux_item(self, book_id: int, aux_item_id: int) -> FinAuxItem:
        item = await self.db.get(FinAuxItem, aux_item_id)
        if not item or item.book_id != book_id:
            raise FinanceCenterError(f"aux item not found: {aux_item_id}")
        return item

    async def _require_cash_account(self, book_id: int, cash_account_id: int) -> FinCashAccount:
        cash = await self.db.get(FinCashAccount, cash_account_id)
        if not cash or cash.book_id != book_id:
            raise FinanceCenterError(f"cash account not found: {cash_account_id}")
        return cash

    async def _voucher_entries(self, voucher_id: int) -> list[FinVoucherEntry]:
        return list(
            (
                await self.db.execute(
                    select(FinVoucherEntry)
                    .where(FinVoucherEntry.voucher_id == voucher_id)
                    .order_by(FinVoucherEntry.line_no)
                )
            ).scalars()
        )

    async def _account_map(self, book_id: int, account_ids: Iterable[int]) -> dict[int, dict]:
        ids = list(account_ids)
        if not ids:
            return {}
        rows = (
            await self.db.execute(
                select(FinAccount).where(FinAccount.book_id == book_id, FinAccount.id.in_(ids))
            )
        ).scalars().all()
        return {
            row.id: {
                "account_code": row.account_code,
                "account_name": row.account_name,
                "balance_direction": row.balance_direction,
            }
            for row in rows
        }

    async def _account_id_by_code(self, book_id: int, code_prefix: str) -> int:
        # matches accounts whose code starts with the prefix; falls back to first detail account
        rows = (
            await self.db.execute(
                select(FinAccount)
                .where(
                    FinAccount.book_id == book_id,
                    FinAccount.account_code.like(f"{code_prefix}%"),
                    FinAccount.is_active.is_(True),
                )
                .order_by(FinAccount.account_level.desc(), FinAccount.account_code)
                .limit(1)
            )
        ).scalars().all()
        if not rows:
            raise FinanceCenterError(f"no account matches code prefix: {code_prefix}")
        return rows[0].id

    async def _find_imbalanced_vouchers(self, book_id: int, period_id: int) -> list[dict]:
        rows = (
            await self.db.execute(
                select(FinVoucher)
                .where(
                    FinVoucher.book_id == book_id,
                    FinVoucher.period_id == period_id,
                    FinVoucher.status.in_(("draft", "reviewed", "posted")),
                    FinVoucher.total_debit != FinVoucher.total_credit,
                )
            )
        ).scalars().all()
        return [{"voucher_id": v.id, "voucher_no": v.voucher_no} for v in rows]

    async def _ensure_source_link(
        self,
        book_id: int,
        target_type: str,
        target_id: int,
        source_database: str,
        source_pk: str,
        import_batch_id: str,
    ) -> None:
        existing = (
            await self.db.execute(
                select(FinSourceLink.id).where(
                    FinSourceLink.book_id == book_id,
                    FinSourceLink.target_type == target_type,
                    FinSourceLink.target_id == target_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return
        self.db.add(
            FinSourceLink(
                book_id=book_id,
                target_type=target_type,
                target_id=target_id,
                source_system="manual",
                source_database=source_database,
                source_pk=source_pk,
                import_batch_id=import_batch_id,
            )
        )

    def _render_entries(self, template_entries: list[dict], source: dict) -> list[dict]:
        rendered: list[dict] = []
        for tpl in template_entries:
            try:
                rendered.append(
                    {
                        "account_id": int(self._render_value(tpl.get("account_id"), source)),
                        "summary": str(self._render_value(tpl.get("summary", ""), source)),
                        "debit_amount": _decimal(self._render_value(tpl.get("debit_amount", 0), source)),
                        "credit_amount": _decimal(self._render_value(tpl.get("credit_amount", 0), source)),
                        "currency_code": str(self._render_value(tpl.get("currency_code", "CNY"), source)),
                        "aux_items": self._render_value(tpl.get("aux_items", {}), source) or {},
                    }
                )
            except Exception as exc:
                raise FinanceCenterError(f"failed to render entry template: {exc}") from exc
        return rendered

    def _render_value(self, value: Any, source: dict) -> Any:
        if isinstance(value, str) and value.startswith("$"):
            key = value[1:]
            if key not in source:
                raise FinanceCenterError(f"missing source field: {key}")
            return source[key]
        if isinstance(value, dict):
            return {k: self._render_value(v, source) for k, v in value.items()}
        if isinstance(value, list):
            return [self._render_value(v, source) for v in value]
        return value

    def _entry_totals_from_rows(self, entries: Iterable[FinVoucherEntry]) -> tuple[Decimal, Decimal]:
        debit = Decimal("0.0000")
        credit = Decimal("0.0000")
        for entry in entries:
            debit += _decimal(entry.debit_amount)
            credit += _decimal(entry.credit_amount)
        return debit, credit

    def _period_for_date(self, target: date) -> str:
        return f"{target.year:04d}-{target.month:02d}"

    def _next_period(self, period: str) -> str:
        year, month = (int(p) for p in period.split("-"))
        if month == 12:
            return f"{year + 1:04d}-01"
        return f"{year:04d}-{month + 1:02d}"

    def _book_dict(self, row: FinBook) -> dict:
        return {
            "id": row.id,
            "book_code": row.book_code,
            "book_name": row.book_name,
            "short_name": row.short_name,
            "base_currency": row.base_currency,
            "accounting_standard": row.accounting_standard,
            "start_period": row.start_period,
            "current_period": row.current_period,
            "status": row.status,
            "version": row.version,
        }

    def _account_dict(self, row: FinAccount) -> dict:
        return {
            "id": row.id,
            "account_code": row.account_code,
            "account_name": row.account_name,
            "parent_id": row.parent_id,
            "account_level": row.account_level,
            "account_type": row.account_type,
            "balance_direction": row.balance_direction,
            "is_detail": row.is_detail,
            "is_cash": row.is_cash,
            "is_bank": row.is_bank,
            "has_quantity": row.has_quantity,
            "has_foreign_currency": row.has_foreign_currency,
            "requires_auxiliary": row.requires_auxiliary,
            "is_active": row.is_active,
        }

    def _voucher_summary(self, row: FinVoucher) -> dict:
        return {
            "id": row.id,
            "book_id": row.book_id,
            "voucher_no": row.voucher_no,
            "voucher_group": row.voucher_group,
            "voucher_date": row.voucher_date.isoformat() if row.voucher_date else None,
            "period": row.period,
            "status": row.status,
            "origin_kind": row.origin_kind,
            "total_debit": float(row.total_debit or 0),
            "total_credit": float(row.total_credit or 0),
            "prepared_name": row.prepared_name,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            "posted_at": row.posted_at.isoformat() if row.posted_at else None,
            "reversal_of_id": row.reversal_of_id,
            "reversed_by_id": row.reversed_by_id,
            "version": row.version,
        }

    def _receivable_dict(self, row: FinReceivable) -> dict:
        return {
            "id": row.id,
            "document_no": row.document_no,
            "counterparty_aux_id": row.counterparty_aux_id,
            "business_date": row.business_date.isoformat() if row.business_date else None,
            "due_date": row.due_date.isoformat() if row.due_date else None,
            "currency_code": row.currency_code,
            "original_amount": float(row.original_amount or 0),
            "settled_amount": float(row.settled_amount or 0),
            "outstanding_amount": float(row.outstanding_amount or 0),
            "status": row.status,
            "draft_voucher_id": row.draft_voucher_id,
        }

    def _payable_dict(self, row: FinPayable) -> dict:
        return {
            "id": row.id,
            "document_no": row.document_no,
            "counterparty_aux_id": row.counterparty_aux_id,
            "business_date": row.business_date.isoformat() if row.business_date else None,
            "due_date": row.due_date.isoformat() if row.due_date else None,
            "currency_code": row.currency_code,
            "original_amount": float(row.original_amount or 0),
            "settled_amount": float(row.settled_amount or 0),
            "outstanding_amount": float(row.outstanding_amount or 0),
            "status": row.status,
            "draft_voucher_id": row.draft_voucher_id,
        }

    def _cash_account_dict(self, row: FinCashAccount) -> dict:
        return {
            "id": row.id,
            "account_code": row.account_code,
            "account_name": row.account_name,
            "account_type": row.account_type,
            "ledger_account_id": row.ledger_account_id,
            "bank_name": row.bank_name,
            "bank_account_masked": row.bank_account_masked,
            "currency_code": row.currency_code,
            "status": row.status,
        }

    def _fixed_asset_dict(self, row: FinFixedAsset) -> dict:
        return {
            "id": row.id,
            "asset_code": row.asset_code,
            "asset_name": row.asset_name,
            "category": row.category,
            "acquisition_date": row.acquisition_date.isoformat() if row.acquisition_date else None,
            "in_service_date": row.in_service_date.isoformat() if row.in_service_date else None,
            "original_cost": float(row.original_cost or 0),
            "residual_rate": float(row.residual_rate or 0),
            "useful_life_months": row.useful_life_months,
            "accumulated_depreciation": float(row.accumulated_depreciation or 0),
            "status": row.status,
            "department_aux_id": row.department_aux_id,
            "expense_account_id": row.expense_account_id,
            "accumulated_account_id": row.accumulated_account_id,
        }
