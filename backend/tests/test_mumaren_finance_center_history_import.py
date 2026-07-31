import hashlib
import json
import os
from pathlib import Path

import pytest


os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("DB_PASSWORD", "test-only-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")


def _manifest(path: Path, *, batch_key: str = "kingdee-2024-q1") -> Path:
    payload = {
        "source_system": "kingdee",
        "source_batch_key": batch_key,
        "vouchers": [
            {
                "source_key": "K3:acct-a:voucher:1001",
                "voucher_no": "记-0001",
                "voucher_date": "2024-01-31",
                "summary": "期初余额",
                "lines": [
                    {"source_key": "K3:acct-a:entry:1", "line_no": 1, "account_code": "1001", "account_name": "库存现金", "debit_amount": "100.00", "credit_amount": "0.00"},
                    {"source_key": "K3:acct-a:entry:2", "line_no": 2, "account_code": "3001", "account_name": "实收资本", "debit_amount": "0.00", "credit_amount": "100.00"},
                ],
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_plan_requires_explicit_kingdee_batch_and_produces_readonly_history_records(tmp_path):
    from app.services.mumaren_finance_center.history import plan_history_import

    manifest_path = _manifest(tmp_path / "kingdee-history.json")
    plan = plan_history_import(manifest_path)

    assert plan.source_system == "kingdee"
    assert plan.source_batch_key == "kingdee-2024-q1"
    assert plan.source_checksum == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert plan.record_count == 1
    assert plan.vouchers[0].record_type == "historical"
    assert plan.vouchers[0].is_readonly is True
    assert plan.vouchers[0].lines[0].source_system == "kingdee"


def test_plan_rejects_non_kingdee_and_unbalanced_history_voucher(tmp_path):
    from app.services.mumaren_finance_center.history import HistoryImportError, plan_history_import

    path = _manifest(tmp_path / "invalid.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["source_system"] = "other"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(HistoryImportError, match="kingdee"):
        plan_history_import(path)

    payload["source_system"] = "kingdee"
    payload["vouchers"][0]["lines"][1]["credit_amount"] = "99.99"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(HistoryImportError, match="借贷不平衡"):
        plan_history_import(path)


@pytest.mark.asyncio
async def test_execute_import_only_writes_new_history_tables_and_is_idempotent(tmp_path):
    from app.models.mumaren_finance_center import (
        FinanceCenterMumarenHistoryImportBatch,
        FinanceCenterMumarenHistoryVoucher,
        FinanceCenterMumarenHistoryVoucherLine,
    )
    from app.services.mumaren_finance_center.history import import_history_manifest

    class Result:
        def scalar_one_or_none(self):
            return None

    class Db:
        def __init__(self):
            self.added = []
            self.executed = []
            self.flushes = 0

        async def execute(self, statement):
            self.executed.append(str(statement))
            return Result()

        def add(self, item):
            self.added.append(item)

        async def flush(self):
            self.flushes += 1
            for index, item in enumerate(self.added, start=1):
                if getattr(item, "id", None) is None:
                    item.id = index

    db = Db()
    result = await import_history_manifest(db, _manifest(tmp_path / "history.json"), execute=True, imported_by=7)

    assert result.mode == "executed"
    assert result.inserted_vouchers == 1
    assert sum(isinstance(item, FinanceCenterMumarenHistoryImportBatch) for item in db.added) == 1
    vouchers = [item for item in db.added if isinstance(item, FinanceCenterMumarenHistoryVoucher)]
    assert len(vouchers) == 1
    assert vouchers[0].source_system == "kingdee"
    assert vouchers[0].record_type == "historical"
    assert vouchers[0].is_readonly is True
    assert sum(isinstance(item, FinanceCenterMumarenHistoryVoucherLine) for item in db.added) == 2
    assert all("finance_center_mumaren_history" in query for query in db.executed)


@pytest.mark.asyncio
async def test_execute_rejects_an_existing_batch_without_a_matching_checksum(tmp_path):
    from app.models.mumaren_finance_center import FinanceCenterMumarenHistoryImportBatch
    from app.services.mumaren_finance_center.history import HistoryImportError, import_history_manifest

    class Result:
        def scalar_one_or_none(self):
            return FinanceCenterMumarenHistoryImportBatch(
                id=9,
                source_system="kingdee",
                source_batch_key="kingdee-2024-q1",
                source_checksum=None,
            )

    class Db:
        async def execute(self, _statement):
            return Result()

        def add(self, _item):
            raise AssertionError("checksum mismatch must fail before writes")

    with pytest.raises(HistoryImportError, match="校验和不一致"):
        await import_history_manifest(Db(), _manifest(tmp_path / "history.json"), execute=True)
