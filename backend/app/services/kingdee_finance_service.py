"""Validation and read-only query service for imported Kingdee history."""

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kingdee_finance import (
    DimFinanceAccount,
    DimFinanceStatementMapping,
    DimLegalEntity,
    DmFinanceStatementMonthly,
    DwdGlBalanceMonthly,
    DwdGlVoucher,
    DwdGlVoucherEntry,
    KingdeeImportBatch,
)


EXPECTED_SNAPSHOT_TOTALS = {
    "vouchers": 339,
    "voucher_entries": 4596,
    "accounts": 416,
    "balances": 6868,
}

EXPECTED_ACCOUNT_SET_TOTALS = {
    "AIS20251127140257": {"vouchers": 77, "voucher_entries": 871, "accounts": 150, "balances": 1378},
    "AIS20260305112309": {"vouchers": 244, "voucher_entries": 3476, "accounts": 219, "balances": 4940},
    "AIS20260305112733": {"vouchers": 18, "voucher_entries": 249, "accounts": 47, "balances": 550},
}


def build_source_pk(account_set: str, *parts: object) -> str:
    return ":".join([str(account_set), *(str(part) for part in parts)])


def validate_snapshot(actual: dict[str, int]) -> dict:
    errors = []
    for name, expected in EXPECTED_SNAPSHOT_TOTALS.items():
        received = int(actual.get(name, -1))
        if received != expected:
            errors.append(f"{name}: expected {expected}, received {received}")
    return {"status": "ready" if not errors else "blocked", "errors": errors}


def validate_account_set_snapshots(actual: dict[str, dict[str, int]]) -> dict:
    errors = []
    if set(actual) != set(EXPECTED_ACCOUNT_SET_TOTALS):
        errors.append(
            f"account sets: expected {sorted(EXPECTED_ACCOUNT_SET_TOTALS)}, received {sorted(actual)}"
        )
    for database, expected_counts in EXPECTED_ACCOUNT_SET_TOTALS.items():
        received_counts = actual.get(database, {})
        for name, expected in expected_counts.items():
            received = int(received_counts.get(name, -1))
            if received != expected:
                errors.append(f"{database}.{name}: expected {expected}, received {received}")
    return {"status": "ready" if not errors else "blocked", "errors": errors}


def validate_voucher_balances(rows: list[dict]) -> list[dict]:
    totals = defaultdict(lambda: [Decimal("0"), Decimal("0")])
    for row in rows:
        key = (str(row["account_set"]), str(row["voucher_id"]))
        totals[key][0] += Decimal(str(row.get("debit") or 0))
        totals[key][1] += Decimal(str(row.get("credit") or 0))
    errors = []
    for (account_set, voucher_id), (debit, credit) in totals.items():
        difference = debit - credit
        if difference != 0:
            errors.append({
                "account_set": account_set,
                "voucher_id": voucher_id,
                "debit": f"{debit:.2f}",
                "credit": f"{credit:.2f}",
                "difference": f"{difference:.2f}",
            })
    return errors


def validate_voucher_header_totals(headers: list[dict], entries: list[dict]) -> list[dict]:
    entry_totals = defaultdict(lambda: [Decimal("0"), Decimal("0")])
    for row in entries:
        key = (str(row["account_set"]), str(row["voucher_id"]))
        entry_totals[key][0] += Decimal(str(row.get("debit") or 0))
        entry_totals[key][1] += Decimal(str(row.get("credit") or 0))
    errors = []
    for row in headers:
        key = (str(row["account_set"]), str(row["voucher_id"]))
        entry_debit, entry_credit = entry_totals.get(key, [Decimal("0"), Decimal("0")])
        debit_difference = Decimal(str(row.get("debit") or 0)) - entry_debit
        credit_difference = Decimal(str(row.get("credit") or 0)) - entry_credit
        if debit_difference != 0 or credit_difference != 0:
            errors.append({
                "account_set": key[0], "voucher_id": key[1],
                "debit_difference": f"{debit_difference:.2f}",
                "credit_difference": f"{credit_difference:.2f}",
            })
    return errors


