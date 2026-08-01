"""Validate and idempotently import a canonical Kingdee JSONL dataset."""

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.database import AsyncSessionLocal
from app.models.kingdee_finance import (
    DimFinanceAccount,
    DimLegalEntity,
    DwdGlBalanceMonthly,
    DwdGlVoucher,
    DwdGlVoucherEntry,
    KingdeeAccount,
    KingdeeAuxItem,
    KingdeeBalance,
    KingdeeCurrency,
    KingdeeDepartment,
    KingdeeEmployee,
    KingdeeImportBatch,
    KingdeeSupplier,
    KingdeeVoucher,
    KingdeeVoucherEntry,
)
from app.services.kingdee_finance_service import (
    EXPECTED_ACCOUNT_SET_TOTALS,
    EXPECTED_SNAPSHOT_TOTALS,
    build_source_pk,
    validate_account_set_snapshots,
    validate_balance_equations,
    validate_snapshot,
    validate_voucher_balances,
    validate_voucher_header_totals,
)


class DatasetValidationError(RuntimeError):
    pass


TABLE_CONFIG = {
    "accounts": ("t_Account", KingdeeAccount),
    "vouchers": ("t_Voucher", KingdeeVoucher),
    "voucher_entries": ("t_VoucherEntry", KingdeeVoucherEntry),
    "balances": ("t_Balance", KingdeeBalance),
    "departments": ("t_Department", KingdeeDepartment),
    "employees": ("t_Base_Emp", KingdeeEmployee),
    "suppliers": ("t_Supplier", KingdeeSupplier),
    "currencies": ("t_Currency", KingdeeCurrency),
    "aux_items": ("t_Item", KingdeeAuxItem),
}


def _decimal(value, default="0") -> str:
    if value in (None, "", "\\N"):
        return default
    return str(Decimal(str(value)))


def _integer(value, default=0) -> int:
    if value in (None, "", "\\N"):
        return default
    return int(Decimal(str(value)))


