import hashlib
import json

import pytest

from scripts.import_kingdee_finance import (
    DatasetValidationError,
    _datetime,
    normalize_balance,
    normalize_voucher_entry,
    verify_dataset_files,
)


def test_binary_rowversion_is_not_treated_as_source_timestamp():
    assert _datetime("AAAAAAAIuSA=") is None


def test_entry_direction_maps_kingdee_fdc_without_guessing_signs():
    debit = normalize_voucher_entry({"FDC": 1, "FAmount": "12.50"})
    credit = normalize_voucher_entry({"FDC": 0, "FAmount": "12.50"})

    assert debit["debit_amount"] == "12.50"
    assert debit["credit_amount"] == "0"
    assert credit["debit_amount"] == "0"
    assert credit["credit_amount"] == "12.50"


def test_balance_uses_signed_source_amount_for_opening_and_closing_columns():
    debit = normalize_balance({"FBeginBalance": "8", "FEndBalance": "10", "FDebit": "4", "FCredit": "2"})
    credit = normalize_balance({"FBeginBalance": "-8", "FEndBalance": "-10", "FDebit": "4", "FCredit": "2"})

    assert debit["opening_debit"] == "8"
    assert debit["opening_credit"] == "0"
    assert credit["closing_debit"] == "0"
    assert credit["closing_credit"] == "10"


def test_manifest_hash_mismatch_blocks_before_database_writes(tmp_path):
    data_file = tmp_path / "accounts.jsonl"
    data_file.write_text('{"FAccountID":1}\n', encoding="utf-8")
    manifest = {
        "files": [{"path": "accounts.jsonl", "sha256": "0" * 64, "rows": 1}]
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(DatasetValidationError, match="SHA-256"):
        verify_dataset_files(manifest_path)

    manifest["files"][0]["sha256"] = hashlib.sha256(data_file.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert verify_dataset_files(manifest_path)["files"][0]["rows"] == 1
