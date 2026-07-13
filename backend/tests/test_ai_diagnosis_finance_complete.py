import asyncio

from app.core.database import AsyncSessionLocal, engine
from app.services.ai_diagnosis_service import AIDiagnosisService


async def _run_finance():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        result = await AIDiagnosisService(db).finance("2026-07-11")
    await engine.dispose()
    return result


def test_finance_diagnosis_exposes_order_count_and_health_score():
    result = asyncio.run(_run_finance())
    summary = result["summary"]

    assert summary["net_sales"] > 0
    assert summary["order_count"] == 31
    assert summary["health_score"] > 0
    assert summary["gross_margin"] > 0
    assert "dwd_pos_ticket" in result["data_quality"]["source_tables"]
