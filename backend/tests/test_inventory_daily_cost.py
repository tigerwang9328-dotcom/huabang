import asyncio
from decimal import Decimal

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine


async def _load_inventory_cost_totals():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(
                """
                WITH expected AS (
                    SELECT SUM(b.qty * COALESCE(
                        NULLIF(sk.cost_price, 0),
                        NULLIF(sk.market_price, 0),
                        NULLIF(p.cost_price, 0)
                    )) AS amount
                    FROM dwd.dwd_inventory_balance b
                    LEFT JOIN dim.dim_sku sk
                      ON sk.product_code = b.product_code
                     AND TRIM(LEADING '-' FROM COALESCE(sk.color_code, '')) =
                         TRIM(LEADING '-' FROM COALESCE(b.color_code, ''))
                     AND COALESCE(sk.size_code, '') = COALESCE(b.size_code, '')
                    LEFT JOIN dim.dim_product p ON b.product_code = p.product_code
                ), actual AS (
                    SELECT SUM(total_cost_amount) AS amount
                    FROM dws.dws_inventory_daily
                    WHERE stat_date = CURRENT_DATE
                )
                SELECT expected.amount AS expected_amount,
                       actual.amount AS actual_amount
                FROM expected CROSS JOIN actual
                """
            )
        )
        row = result.mappings().one()
    await engine.dispose()
    return row


def test_current_inventory_daily_rebuilds_sku_key_before_product_cost_fallback():
    totals = asyncio.run(_load_inventory_cost_totals())

    assert totals["expected_amount"] is not None
    assert totals["expected_amount"] > Decimal("0")
    assert totals["actual_amount"] == totals["expected_amount"]
