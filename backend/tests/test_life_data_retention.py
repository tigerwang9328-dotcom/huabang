import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.life_data import LifeDataCapture


_BACKEND_DIR = Path(__file__).resolve().parents[1]
_MIGRATION = (
    _BACKEND_DIR
    / "alembic"
    / "versions"
    / "f1b2c3d4e5f6_life_data_collector.py"
)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _RecordingScheduler:
    def __init__(self):
        self.jobs = []

    def add_job(self, func, trigger, **kwargs):
        self.jobs.append({"func": func, "trigger": trigger, **kwargs})

    def get_jobs(self):
        return self.jobs


def test_capture_created_at_has_model_and_migration_index():
    indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in LifeDataCapture.__table__.indexes
    }

    assert indexes["ix_app_life_data_capture_created_at"] == ("created_at",)

    migration_source = _MIGRATION.read_text(encoding="utf-8")
    assert "CREATE INDEX IF NOT EXISTS ix_app_life_data_capture_created_at" in migration_source
    assert "ON app.life_data_capture (created_at)" in migration_source


@pytest.mark.asyncio
async def test_cleanup_deletes_captures_older_than_90_days_and_commits(monkeypatch):
    from app.jobs import life_data_jobs

    now = datetime(2026, 7, 12, 3, 20, tzinfo=timezone.utc)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(rowcount=7)),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    monkeypatch.setattr(life_data_jobs, "_utc_now", lambda: now)
    monkeypatch.setattr(
        life_data_jobs,
        "AsyncSessionLocal",
        lambda: _SessionContext(session),
    )

    deleted = await life_data_jobs.cleanup_life_data_captures()

    statement = session.execute.await_args.args[0]
    compiled = statement.compile()
    assert statement.table.fullname == LifeDataCapture.__table__.fullname
    assert "DELETE FROM app.life_data_capture" in str(compiled)
    assert "created_at < :" in str(compiled)
    assert list(compiled.params.values()) == [now - timedelta(days=90)]
    assert deleted == 7
    session.commit.assert_awaited_once_with()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_rolls_back_logs_and_reraises_database_errors(
    monkeypatch,
    caplog,
):
    from app.jobs import life_data_jobs

    session = SimpleNamespace(
        execute=AsyncMock(side_effect=RuntimeError("database unavailable")),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    monkeypatch.setattr(
        life_data_jobs,
        "AsyncSessionLocal",
        lambda: _SessionContext(session),
    )

    with caplog.at_level(logging.ERROR, logger=life_data_jobs.__name__):
        with pytest.raises(RuntimeError, match="database unavailable"):
            await life_data_jobs.cleanup_life_data_captures()

    session.rollback.assert_awaited_once_with()
    session.commit.assert_not_awaited()
    assert "LifeData原始采集数据清理失败" in caplog.text


def test_scheduler_registers_daily_life_data_cleanup(monkeypatch):
    from app.jobs import life_data_jobs
    from app.jobs import scheduler as scheduler_module

    recording_scheduler = _RecordingScheduler()
    monkeypatch.setattr(scheduler_module, "scheduler", recording_scheduler)

    scheduler_module.setup_jobs()

    job = next(
        job
        for job in recording_scheduler.jobs
        if job["id"] == "life_data_capture_cleanup"
    )
    fields = {field.name: str(field) for field in job["trigger"].fields}
    assert job["func"] is life_data_jobs.cleanup_life_data_captures
    assert fields["hour"] == "3"
    assert fields["minute"] == "20"
    assert str(job["trigger"].timezone) == "Asia/Shanghai"
    assert job["replace_existing"] is True
    assert job["coalesce"] is True
    assert job["max_instances"] == 1
