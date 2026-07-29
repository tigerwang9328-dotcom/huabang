from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pytest

from app.services.finance_v2.history_import_plan import HistoryPublicationError, plan_history_import
from app.services.finance_v2.history_import_service import FinanceV2HistoryImportService
from app.services.finance_v2.kingdee_history_loader import KingdeeHistoryRecord


@dataclass(frozen=True)
class _Record:
    source_pk: str
    source_hash: str


def test_history_import_plan_keeps_matching_sources_idempotent_and_stages_only_new_facts():
    plan = plan_history_import(
        [_Record("same", "same-hash"), _Record("new", "new-hash")],
        {"same": "same-hash"},
    )

    assert [record.source_pk for record in plan.new_records] == ["new"]
    assert plan.idempotent_source_pks == ("same",)
    assert plan.conflicts == ()


def test_history_import_plan_reports_changed_source_hash_without_planning_any_write():
    plan = plan_history_import(
        [_Record("changed", "new-hash")],
        {"changed": "old-hash"},
    )

    assert plan.new_records == ()
    assert plan.conflicts == (("changed", "old-hash", "new-hash"),)


class _Result:
    def scalars(self):
        return self

    def all(self):
        return []


class _StageDb:
    def __init__(self):
        self.added = []
        self.flush_count = 0

    async def scalar(self, *_args, **_kwargs):
        return None

    async def execute(self, *_args, **_kwargs):
        return _Result()

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flush_count += 1
        for value in self.added:
            if value.__class__.__name__ == "FinanceV2HistoryBatch" and value.id is None:
                value.id = 1


@pytest.mark.asyncio
async def test_history_stage_flushes_staging_rows_before_same_transaction_validation():
    record = KingdeeHistoryRecord(
        source_system="kingdee",
        source_database="AIS1",
        source_pk="AIS1:voucher:1",
        source_hash="a" * 64,
        voucher_no="1",
        voucher_group="记",
        voucher_date=date(2026, 6, 30),
        fiscal_year=2026,
        fiscal_period=6,
        source_status="posted",
        total_debit="1.00",
        total_credit="1.00",
        lines=(),
        raw_payload={"header": {}, "entries": [], "account_codes": {}},
    )
    db = _StageDb()

    result = await FinanceV2HistoryImportService(db).stage(
        batch_code="history-stage-flush",
        source_database="AIS1",
        records=[record],
    )

    assert result.status == "loaded"
    assert db.flush_count == 2


class _EmptyStagingDb:
    def __init__(self, status: str):
        self.batch = SimpleNamespace(id=1, status=status)

    async def get(self, *_args, **_kwargs):
        return self.batch

    async def execute(self, *_args, **_kwargs):
        return _Result()


@pytest.mark.asyncio
async def test_history_validation_rejects_an_empty_staging_batch():
    with pytest.raises(HistoryPublicationError, match="requires at least one staged voucher"):
        await FinanceV2HistoryImportService(_EmptyStagingDb("loaded")).validate(1)


@pytest.mark.asyncio
async def test_history_publication_rejects_an_empty_staging_batch():
    with pytest.raises(HistoryPublicationError, match="requires at least one staged voucher"):
        await FinanceV2HistoryImportService(_EmptyStagingDb("validated")).publish(1)
