import asyncio

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.services.ai_diagnosis_service import AIDiagnosisService


async def _run_inventory():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        result = await AIDiagnosisService(db).inventory()
    await engine.dispose()
    return result


async def _raw_negative_sku_count():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            select count(distinct (
                warehouse_code,
                coalesce(
                    nullif(sku_code,''),
                    concat(product_code, trim(leading '-' from coalesce(color_code,'')), coalesce(size_code,''))
                )
            ))
            from dwd.v_apparel_inventory_balance
            where qty < 0
        """))
        count = int(result.scalar() or 0)
    await engine.dispose()
    return count


def test_inventory_diagnosis_uses_current_balance_and_complete_business_metrics():
    result = asyncio.run(_run_inventory())
    summary = result["summary"]

    assert summary["health_score"] > 0
    assert summary["net_sales"] > 0
    assert summary["order_count"] > 0
    assert summary["gross_margin"] > 0
    assert summary["total_inventory_qty"] > 0
    assert summary["inventory_amount"] > 0
    assert summary["age_90_amount"] > 0
    # The production SKU population changes with each inventory sync.  The
    # contract is that the diagnosis reads a non-empty current balance, not a
    # fixed historical row-count threshold.
    assert summary["sku_count"] > 0
    assert summary["negative_sku_count"] == asyncio.run(_raw_negative_sku_count())
    assert "dwd_inventory_balance" in result["data_quality"]["source_tables"]
    payload = str(result["diagnoses"])
    assert "S003" not in payload
    assert "P004-M" not in payload
