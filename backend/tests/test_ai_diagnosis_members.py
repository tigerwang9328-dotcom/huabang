import asyncio
import logging

from app.core.database import AsyncSessionLocal, engine
from app.services.ai_diagnosis_service import AIDiagnosisService


async def _run_members():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        result = await AIDiagnosisService(db).members()
    await engine.dispose()
    return result


async def _run_actions():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        result = await AIDiagnosisService(db).action_tasks()
    await engine.dispose()
    return result


def test_members_query_does_not_fall_back_after_sql_error(caplog):
    with caplog.at_level(logging.ERROR, logger="app.services.ai_diagnosis_service"):
        result = asyncio.run(_run_members())

    assert result["summary"]["member_order_count"] > 0
    assert result["summary"]["visit_stat_date"]
    assert result["summary"]["visit_count"] > 0
    assert not [record for record in caplog.records if "query failed" in record.message]


def test_actions_use_latest_member_visit_snapshot():
    result = asyncio.run(_run_actions())

    assert not any("会员回访清单为空" in warning for warning in result["data_quality"]["warnings"])
