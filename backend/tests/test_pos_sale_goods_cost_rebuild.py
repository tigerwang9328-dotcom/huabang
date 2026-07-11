import asyncio
from decimal import Decimal

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine


async def _load_latest_cost_totals():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(
                """
                WITH latest AS (
                    SELECT MAX(biz_date) AS stat_date
                    FROM dwd.dwd_pos_sale_goods
                ), expected AS (
                    SELECT
                        SUM(s.sales_qty * COALESCE(
                            NULLIF(sk.cost_price, 0),
                            NULLIF(sk.market_price, 0),
                            NULLIF(p.cost_price, 0)
                        )) AS cost_amount,
                        SUM(s.sales_amount) - SUM(s.sales_qty * COALESCE(
                            NULLIF(sk.cost_price, 0),
                            NULLIF(sk.market_price, 0),
                            NULLIF(p.cost_price, 0)
                        )) AS gross_profit
                    FROM dwd.dwd_pos_sale_goods s
                    JOIN latest l ON l.stat_date = s.biz_date
                    LEFT JOIN dim.dim_sku sk
                      ON REPLACE(s.sku_code, '|', '') = sk.sku_code
                    LEFT JOIN dim.dim_product p
                      ON s.product_code = p.product_code
                ), actual AS (
                    SELECT
                        SUM(d.cost_amount) AS cost_amount,
                        SUM(d.gross_profit) AS gross_profit
                    FROM dws.dws_product_daily d
                    JOIN latest l ON l.stat_date = d.stat_date
                )
                SELECT
                    expected.cost_amount AS expected_cost,
                    expected.gross_profit AS expected_gross,
                    actual.cost_amount AS actual_cost,
                    actual.gross_profit AS actual_gross
                FROM expected CROSS JOIN actual
                """
            )
        )
        row = result.mappings().one()
    await engine.dispose()
    return row


def test_latest_product_daily_uses_sku_cost_with_market_price_fallback():
    totals = asyncio.run(_load_latest_cost_totals())

    assert totals["expected_cost"] is not None
    assert totals["expected_cost"] > Decimal("0")
    assert totals["actual_cost"] == totals["expected_cost"]
    assert totals["actual_gross"] == totals["expected_gross"]
