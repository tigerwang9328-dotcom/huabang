import asyncio
from app.core.database import AsyncSessionLocal,engine
from app.services.ai_diagnosis_service import AIDiagnosisService

async def _run():
    await engine.dispose()
    async with AsyncSessionLocal() as db: result=await AIDiagnosisService(db).sales("2026-07-11")
    await engine.dispose();return result

def test_sales_diagnosis_includes_baison_monthly_target():
    result=asyncio.run(_run());summary=result["summary"]
    assert summary["monthly_target_amount"]>0
    assert summary["monthly_actual_amount"]>0
    assert summary["monthly_achievement_rate"]>0
    assert "dws_store_target_monthly" in result["data_quality"]["source_tables"]
