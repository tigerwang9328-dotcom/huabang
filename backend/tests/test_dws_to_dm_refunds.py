from datetime import date

import pytest

from app.services.etl.dws_to_dm import DwsToDm


class _FetchResult:
    def __init__(self, *, one=None, rows=None, scalar=None):
        self._one = one
        self._rows = rows or []
        self._scalar = scalar

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _CaptureDb:
    def __init__(self, company_row=None):
        self.calls = []
        self._results = [
            _FetchResult(one=company_row or (
                1000,
                800,
                200,
                0.2,
                54,
                946,
                10,
                20,
                100,
                2,
                0.9,
                300,
                0.3,
                700,
                True,
            )),
            _FetchResult(rows=[("285101", 300), ("285204", 200), ("285702", 100)]),
            _FetchResult(scalar=3),
            _FetchResult(scalar=5000),
            _FetchResult(scalar=100),
            _FetchResult(one=(2000, 500, 9000)),
            _FetchResult(),
        ]
        self.committed = False
        self.rolled_back = False

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        return self._results.pop(0)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class _EtlLog:
    def start_task(self, *_args, **_kwargs):
        return 1

    def finish_task(self, *_args, **_kwargs):
        return None

    def fail_task(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_boss_daily_report_writes_return_fields_without_snapshot_meta():
    db = _CaptureDb()

    rows = await DwsToDm()._boss_daily_report("2026-07-06", db, _EtlLog())

    assert rows == 1
    assert db.committed is True
    insert_sql, insert_params = db.calls[-1]
    assert "return_amount" in insert_sql
    assert "return_rate" in insert_sql
    assert "source_freshness" not in insert_sql
    assert "metric_status" not in insert_sql
    conflict_update = insert_sql.split("DO UPDATE SET", 1)[1]
    assert "generated_at" not in conflict_update
    assert insert_params["return_amount"] == 54.0
    assert insert_params["return_rate"] == 0.054


@pytest.mark.asyncio
async def test_boss_daily_report_keeps_return_only_rate_undefined():
    db = _CaptureDb(company_row=(
        0, 0, 0, None, 54, -54, 0, 0, 0, 0, None, 0, None, 0, True,
    ))

    await DwsToDm()._boss_daily_report("2026-07-06", db, _EtlLog())

    _, insert_params = db.calls[-1]
    assert insert_params["return_amount"] == 54.0
    assert insert_params["return_rate"] is None