def validate_balance_equations(rows: list[dict]) -> list[dict]:
    errors = []
    for row in rows:
        opening = Decimal(str(row.get("opening_debit") or 0)) - Decimal(str(row.get("opening_credit") or 0))
        activity = Decimal(str(row.get("period_debit") or 0)) - Decimal(str(row.get("period_credit") or 0))
        closing = Decimal(str(row.get("closing_debit") or 0)) - Decimal(str(row.get("closing_credit") or 0))
        difference = opening + activity - closing
        if difference != 0:
            errors.append({
                "account_set": str(row["account_set"]),
                "source_pk": str(row["source_pk"]),
                "difference": f"{difference:.2f}",
            })
    return errors


def evaluate_statement_status(source_rows: int, account_count: int, mapped_count: int) -> str:
    if source_rows <= 0:
        return "pending_data"
    if account_count <= 0 or mapped_count < account_count:
        return "pending_mapping"
    return "ready"


def _number(value):
    return float(value) if value is not None else None


class KingdeeFinanceQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def account_sets(self):
        rows = (await self.db.execute(select(DimLegalEntity).order_by(DimLegalEntity.entity_code))).scalars().all()
        return [{
            "id": row.id,
            "entity_code": row.entity_code,
            "account_set_code": row.account_set_code,
            "company_name": row.entity_name,
            "short_name": row.short_name,
            "start_period": row.start_period,
            "current_period": row.current_period,
            "status": row.status,
        } for row in rows]

    async def _entity(self, account_set_code: str):
        return (await self.db.execute(
            select(DimLegalEntity).where(DimLegalEntity.account_set_code == account_set_code)
        )).scalar_one_or_none()

    async def periods(self, account_set_code: str):
        entity = await self._entity(account_set_code)
        if not entity:
            return []
        periods = (await self.db.execute(
            select(DwdGlBalanceMonthly.period)
            .where(DwdGlBalanceMonthly.legal_entity_id == entity.id)
            .distinct().order_by(DwdGlBalanceMonthly.period)
        )).scalars().all()
        return [{"account_set_code": account_set_code, "period": period, "status": "source_closed"} for period in periods]

    async def statements(self, account_set_code: str, period: str, statement_type: str):
        entity = await self._entity(account_set_code)
        if not entity:
            return {"status": "pending_data", "items": [], "issues": ["account_set_not_found"]}
        account_count = (await self.db.execute(
            select(func.count(DimFinanceAccount.id)).where(DimFinanceAccount.legal_entity_id == entity.id)
        )).scalar_one()
        mapped_count = (await self.db.execute(
            select(func.count(func.distinct(DimFinanceStatementMapping.finance_account_id))).where(
                DimFinanceStatementMapping.legal_entity_id == entity.id,
                DimFinanceStatementMapping.statement_type == statement_type,
                DimFinanceStatementMapping.mapping_status == "confirmed",
            )
        )).scalar_one()
        rows = (await self.db.execute(
            select(DmFinanceStatementMonthly).where(
                DmFinanceStatementMonthly.legal_entity_id == entity.id,
                DmFinanceStatementMonthly.period == period,
                DmFinanceStatementMonthly.statement_type == statement_type,
            ).order_by(DmFinanceStatementMonthly.display_order)
        )).scalars().all()
        source_rows = (await self.db.execute(
            select(func.count(DwdGlBalanceMonthly.id)).where(
                DwdGlBalanceMonthly.legal_entity_id == entity.id,
                DwdGlBalanceMonthly.period == period,
            )
        )).scalar_one()
        status = evaluate_statement_status(source_rows, account_count, mapped_count)
        return {"status": status, "items": [{
            "line_code": row.line_code,
            "line_name": row.line_name,
            "current_amount": _number(row.current_amount),
            "year_to_date_amount": _number(row.year_to_date_amount),
            "status": row.status,
        } for row in rows], "issues": [] if status == "ready" else [status]}

    async def account_balances(self, account_set_code: str, period: str, page: int, page_size: int, keyword: str | None = None):
        entity = await self._entity(account_set_code)
        if not entity:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        base = select(DwdGlBalanceMonthly, DimFinanceAccount).join(
            DimFinanceAccount, DimFinanceAccount.id == DwdGlBalanceMonthly.finance_account_id
        ).where(DwdGlBalanceMonthly.legal_entity_id == entity.id, DwdGlBalanceMonthly.period == period)
        if keyword:
            base = base.where(
                DimFinanceAccount.account_code.ilike(f"%{keyword}%") |
                DimFinanceAccount.account_name.ilike(f"%{keyword}%")
            )
        total = (await self.db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        rows = (await self.db.execute(base.order_by(DimFinanceAccount.account_code).offset((page - 1) * page_size).limit(page_size))).all()
        return {"items": [{
            "account_code": account.account_code,
            "account_name": account.account_name,
            "balance_direction": account.balance_direction,
            "period": balance.period,
            "opening_debit": _number(balance.opening_debit),
            "opening_credit": _number(balance.opening_credit),
            "period_debit": _number(balance.period_debit),
            "period_credit": _number(balance.period_credit),
            "closing_debit": _number(balance.closing_debit),
            "closing_credit": _number(balance.closing_credit),
        } for balance, account in rows], "total": total, "page": page, "page_size": page_size}

    async def vouchers(self, account_set_code: str, period: str | None, page: int, page_size: int, keyword: str | None = None):
        entity = await self._entity(account_set_code)
        if not entity:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        query = select(DwdGlVoucher).where(DwdGlVoucher.legal_entity_id == entity.id)
        if period:
            year, month = (int(part) for part in period.split("-"))
            query = query.where(DwdGlVoucher.fiscal_year == year, DwdGlVoucher.fiscal_period == month)
        if keyword:
            query = query.where(DwdGlVoucher.voucher_no.ilike(f"%{keyword}%"))
        total = (await self.db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        rows = (await self.db.execute(query.order_by(DwdGlVoucher.voucher_date.desc(), DwdGlVoucher.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
        return {"items": [{
            "id": row.id,
            "voucher_no": row.voucher_no,
            "voucher_date": str(row.voucher_date),
            "period": f"{row.fiscal_year:04d}-{row.fiscal_period:02d}",
            "source_status": row.source_status,
            "is_posted": row.is_posted,
            "total_debit": _number(row.total_debit),
            "total_credit": _number(row.total_credit),
            "read_only": True,
        } for row in rows], "total": total, "page": page, "page_size": page_size}

    async def voucher_detail(self, voucher_id: int):
        voucher = await self.db.get(DwdGlVoucher, voucher_id)
        if not voucher:
            return None
        rows = (await self.db.execute(
            select(DwdGlVoucherEntry, DimFinanceAccount)
            .join(DimFinanceAccount, DimFinanceAccount.id == DwdGlVoucherEntry.finance_account_id)
            .where(DwdGlVoucherEntry.voucher_id == voucher_id)
            .order_by(DwdGlVoucherEntry.line_no, DwdGlVoucherEntry.id)
        )).all()
        return {
            "id": voucher.id,
            "voucher_no": voucher.voucher_no,
            "voucher_date": str(voucher.voucher_date),
            "source_status": voucher.source_status,
            "read_only": True,
            "entries": [{
                "line_no": entry.line_no,
                "account_code": account.account_code,
                "account_name": account.account_name,
                "summary": entry.summary,
                "debit_amount": _number(entry.debit_amount),
                "credit_amount": _number(entry.credit_amount),
                "currency_code": entry.currency_code,
            } for entry, account in rows],
        }

    async def import_batches(self):
        rows = (await self.db.execute(select(KingdeeImportBatch).order_by(KingdeeImportBatch.started_at.desc()))).scalars().all()
        return [{
            "batch_id": row.batch_id,
            "run_id": row.run_id,
            "source_database": row.source_database,
            "backup_sha256": row.backup_sha256,
            "status": row.status,
            "actual_counts": row.actual_counts,
            "validation_result": row.validation_result,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        } for row in rows]

    async def data_quality(self, account_set_code: str | None = None):
        entity = await self._entity(account_set_code) if account_set_code else None
        account_filter = [DimFinanceAccount.legal_entity_id == entity.id] if entity else []
        accounts = (await self.db.execute(select(func.count(DimFinanceAccount.id)).where(*account_filter))).scalar_one()
        mapping_filter = [DimFinanceStatementMapping.legal_entity_id == entity.id] if entity else []
        mapped = (await self.db.execute(select(func.count(func.distinct(DimFinanceStatementMapping.finance_account_id))).where(
            *mapping_filter, DimFinanceStatementMapping.mapping_status == "confirmed"
        ))).scalar_one()
        issues = []
        if mapped < accounts:
            issues.append({"code": "unmapped_accounts", "severity": "blocking", "count": accounts - mapped})
        return {
            "status": "ready" if not issues else "pending_mapping",
            "account_set_code": account_set_code,
            "account_count": accounts,
            "mapped_account_count": mapped,
            "issues": issues,
        }
