"""Read and validate native Kingdee migration snapshots for Finance V2 history.

This module only reads the locally exported snapshot.  It never connects to,
writes to, or repairs Kingdee/ODS tables.  Database staging and publication are
intentionally a separate responsibility.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


class KingdeeHistorySourceError(ValueError):
    """The immutable snapshot cannot be safely staged as Finance V2 history."""


@dataclass(frozen=True)
class KingdeeHistoryLine:
    source_pk: str
    line_no: int
    account_code: str
    summary: str | None
    currency_code: str
    exchange_rate: str
    debit_amount: str
    credit_amount: str
    raw_dimensions: dict[str, str]


@dataclass(frozen=True)
class KingdeeHistoryRecord:
    source_system: str
    source_database: str
    source_pk: str
    source_hash: str
    voucher_no: str | None
    voucher_group: str | None
    voucher_date: date
    fiscal_year: int
    fiscal_period: int
    source_status: str
    total_debit: str
    total_credit: str
    lines: tuple[KingdeeHistoryLine, ...]
    raw_payload: dict[str, Any]


_REQUIRED_TABLES = frozenset({"t_Account", "t_Voucher", "t_VoucherEntry"})
_MONEY_QUANTUM = Decimal("0.01")


def _null(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if text in {"", "\\N"} else text


def _required(row: dict[str, str], field: str, context: str) -> str:
    value = _null(row.get(field))
    if value is None:
        raise KingdeeHistorySourceError(f"{context}: missing {field}")
    return value


def _money(value: Any, context: str, *, allow_negative: bool = False) -> str:
    raw = _null(value)
    if raw is None:
        return "0.00"
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise KingdeeHistorySourceError(f"{context}: invalid amount {raw!r}") from exc
    if not amount.is_finite() or (amount < 0 and not allow_negative):
        qualifier = "finite" if allow_negative else "a non-negative finite"
        raise KingdeeHistorySourceError(f"{context}: amount must be {qualifier} value")
    rounded = amount.quantize(_MONEY_QUANTUM)
    if rounded != amount:
        raise KingdeeHistorySourceError(f"{context}: amount has more than two decimal places")
    return f"{rounded:.2f}"


def _decimal(value: Any, context: str) -> str:
    raw = _null(value)
    if raw is None:
        return "1"
    try:
        result = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise KingdeeHistorySourceError(f"{context}: invalid decimal {raw!r}") from exc
    if not result.is_finite() or result <= 0:
        raise KingdeeHistorySourceError(f"{context}: exchange rate must be positive and finite")
    return format(result.normalize(), "f")


def _integer(value: Any, context: str) -> int:
    raw = _required({"value": value}, "value", context)
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise KingdeeHistorySourceError(f"{context}: invalid integer {raw!r}") from exc
    if parsed != parsed.to_integral_value():
        raise KingdeeHistorySourceError(f"{context}: must be an integer")
    return int(parsed)


def _date(value: Any, context: str) -> date:
    raw = _required({"value": value}, "value", context)
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise KingdeeHistorySourceError(f"{context}: invalid date {raw!r}") from exc


def _safe_snapshot_path(snapshot_root: Path, relative_path: str) -> Path:
    candidate = (snapshot_root / relative_path).resolve()
    try:
        candidate.relative_to(snapshot_root.resolve())
    except ValueError as exc:
        raise KingdeeHistorySourceError(f"snapshot table path escapes root: {relative_path}") from exc
    return candidate


def _read_verified_table(snapshot_root: Path, metadata: dict[str, Any]) -> list[dict[str, str]]:
    table_name = str(metadata.get("table") or "")
    relative_path = _null(metadata.get("file"))
    expected_hash = _null(metadata.get("sha256"))
    if metadata.get("status") != "ok" or not table_name or relative_path is None or expected_hash is None:
        raise KingdeeHistorySourceError(f"{table_name or 'unknown table'}: incomplete or failed snapshot metadata")
    path = _safe_snapshot_path(snapshot_root, relative_path)
    if not path.is_file():
        raise KingdeeHistorySourceError(f"{table_name}: snapshot file is missing")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest.lower() != expected_hash.lower():
        raise KingdeeHistorySourceError(f"{table_name}: SHA-256 mismatch")
    try:
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise KingdeeHistorySourceError(f"{table_name}: cannot read gzip CSV snapshot") from exc
    if len(rows) != _integer(metadata.get("rows"), f"{table_name}.rows"):
        raise KingdeeHistorySourceError(f"{table_name}: row count mismatch")
    return rows


def _canonical_row(row: dict[str, str]) -> dict[str, str | None]:
    return {key: _null(value) for key, value in sorted(row.items())}


def _source_hash(
    header: dict[str, str],
    entries: list[dict[str, str]],
    account_codes: dict[str, str] | None = None,
) -> str:
    payload = {
        "header": _canonical_row(header),
        "entries": [_canonical_row(entry) for entry in sorted(entries, key=lambda row: _integer(row.get("FEntryID"), "FEntryID"))],
        "account_codes": dict(sorted((account_codes or {}).items())),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _status(header: dict[str, str]) -> str:
    def truthy(value: Any) -> bool:
        return (_null(value) or "").lower() in {"1", "true", "yes"}

    return "posted" if truthy(header.get("FPosted")) else "checked" if truthy(header.get("FChecked")) else "unposted"


def _record_from_rows(database: str, header: dict[str, str], entries: list[dict[str, str]], account_codes: dict[str, str]) -> KingdeeHistoryRecord:
    voucher_id = _required(header, "FVoucherID", f"{database}.voucher")
    context = f"{database}.voucher:{voucher_id}"
    if not entries:
        raise KingdeeHistorySourceError(f"{context}: has no voucher entries")

    history_lines: list[KingdeeHistoryLine] = []
    debit_total = Decimal("0.00")
    credit_total = Decimal("0.00")
    for entry in sorted(entries, key=lambda row: _integer(row.get("FEntryID"), f"{context}.FEntryID")):
        entry_id = _required(entry, "FEntryID", f"{context}.entry")
        account_id = _required(entry, "FAccountID", f"{context}.entry:{entry_id}")
        account_code = account_codes.get(account_id)
        if account_code is None:
            raise KingdeeHistorySourceError(f"{context}.entry:{entry_id}: unknown account {account_id}")
        direction = _integer(entry.get("FDC"), f"{context}.entry:{entry_id}.FDC")
        if direction not in {0, 1}:
            raise KingdeeHistorySourceError(f"{context}.entry:{entry_id}: unsupported FDC {direction}")
        amount = _money(entry.get("FAmount"), f"{context}.entry:{entry_id}.FAmount", allow_negative=True)
        debit = amount if direction == 1 else "0.00"
        credit = amount if direction == 0 else "0.00"
        debit_total += Decimal(debit)
        credit_total += Decimal(credit)
        detail_id = _null(entry.get("FDetailID"))
        history_lines.append(
            KingdeeHistoryLine(
                source_pk=f"{database}:voucher:{voucher_id}:entry:{entry_id}",
                line_no=_integer(entry_id, f"{context}.entry"),
                account_code=account_code,
                summary=_null(entry.get("FExplanation")),
                currency_code=_null(entry.get("FCurrencyID")) or "CNY",
                exchange_rate=_decimal(entry.get("FExchangeRate"), f"{context}.entry:{entry_id}.FExchangeRate"),
                debit_amount=debit,
                credit_amount=credit,
                raw_dimensions={} if detail_id is None else {"kingdee_detail_id": detail_id},
            )
        )

    expected_debit = Decimal(_money(header.get("FDebitTotal"), f"{context}.FDebitTotal"))
    expected_credit = Decimal(_money(header.get("FCreditTotal"), f"{context}.FCreditTotal"))
    if debit_total != credit_total:
        raise KingdeeHistorySourceError(f"{context}: debit and credit are not balanced")
    if (expected_debit, expected_credit) != (debit_total, credit_total):
        raise KingdeeHistorySourceError(f"{context}: header total mismatch")

    entry_account_ids = {
        line.source_pk: _required(entry, "FAccountID", context)
        for line, entry in zip(history_lines, sorted(entries, key=lambda row: _integer(row.get("FEntryID"), f"{context}.FEntryID")))
    }
    raw_payload = {
        "header": _canonical_row(header),
        "entries": [_canonical_row(entry) for entry in entries],
        "account_codes": {account_id: account_codes[account_id] for account_id in sorted(set(entry_account_ids.values()))},
        "entry_account_ids": entry_account_ids,
    }
    return KingdeeHistoryRecord(
        source_system="kingdee",
        source_database=database,
        source_pk=f"{database}:voucher:{voucher_id}",
        source_hash=_source_hash(header, entries, raw_payload["account_codes"]),
        voucher_no=_null(header.get("FNumber")),
        voucher_group=_null(header.get("FGroupID")),
        voucher_date=_date(header.get("FDate"), f"{context}.FDate"),
        fiscal_year=_integer(header.get("FYear"), f"{context}.FYear"),
        fiscal_period=_integer(header.get("FPeriod"), f"{context}.FPeriod"),
        source_status=_status(header),
        total_debit=f"{debit_total:.2f}",
        total_credit=f"{credit_total:.2f}",
        lines=tuple(history_lines),
        raw_payload=raw_payload,
    )


def load_kingdee_history_records(manifest_path: Path) -> list[KingdeeHistoryRecord]:
    """Return validated historical vouchers from the official native snapshot only."""

    manifest_path = manifest_path.resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise KingdeeHistorySourceError("cannot read Kingdee snapshot manifest") from exc
    if not isinstance(manifest, dict):
        raise KingdeeHistorySourceError("Kingdee snapshot manifest must be an object")
    official_databases = sorted(
        str(item.get("database"))
        for item in manifest.get("account_sets", [])
        if isinstance(item, dict) and item.get("classification") == "official" and item.get("database")
    )
    if not official_databases:
        raise KingdeeHistorySourceError("Kingdee snapshot has no official account sets")
    databases = {
        str(item.get("database")): item
        for item in manifest.get("databases", [])
        if isinstance(item, dict) and item.get("database")
    }
    records: list[KingdeeHistoryRecord] = []
    for database in official_databases:
        metadata = databases.get(database)
        if metadata is None:
            raise KingdeeHistorySourceError(f"{database}: missing database snapshot metadata")
        table_metadata = {
            str(item.get("table")): item
            for item in metadata.get("tables", [])
            if isinstance(item, dict) and item.get("table") in _REQUIRED_TABLES
        }
        missing_tables = sorted(_REQUIRED_TABLES.difference(table_metadata))
        if missing_tables:
            raise KingdeeHistorySourceError(f"{database}: missing required table metadata: {', '.join(missing_tables)}")
        accounts = _read_verified_table(manifest_path.parent / "databases" / database, table_metadata["t_Account"])
        vouchers = _read_verified_table(manifest_path.parent / "databases" / database, table_metadata["t_Voucher"])
        entries = _read_verified_table(manifest_path.parent / "databases" / database, table_metadata["t_VoucherEntry"])
        account_codes = {
            _required(row, "FAccountID", f"{database}.account"): _required(row, "FNumber", f"{database}.account")
            for row in accounts
        }
        entries_by_voucher: dict[str, list[dict[str, str]]] = {}
        for entry in entries:
            entries_by_voucher.setdefault(_required(entry, "FVoucherID", f"{database}.entry"), []).append(entry)
        for header in vouchers:
            records.append(_record_from_rows(database, header, entries_by_voucher.get(_required(header, "FVoucherID", f"{database}.voucher"), []), account_codes))
    return sorted(records, key=lambda record: (record.source_database, record.voucher_date, record.source_pk))
