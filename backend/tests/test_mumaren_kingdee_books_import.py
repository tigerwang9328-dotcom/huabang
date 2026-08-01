import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("DB_PASSWORD", "test-only-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _canonical_snapshot(tmp_path: Path) -> Path:
    root = tmp_path / "canonical"
    root.mkdir()
    account_set = root / "AIS_TEST"
    account_set.mkdir()
    files = {
        "accounts.jsonl": [
            {"FAccountID": 1, "FNumber": "1001", "FName": "库存现金", "FDC": 1, "FLevel": 1},
            {"FAccountID": 2, "FNumber": "3001", "FName": "实收资本", "FDC": 0, "FLevel": 1},
            {"FAccountID": 3, "FNumber": "1122", "FName": "应收账款", "FDC": 1, "FLevel": 1},
        ],
        "vouchers.jsonl": [{"FVoucherID": 1, "FNumber": 1, "FDate": "2026-01-31T00:00:00", "FGroupID": 1, "FExplanation": "期初", "FEntryCount": 4, "FDebitTotal": 100, "FCreditTotal": 100}],
        "voucher_entries.jsonl": [
            {"FVoucherID": 1, "FEntryID": 0, "FAccountID": 1, "FDC": 1, "FAmount": 120},
            {"FVoucherID": 1, "FEntryID": 1, "FAccountID": 2, "FDC": 0, "FAmount": 120},
            {"FVoucherID": 1, "FEntryID": 2, "FAccountID": 1, "FDC": 1, "FAmount": -20},
            {"FVoucherID": 1, "FEntryID": 3, "FAccountID": 2, "FDC": 0, "FAmount": -20},
        ],
        "balances.jsonl": [{"FAccountID": 3, "FYear": 2026, "FPeriod": 1, "FDetailID": 0, "FCurrencyID": 0, "FBeginBalance": 80, "FDebit": 100, "FCredit": 20, "FEndBalance": 160}],
    }
    manifest_files = []
    for name, rows in files.items():
        path = account_set / name
        _write_jsonl(path, rows)
        rel = f"AIS_TEST/{name}"
        manifest_files.append({"path": rel, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows": len(rows)})
    manifest = {"run_id": "K3TEST", "account_sets": [{"database": "AIS_TEST", "company_name": "测试公司", "short_name": "测试公司", "start_period": "2026-01", "current_period": "2026-01", "tables": {key[:-6]: f"AIS_TEST/{key}" for key in files}}], "files": manifest_files}
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return root


def _replace_source_rows(root: Path, filename: str, rows: list[dict]) -> None:
    """Mutate a test snapshot and keep its manifest checksum authoritative."""
    path = root / "AIS_TEST" / filename
    _write_jsonl(path, rows)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        if item["path"] == f"AIS_TEST/{filename}":
            item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            item["rows"] = len(rows)
            break
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def test_canonical_plan_creates_readonly_book_and_normalizes_negative_entries(tmp_path):
    from app.services.mumaren_finance_center.kingdee_books import plan_kingdee_books_import

    plan = plan_kingdee_books_import(_canonical_snapshot(tmp_path) / "manifest.json")

    assert plan.book_count == 1
    assert plan.voucher_count == 1
    assert plan.line_count == 4
    assert plan.balance_count == 1
    book = plan.books[0]
    assert len(book.accounts) == 3
    assert len(book.periods) == 1
    assert len(book.balance_snapshots) == 1
    assert book.balance_snapshots[0].account_source_key == "3"
    assert book.balance_snapshots[0].account_code == "1122"
    assert book.balance_snapshots[0].opening_amount == "80.00"
    assert book.balance_snapshots[0].closing_amount == "160.00"
    assert book.balance_snapshots[0].source_key == "FAccountID=3|FYear=2026|FPeriod=1|FDetailID=0|FCurrencyID=0"
    assert book.periods[0].period_code == "2026-01"
    assert book.is_readonly is True
    assert book.source_database == "AIS_TEST"
    assert book.vouchers[0].status == "posted"
    assert book.vouchers[0].summary == "期初"
    assert book.vouchers[0].normalized_negative_line_count == 2
    assert book.vouchers[0].is_normalized is True
    assert book.vouchers[0].lines[2].source_payload["FAmount"] == -20
    assert book.vouchers[0].lines[2].source_payload["normalization_rule"] == "flip_direction_and_abs_amount"
    assert [(line.debit_amount, line.credit_amount) for line in book.vouchers[0].lines] == [("120.00", "0.00"), ("0.00", "120.00"), ("0.00", "20.00"), ("20.00", "0.00")]


def test_canonical_plan_keeps_distinct_balance_evidence_for_same_account_period(tmp_path):
    from app.services.mumaren_finance_center.kingdee_books import plan_kingdee_books_import

    root = _canonical_snapshot(tmp_path)
    _replace_source_rows(root, "balances.jsonl", [
        {"FAccountID": 3, "FYear": 2026, "FPeriod": 1, "FDetailID": 0, "FCurrencyID": 0, "FBeginBalance": 80, "FDebit": 100, "FCredit": 20, "FEndBalance": 160},
        {"FAccountID": 3, "FYear": 2026, "FPeriod": 1, "FDetailID": 9, "FCurrencyID": 1, "FBeginBalance": 8, "FDebit": 10, "FCredit": 2, "FEndBalance": 16},
    ])

    snapshots = plan_kingdee_books_import(root / "manifest.json").books[0].balance_snapshots

    assert len(snapshots) == 2
    assert len({snapshot.source_key for snapshot in snapshots}) == 2
    assert {snapshot.source_key for snapshot in snapshots} == {
        "FAccountID=3|FYear=2026|FPeriod=1|FDetailID=0|FCurrencyID=0",
        "FAccountID=3|FYear=2026|FPeriod=1|FDetailID=9|FCurrencyID=1",
    }


def test_canonical_plan_rejects_balance_without_its_full_source_identity(tmp_path):
    from app.services.mumaren_finance_center.kingdee_books import KingdeeBooksImportError, plan_kingdee_books_import

    root = _canonical_snapshot(tmp_path)
    _replace_source_rows(root, "balances.jsonl", [
        {"FAccountID": 3, "FYear": 2026, "FPeriod": 1, "FDetailID": 0, "FBeginBalance": 80, "FDebit": 100, "FCredit": 20, "FEndBalance": 160},
    ])

    with pytest.raises(KingdeeBooksImportError, match="来源主键字段缺失"):
        plan_kingdee_books_import(root / "manifest.json")


def test_canonical_plan_rejects_changed_source_file(tmp_path):
    from app.services.mumaren_finance_center.kingdee_books import KingdeeBooksImportError, plan_kingdee_books_import

    root = _canonical_snapshot(tmp_path)
    (root / "AIS_TEST" / "accounts.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(KingdeeBooksImportError, match="校验和"):
        plan_kingdee_books_import(root / "manifest.json")


def test_canonical_plan_uses_fvoucherid_as_key_when_fnumber_repeats(tmp_path):
    from app.services.mumaren_finance_center.kingdee_books import plan_kingdee_books_import

    root = _canonical_snapshot(tmp_path)
    headers = [json.loads(line) for line in (root / "AIS_TEST" / "vouchers.jsonl").read_text(encoding="utf-8").splitlines()]
    entries = [json.loads(line) for line in (root / "AIS_TEST" / "voucher_entries.jsonl").read_text(encoding="utf-8").splitlines()]
    headers.append({"FVoucherID": 2, "FNumber": 1, "FDate": "2026-02-01T00:00:00", "FGroupID": 7, "FExplanation": "重复号码", "FEntryCount": 2, "FDebitTotal": 50, "FCreditTotal": 50})
    entries.extend([
        {"FVoucherID": 2, "FEntryID": 0, "FAccountID": 1, "FDC": 1, "FAmount": 50},
        {"FVoucherID": 2, "FEntryID": 1, "FAccountID": 2, "FDC": 0, "FAmount": 50},
    ])
    _replace_source_rows(root, "vouchers.jsonl", headers)
    _replace_source_rows(root, "voucher_entries.jsonl", entries)

    vouchers = plan_kingdee_books_import(root / "manifest.json").books[0].vouchers

    assert [voucher.source_key for voucher in vouchers] == ["1", "2"]
    assert len({voucher.voucher_no for voucher in vouchers}) == 2
    assert vouchers[1].source_payload["source_header"] == headers[1]
    assert vouchers[1].source_payload["source_header"]["FGroupID"] == 7
    assert vouchers[1].source_payload["source_header"]["FExplanation"] == "重复号码"


def test_canonical_plan_rejects_header_entry_count_or_source_totals_mismatch(tmp_path):
    from app.services.mumaren_finance_center.kingdee_books import KingdeeBooksImportError, plan_kingdee_books_import

    root = _canonical_snapshot(tmp_path)
    header = json.loads((root / "AIS_TEST" / "vouchers.jsonl").read_text(encoding="utf-8").splitlines()[0])
    header["FEntryCount"] = 3
    _replace_source_rows(root, "vouchers.jsonl", [header])

    with pytest.raises(KingdeeBooksImportError, match="分录数量"):
        plan_kingdee_books_import(root / "manifest.json")

    header["FEntryCount"] = 4
    header["FDebitTotal"] = 101
    _replace_source_rows(root, "vouchers.jsonl", [header])
    with pytest.raises(KingdeeBooksImportError, match="借方合计"):
        plan_kingdee_books_import(root / "manifest.json")


@pytest.mark.asyncio
async def test_first_execute_import_marks_the_new_batch_imported_without_reloading_it(tmp_path):
    """Exercise the real first-import control flow with a stateful session, not canned query results."""
    from app.services.mumaren_finance_center.kingdee_books import import_kingdee_books

    class ScalarRows:
        def __init__(self, rows: list[Any]):
            self.rows = rows

        def scalar_one_or_none(self):
            assert len(self.rows) <= 1
            return self.rows[0] if self.rows else None

        def scalars(self):
            return self

        def all(self):
            return list(self.rows)

    class StatefulSession:
        def __init__(self):
            self.objects: list[Any] = []
            self._next_id = 1

        async def execute(self, statement):
            descriptions = getattr(statement, "column_descriptions", None)
            if not descriptions:  # transaction-local PostgreSQL setting
                return ScalarRows([])
            entity = descriptions[0]["entity"]
            return ScalarRows([item for item in self.objects if isinstance(item, entity)])

        def add(self, value):
            self.objects.append(value)

        async def flush(self):
            for value in self.objects:
                if getattr(value, "id", None) is None:
                    value.id = self._next_id
                    self._next_id += 1

    db = StatefulSession()
    result = await import_kingdee_books(db, _canonical_snapshot(tmp_path) / "manifest.json", execute=True)

    batches = [item for item in db.objects if item.__class__.__name__ == "FinanceCenterMumarenKingdeeImportBatch"]
    assert result.status == "imported"
    assert len(batches) == 1
    assert batches[0].validation_status == "imported"
    assert batches[0].imported_at is not None
    historical_rows = [item for item in db.objects if hasattr(item, "source_system")]
    assert historical_rows
    assert {item.source_system for item in historical_rows} == {"kingdee_history"}


def test_finance_center_has_a_book_scoped_readonly_balance_snapshot_model():
    from app.models.mumaren_finance_center import FinanceCenterMumarenBalanceSnapshot

    table = FinanceCenterMumarenBalanceSnapshot.__table__
    assert table.schema == "finance_center_mumaren"
    assert {"book_id", "account_id", "period_code", "source_system", "source_database", "is_readonly"} <= set(table.columns.keys())


def test_current_book_models_expose_kingdee_lineage_and_readonly_metadata():
    from app.models.mumaren_finance_center import FinanceCenterMumarenBook, FinanceCenterMumarenVoucher

    assert {"source_system", "source_database", "source_company_name", "source_key", "source_checksum", "import_batch_key", "is_readonly"} <= set(FinanceCenterMumarenBook.__table__.columns.keys())
    assert {"source_system", "source_database", "source_key", "source_checksum", "import_batch_key", "is_readonly", "is_normalized"} <= set(FinanceCenterMumarenVoucher.__table__.columns.keys())


def test_readonly_current_book_voucher_cannot_enter_review_or_post_workflow():
    from app.models.mumaren_finance_center import FinanceCenterMumarenVoucher
    from app.services.mumaren_finance_center.workflow import HistoricalRecordReadonlyError, post_voucher, review_voucher

    voucher = FinanceCenterMumarenVoucher(status="draft", is_readonly=True)
    with pytest.raises(HistoricalRecordReadonlyError, match="只读"):
        review_voucher(voucher, operator_id=1)
    voucher.status = "reviewed"
    with pytest.raises(HistoricalRecordReadonlyError, match="只读"):
        post_voucher(voucher, operator_id=1)
