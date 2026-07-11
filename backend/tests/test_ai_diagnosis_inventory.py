import asyncio

from app.core.database import AsyncSessionLocal, engine
from app.services.ai_diagnosis_service import AIDiagnosisService


async def _run_inventory():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        result = await AIDiagnosisService(db).inventory()
    await engine.dispose()
    return result


def test_default_inventory_diagnosis_uses_latest_costed_snapshot():
    result = asyncio.run(_run_inventory())
    summary = result["summary"]

    assert summary["inventory_stat_date"]
    assert summary["inventory_amount"] > 0
