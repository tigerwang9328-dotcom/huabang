import csv
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from app.services.finance_v2.kingdee_history_loader import (
    KingdeeHistorySourceError,
    load_kingdee_history_records,
)


def _write_gzip_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _table_metadata(root: Path, table: str) -> dict:
    relative_path = f"data/dbo.{table}.csv.gz"
    path = root / relative_path
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        row_count = sum(1 for _ in csv.DictReader(stream))
    return {
        "schema": "dbo",
        "table": table,
        "file": relative_path,
        "rows": row_count,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "status": "ok",
    }


def _write_snapshot(
    root: Path,
    *,
    credit_total: str = "100.00",
    signed_red_lines: bool = False,
    debit_account_code: str = "1001",
) -> Path:
    database = "AIS_OFFICIAL"
    database_root = root / "databases" / database
    _write_gzip_csv(
        database_root / "data/dbo.t_Account.csv.gz",
        ["FAccountID", "FNumber", "FName"],
        [
            {"FAccountID": "1000", "FNumber": debit_account_code, "FName": "库存现金"},
            {"FAccountID": "2000", "FNumber": "2202", "FName": "应付账款"},
        ],
    )
    _write_gzip_csv(
        database_root / "data/dbo.t_Voucher.csv.gz",
        ["FVoucherID", "FDate", "FYear", "FPeriod", "FGroupID", "FNumber", "FDebitTotal", "FCreditTotal", "FPosted", "FChecked"],
        [{"FVoucherID": "42", "FDate": "2026-06-30T00:00:00.0000000", "FYear": "2026", "FPeriod": "6", "FGroupID": "1", "FNumber": "8", "FDebitTotal": "90.00" if signed_red_lines else "100.00", "FCreditTotal": "90.00" if signed_red_lines else credit_total, "FPosted": "true", "FChecked": "true"}],
    )
    _write_gzip_csv(
        database_root / "data/dbo.t_VoucherEntry.csv.gz",
        ["FVoucherID", "FEntryID", "FExplanation", "FAccountID", "FDetailID", "FCurrencyID", "FExchangeRate", "FDC", "FAmount"],
        [
            {"FVoucherID": "42", "FEntryID": "0", "FExplanation": "借方", "FAccountID": "1000", "FDetailID": "\\N", "FCurrencyID": "1", "FExchangeRate": "1", "FDC": "1", "FAmount": "100.00"},
            {"FVoucherID": "42", "FEntryID": "1", "FExplanation": "贷方", "FAccountID": "2000", "FDetailID": "\\N", "FCurrencyID": "1", "FExchangeRate": "1", "FDC": "0", "FAmount": "100.00"},
        ] + ([
            {"FVoucherID": "42", "FEntryID": "2", "FExplanation": "红字借方", "FAccountID": "1000", "FDetailID": "\\N", "FCurrencyID": "1", "FExchangeRate": "1", "FDC": "1", "FAmount": "-10.00"},
            {"FVoucherID": "42", "FEntryID": "3", "FExplanation": "红字贷方", "FAccountID": "2000", "FDetailID": "\\N", "FCurrencyID": "1", "FExchangeRate": "1", "FDC": "0", "FAmount": "-10.00"},
        ] if signed_red_lines else []),
    )
    manifest = {
        "run_id": "K3MIG_TEST",
        "account_sets": [
            {"database": database, "classification": "official"},
            {"database": "AIS_TEST", "classification": "test"},
        ],
        "databases": [
            {
                "database": database,
                "tables": [_table_metadata(database_root, name) for name in ("t_Account", "t_Voucher", "t_VoucherEntry")],
            }
        ],
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest_path


def test_loader_reads_only_official_snapshot_rows_and_creates_stable_history_facts(tmp_path: Path):
    records = load_kingdee_history_records(_write_snapshot(tmp_path))

    assert len(records) == 1
    record = records[0]
    assert record.source_database == "AIS_OFFICIAL"
    assert record.source_pk == "AIS_OFFICIAL:voucher:42"
    assert record.total_debit == "100.00"
    assert record.total_credit == "100.00"
    assert record.source_status == "posted"
    assert [line.account_code for line in record.lines] == ["1001", "2202"]
    assert [(line.debit_amount, line.credit_amount) for line in record.lines] == [("100.00", "0.00"), ("0.00", "100.00")]
    assert len(record.source_hash) == 64


def test_loader_blocks_unbalanced_voucher_before_any_history_database_write(tmp_path: Path):
    with pytest.raises(KingdeeHistorySourceError, match="header total mismatch"):
        load_kingdee_history_records(_write_snapshot(tmp_path, credit_total="99.00"))


def test_loader_preserves_signed_red_entries_when_their_source_header_totals_match(tmp_path: Path):
    record = load_kingdee_history_records(_write_snapshot(tmp_path, signed_red_lines=True))[0]

    assert record.total_debit == "90.00"
    assert record.total_credit == "90.00"
    assert [(line.debit_amount, line.credit_amount) for line in record.lines] == [
        ("100.00", "0.00"),
        ("0.00", "100.00"),
        ("-10.00", "0.00"),
        ("0.00", "-10.00"),
    ]


def test_loader_hash_changes_when_referenced_kingdee_account_code_changes(tmp_path: Path):
    first = load_kingdee_history_records(_write_snapshot(tmp_path / "first"))[0]
    second = load_kingdee_history_records(_write_snapshot(tmp_path / "second", debit_account_code="1002"))[0]

    assert first.source_pk == second.source_pk
    assert first.source_hash != second.source_hash