def _boolean(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _date(value):
    if value in (None, "", "\\N"):
        return None
    return date.fromisoformat(str(value)[:10])


def _datetime(value):
    if value in (None, "", "\\N"):
        return None
    normalized = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        try:
            return datetime.fromisoformat(normalized[:19])
        except ValueError:
            return None


def normalize_voucher_entry(row: dict) -> dict:
    amount = _decimal(row.get("FAmount"))
    is_debit = _integer(row.get("FDC")) == 1
    return {
        "debit_amount": amount if is_debit else "0",
        "credit_amount": "0" if is_debit else amount,
    }


def _split_signed_balance(value) -> tuple[str, str]:
    amount = Decimal(_decimal(value))
    return (str(amount), "0") if amount >= 0 else ("0", str(-amount))


def normalize_balance(row: dict) -> dict:
    opening_debit, opening_credit = _split_signed_balance(row.get("FBeginBalance"))
    closing_debit, closing_credit = _split_signed_balance(row.get("FEndBalance"))
    return {
        "opening_debit": opening_debit,
        "opening_credit": opening_credit,
        "period_debit": _decimal(row.get("FDebit")),
        "period_credit": _decimal(row.get("FCredit")),
        "closing_debit": closing_debit,
        "closing_credit": closing_credit,
    }


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise DatasetValidationError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
    return rows


def verify_dataset_files(manifest_path: Path) -> dict:
    manifest = _load_json(manifest_path)
    manifest["_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    for item in manifest.get("files", []):
        path = manifest_path.parent / item["path"]
        if not path.is_file():
            raise DatasetValidationError(f"missing dataset file: {item['path']}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest.lower() != str(item["sha256"]).lower():
            raise DatasetValidationError(f"SHA-256 mismatch: {item['path']}")
        actual_rows = sum(1 for line in path.open("r", encoding="utf-8-sig") if line.strip())
        if actual_rows != int(item["rows"]):
            raise DatasetValidationError(
                f"row count mismatch: {item['path']} expected {item['rows']} received {actual_rows}"
            )
    return manifest


def load_dataset(manifest_path: Path) -> tuple[dict, dict[str, dict[str, list[dict]]]]:
    manifest = verify_dataset_files(manifest_path)
    datasets = {}
    for account_set in manifest.get("account_sets", []):
        database = account_set["database"]
        datasets[database] = {
            name: load_jsonl(manifest_path.parent / relative_path)
            for name, relative_path in account_set["tables"].items()
        }
    return manifest, datasets


def validate_dataset(manifest: dict, datasets: dict) -> dict:
    official = [item for item in manifest.get("account_sets", []) if item.get("classification") == "official"]
    if len(official) != 3:
        raise DatasetValidationError(f"expected 3 official account sets, received {len(official)}")
    totals = {
        name: sum(len(datasets[item["database"]].get(name, [])) for item in official)
        for name in EXPECTED_SNAPSHOT_TOTALS
    }
    snapshot_result = validate_snapshot(totals)
    per_account_set = {
        item["database"]: {
            name: len(datasets[item["database"]].get(name, []))
            for name in EXPECTED_SNAPSHOT_TOTALS
        }
        for item in official
    }
    account_set_result = validate_account_set_snapshots(per_account_set)
    entries = []
    headers = []
    balance_rows = []
    for item in official:
        database = item["database"]
        for row in datasets[database]["vouchers"]:
            headers.append({
                "account_set": database,
                "voucher_id": row["FVoucherID"],
                "debit": _decimal(row.get("FDebitTotal")),
                "credit": _decimal(row.get("FCreditTotal")),
            })
        for row in datasets[database]["voucher_entries"]:
            amounts = normalize_voucher_entry(row)
            entries.append({
                "account_set": database,
                "voucher_id": row["FVoucherID"],
                "debit": amounts["debit_amount"],
                "credit": amounts["credit_amount"],
            })
        for row in datasets[database]["balances"]:
            split = normalize_balance(row)
            balance_rows.append({
                "account_set": database,
                "source_pk": build_source_pk(
                    database, row["FYear"], row["FPeriod"], row["FAccountID"],
                    row.get("FDetailID") or "", row.get("FCurrencyID") or "",
                    row.get("FFrameWorkID") or "", row.get("FIsAdjustPeriod") or 0,
                ),
                **split,
            })
    balance_errors = validate_voucher_balances(entries)
    header_errors = validate_voucher_header_totals(headers, entries)
    balance_equation_errors = validate_balance_equations(balance_rows)
    errors = [*snapshot_result["errors"], *account_set_result["errors"]]
    if balance_errors:
        errors.append(f"{len(balance_errors)} unbalanced vouchers")
    if header_errors:
        errors.append(f"{len(header_errors)} voucher header total mismatches")
    if balance_equation_errors:
        errors.append(f"{len(balance_equation_errors)} balance equation mismatches")
    result = {
        "status": "ready" if not errors else "blocked",
        "totals": totals,
        "account_set_totals": per_account_set,
        "errors": errors,
        "unbalanced_vouchers": balance_errors,
        "voucher_header_mismatches": header_errors,
        "balance_equation_mismatches": balance_equation_errors,
    }
    if errors:
        raise DatasetValidationError(json.dumps(result, ensure_ascii=False))
    return result


async def _upsert(db, model, values: list[dict], constraint: str, update_columns: Iterable[str]):
    if not values:
        return
    for start in range(0, len(values), 500):
        chunk = values[start:start + 500]
        stmt = insert(model).values(chunk)
        primary_keys = {column.name for column in model.__table__.primary_key.columns}
        update_names = [name for name in update_columns if name not in primary_keys]
        stmt = stmt.on_conflict_do_update(
            constraint=constraint,
            set_={name: getattr(stmt.excluded, name) for name in update_names},
        )
        await db.execute(stmt)


def _lineage(database: str, source_pk: str, batch_id: str, row: dict) -> dict:
    return {
        "source_system": "kingdee",
        "source_database": database,
        "source_pk": source_pk,
        "import_batch_id": batch_id,
        "source_updated_at": _datetime(row.get("FModifyDate") or row.get("FModifyTime")),
        "raw_data": row,
    }


def _account_values(database: str, batch_id: str, row: dict) -> dict:
    return {
        **_lineage(database, build_source_pk(database, row["FAccountID"]), batch_id, row),
        "account_id": str(row["FAccountID"]),
        "account_code": str(row.get("FNumber") or ""),
        "account_name": str(row.get("FName") or ""),
        "parent_account_id": str(row.get("FParentID") or ""),
        "account_level": _integer(row.get("FLevel")),
        "account_class": str(row.get("FGroupID") or ""),
        "balance_direction": "debit" if _integer(row.get("FDC"), 1) == 1 else "credit",
        "is_detail": _boolean(row.get("FDetail")),
        "is_cash": _boolean(row.get("FIsCash")),
        "is_bank": _boolean(row.get("FIsBank")),
        "is_contact": _boolean(row.get("FContact")),
        "is_cash_flow": _boolean(row.get("FIsCashFlow")),
    }


def _official_batch_values(manifest: dict, datasets: dict, validation: dict) -> list[dict]:
    values = []
    for item in manifest["account_sets"]:
        if item.get("classification") != "official":
            continue
        database = item["database"]
        rows = datasets[database]
        values.append({
            "batch_id": f"{manifest['run_id']}:{database}",
            "run_id": manifest["run_id"],
            "source_database": database,
            "restored_database": item.get("restored_database"),
            "backup_file": item["backup_file"],
            "backup_sha256": item["backup_sha256"],
            "manifest_sha256": manifest.get("_manifest_sha256"),
            "status": "importing",
            "expected_counts": EXPECTED_ACCOUNT_SET_TOTALS[database],
            "actual_counts": {name: len(rows.get(name, [])) for name in EXPECTED_SNAPSHOT_TOTALS},
            "validation_result": validation,
            "error_message": None,
            "completed_at": None,
        })
    return values


async def _record_batch_failure(batch_ids: list[str], exc: Exception) -> None:
    message = f"{type(exc).__name__}: {exc}"[:4000]
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(
                update(KingdeeImportBatch)
                .where(KingdeeImportBatch.batch_id.in_(batch_ids))
                .values(status="failed", error_message=message, completed_at=datetime.now(timezone.utc))
            )


async def _import_dataset_transaction(manifest: dict, datasets: dict, validation: dict) -> dict:
    batch_ids = []
    async with AsyncSessionLocal() as db:
        async with db.begin():
            for item in manifest["account_sets"]:
                if item.get("classification") != "official":
                    continue
                database = item["database"]
                rows = datasets[database]
                batch_id = f"{manifest['run_id']}:{database}"
                batch_ids.append(batch_id)
                batch_values = {
                    "batch_id": batch_id,
                    "run_id": manifest["run_id"],
                    "source_database": database,
                    "restored_database": item.get("restored_database"),
                    "backup_file": item["backup_file"],
                    "backup_sha256": item["backup_sha256"],
                    "manifest_sha256": manifest.get("_manifest_sha256"),
                    "status": "importing",
                    "expected_counts": EXPECTED_ACCOUNT_SET_TOTALS[database],
                    "actual_counts": {name: len(rows.get(name, [])) for name in EXPECTED_SNAPSHOT_TOTALS},
                    "validation_result": validation,
                    "error_message": None,
                }
                await _upsert(db, KingdeeImportBatch, [batch_values], "kingdee_import_batch_pkey", batch_values.keys())
                account_values = [_account_values(database, batch_id, row) for row in rows["accounts"]]
                await _upsert(db, KingdeeAccount, account_values, "uq_kingdee_account_source", account_values[0].keys() if account_values else [])

                voucher_values = []
                for row in rows["vouchers"]:
                    voucher_values.append({
                        **_lineage(database, build_source_pk(database, row["FVoucherID"]), batch_id, row),
                        "voucher_id": str(row["FVoucherID"]), "voucher_no": str(row.get("FNumber") or ""),
                        "voucher_group": str(row.get("FGroupID") or ""), "voucher_date": _date(row["FDate"]),
                        "fiscal_year": _integer(row["FYear"]), "fiscal_period": _integer(row["FPeriod"]),
                        "source_status": "posted" if _boolean(row.get("FPosted")) else "checked" if _boolean(row.get("FChecked")) else "unposted",
                        "is_checked": _boolean(row.get("FChecked")), "is_posted": _boolean(row.get("FPosted")),
                        "preparer_name": str(row.get("FPreparerID") or ""), "checker_name": str(row.get("FCheckerID") or ""),
                        "poster_name": str(row.get("FPosterID") or ""), "total_debit": _decimal(row.get("FDebitTotal")),
                        "total_credit": _decimal(row.get("FCreditTotal")),
                    })
                await _upsert(db, KingdeeVoucher, voucher_values, "uq_kingdee_voucher_source", voucher_values[0].keys() if voucher_values else [])

                entry_values = []
                for row in rows["voucher_entries"]:
                    amounts = normalize_voucher_entry(row)
                    entry_values.append({
                        **_lineage(database, build_source_pk(database, row["FVoucherID"], row["FEntryID"]), batch_id, row),
                        "voucher_id": str(row["FVoucherID"]), "entry_id": str(row["FEntryID"]),
                        "line_no": _integer(row.get("FEntryID")), "account_id": str(row["FAccountID"]),
                        "summary": row.get("FExplanation"), "currency_id": str(row.get("FCurrencyID") or ""),
                        "exchange_rate": _decimal(row.get("FExchangeRate"), "1"), **amounts,
                        "quantity": _decimal(row.get("FQuantity")), "detail_id": str(row.get("FDetailID") or ""),
                        "settlement_no": row.get("FSettleNo"),
                    })
                await _upsert(db, KingdeeVoucherEntry, entry_values, "uq_kingdee_voucher_entry_source", entry_values[0].keys() if entry_values else [])

                balance_values = []
                for row in rows["balances"]:
                    source_pk = build_source_pk(database, row["FYear"], row["FPeriod"], row["FAccountID"], row.get("FDetailID") or "", row.get("FCurrencyID") or "", row.get("FFrameWorkID") or "", row.get("FIsAdjustPeriod") or 0)
                    split = normalize_balance(row)
                    balance_values.append({
                        **_lineage(database, source_pk, batch_id, row), "fiscal_year": _integer(row["FYear"]),
                        "fiscal_period": _integer(row["FPeriod"]), "account_id": str(row["FAccountID"]),
                        "detail_id": str(row.get("FDetailID") or ""), "currency_id": str(row.get("FCurrencyID") or ""),
                        "framework_id": str(row.get("FFrameWorkID") or ""), "is_adjust_period": _boolean(row.get("FIsAdjustPeriod")),
                        **split, "ytd_debit": _decimal(row.get("FYtdDebit")), "ytd_credit": _decimal(row.get("FYtdCredit")),
                    })
                await _upsert(db, KingdeeBalance, balance_values, "uq_kingdee_balance_source", balance_values[0].keys() if balance_values else [])

                auxiliary = (
                    ("departments", KingdeeDepartment, "uq_kingdee_department_source", "FItemID", lambda row: {"department_id": str(row["FItemID"]), "department_code": row.get("FNumber"), "department_name": row.get("FName"), "parent_department_id": str(row.get("FParentID") or "")}),
                    ("employees", KingdeeEmployee, "uq_kingdee_employee_source", "FItemID", lambda row: {"employee_id": str(row["FItemID"]), "employee_code": row.get("FNumber"), "employee_name": row.get("FName"), "department_id": str(row.get("FDepartmentID") or row.get("FItemDepID") or ""), "employment_status": "left" if row.get("FLeaveDate") not in (None, "", "\\N") else "active"}),
                    ("suppliers", KingdeeSupplier, "uq_kingdee_supplier_source", "FItemID", lambda row: {"supplier_id": str(row["FItemID"]), "supplier_code": row.get("FNumber"), "supplier_name": row.get("FName"), "contact_name": row.get("FContact")}),
                    ("currencies", KingdeeCurrency, "uq_kingdee_currency_source", "FCurrencyID", lambda row: {"currency_id": str(row["FCurrencyID"]), "currency_code": row.get("FNumber"), "currency_name": row.get("FName"), "precision": _integer(row.get("FScale"), 2)}),
                    ("aux_items", KingdeeAuxItem, "uq_kingdee_aux_item_source", "FItemID", lambda row: {"item_id": str(row["FItemID"]), "item_class": str(row.get("FItemClassID") or ""), "item_code": row.get("FNumber"), "item_name": row.get("FName")}),
                )
                for name, model, constraint, key, mapper in auxiliary:
                    values = [{**_lineage(database, build_source_pk(database, row[key]), batch_id, row), **mapper(row)} for row in rows.get(name, [])]
                    await _upsert(db, model, values, constraint, values[0].keys() if values else [])

                entity_values = {
                    "entity_code": database, "entity_name": item["company_name"], "short_name": item.get("short_name"),
                    "source_system": "kingdee", "source_database": database,
                    "source_pk": build_source_pk(database, "legal_entity"), "import_batch_id": batch_id,
                    "source_updated_at": None, "account_set_code": database,
                    "start_period": item.get("start_period"), "current_period": item.get("current_period"), "status": "active",
                }
                await _upsert(db, DimLegalEntity, [entity_values], "uq_legal_entity_source_account_set", entity_values.keys())
                entity = (await db.execute(select(DimLegalEntity).where(DimLegalEntity.account_set_code == database))).scalar_one()

                dim_accounts = [{
                    "legal_entity_id": entity.id, "source_account_id": value["account_id"], "account_code": value["account_code"],
                    "account_name": value["account_name"], "account_level": value["account_level"], "account_type": value["account_class"],
                    "balance_direction": value["balance_direction"], "is_cash": value["is_cash"], "is_bank": value["is_bank"],
                    "is_active": True, "source_system": "kingdee", "source_database": database,
                    "source_pk": value["source_pk"], "import_batch_id": batch_id, "source_updated_at": value["source_updated_at"],
                } for value in account_values]
                await _upsert(db, DimFinanceAccount, dim_accounts, "uq_finance_account_entity_source", dim_accounts[0].keys() if dim_accounts else [])
                dim_account_map = dict((await db.execute(select(DimFinanceAccount.source_account_id, DimFinanceAccount.id).where(DimFinanceAccount.legal_entity_id == entity.id))).all())

                dwd_vouchers = [{
                    "legal_entity_id": entity.id, "voucher_no": value["voucher_no"], "voucher_group": value["voucher_group"],
                    "voucher_date": value["voucher_date"], "fiscal_year": value["fiscal_year"], "fiscal_period": value["fiscal_period"],
                    "source_status": value["source_status"], "is_checked": value["is_checked"], "is_posted": value["is_posted"],
                    "preparer_name": value["preparer_name"], "total_debit": value["total_debit"], "total_credit": value["total_credit"],
                    "source_system": "kingdee", "source_database": database, "source_pk": value["source_pk"],
                    "import_batch_id": batch_id, "source_updated_at": value["source_updated_at"],
                } for value in voucher_values]
                await _upsert(db, DwdGlVoucher, dwd_vouchers, "uq_dwd_gl_voucher_source", dwd_vouchers[0].keys() if dwd_vouchers else [])
                voucher_map = dict((await db.execute(select(DwdGlVoucher.source_pk, DwdGlVoucher.id).where(DwdGlVoucher.legal_entity_id == entity.id))).all())
                dwd_entries = []
                for value in entry_values:
                    voucher_pk = build_source_pk(database, value["voucher_id"])
                    dwd_entries.append({
                        "voucher_id": voucher_map[voucher_pk], "legal_entity_id": entity.id, "line_no": value["line_no"],
                        "finance_account_id": dim_account_map[value["account_id"]], "account_code": None, "summary": value["summary"],
                        "debit_amount": value["debit_amount"], "credit_amount": value["credit_amount"], "currency_code": value["currency_id"],
                        "exchange_rate": value["exchange_rate"], "quantity": value["quantity"], "auxiliary_detail_id": value["detail_id"],
                        "source_system": "kingdee", "source_database": database, "source_pk": value["source_pk"],
                        "import_batch_id": batch_id, "source_updated_at": value["source_updated_at"],
                    })
                await _upsert(db, DwdGlVoucherEntry, dwd_entries, "uq_dwd_gl_voucher_entry_source", dwd_entries[0].keys() if dwd_entries else [])
                dwd_balances = [{
                    "legal_entity_id": entity.id, "finance_account_id": dim_account_map[value["account_id"]],
                    "period": f"{value['fiscal_year']:04d}-{value['fiscal_period']:02d}", "detail_id": value["detail_id"],
                    "currency_code": value["currency_id"] or "CNY", "opening_debit": value["opening_debit"],
                    "opening_credit": value["opening_credit"], "period_debit": value["period_debit"], "period_credit": value["period_credit"],
                    "closing_debit": value["closing_debit"], "closing_credit": value["closing_credit"],
                    "source_system": "kingdee", "source_database": database, "source_pk": value["source_pk"],
                    "import_batch_id": batch_id, "source_updated_at": value["source_updated_at"],
                } for value in balance_values]
                await _upsert(db, DwdGlBalanceMonthly, dwd_balances, "uq_dwd_gl_balance_source", dwd_balances[0].keys() if dwd_balances else [])

                await db.execute(insert(KingdeeImportBatch).values(
                    batch_id=batch_id, run_id=manifest["run_id"], source_database=database,
                    backup_file=item["backup_file"], backup_sha256=item["backup_sha256"],
                    status="validated", completed_at=datetime.now(timezone.utc),
                ).on_conflict_do_update(constraint="kingdee_import_batch_pkey", set_={
                    "status": "validated", "completed_at": datetime.now(timezone.utc), "validation_result": validation,
                }))
    return {"status": "validated", "batch_ids": batch_ids, "validation": validation}


async def import_dataset(manifest: dict, datasets: dict, validation: dict) -> dict:
    batch_values = _official_batch_values(manifest, datasets, validation)
    batch_ids = [value["batch_id"] for value in batch_values]
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await _upsert(
                db,
                KingdeeImportBatch,
                batch_values,
                "kingdee_import_batch_pkey",
                batch_values[0].keys() if batch_values else [],
            )
    try:
        return await _import_dataset_transaction(manifest, datasets, validation)
    except Exception as exc:
        await _record_batch_failure(batch_ids, exc)
        raise


async def run(manifest_path: Path, apply: bool) -> dict:
    manifest, datasets = load_dataset(manifest_path)
    validation = validate_dataset(manifest, datasets)
    if not apply:
        return {"status": "validated_only", "validation": validation}
    return await import_dataset(manifest, datasets, validation)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--apply", action="store_true", help="write validated data to PostgreSQL")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.manifest, args.apply)), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
