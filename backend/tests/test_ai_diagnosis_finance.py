import asyncio

from app.core.database import AsyncSessionLocal, engine
from app.services.ai_diagnosis_service import AIDiagnosisService


async def _run_finance(stat_date: str):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        result = await AIDiagnosisService(db).finance(stat_date=stat_date)
    await engine.dispose()
    return result


def test_finance_uses_completed_dingtalk_expense_amount():
    result = asyncio.run(_run_finance("2026-06-15"))

    assert result["summary"]["total_expense"] == 900.0


def test_finance_keeps_gross_profit_but_warns_for_estimated_sku_cost():
    result = asyncio.run(_run_finance("2026-07-09"))

    assert result["summary"]["cost_of_goods"] > 0
    assert result["summary"]["gross_profit"] > 0
    assert any("成本" in warning for warning in result["data_quality"]["warnings"])
