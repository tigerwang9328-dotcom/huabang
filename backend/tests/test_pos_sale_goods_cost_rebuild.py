import asyncio
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.integrations.baison.services.pos_sale_goods_service import PosSaleGoodsService


async def _load_latest_cost_totals():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        latest_date = (await db.execute(
            text("SELECT MAX(biz_date) FROM dwd.dwd_pos_sale_goods")
        )).scalar_one()
    await engine.dispose()
    await PosSaleGoodsService().rebuild_dws_summary(
        latest_date.isoformat(), latest_date.isoformat()
    )
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(
                """
                WITH latest AS (
                    SELECT MAX(biz_date) AS stat_date
                    FROM dwd.dwd_pos_sale_goods
                ), expected AS (
                    SELECT
                        SUM(CASE
                            WHEN p.supplier_code = 'GY1229'
                             AND sp.standard_purchase_price = 1
                            THEN s.sales_amount * 0.60
                            WHEN sp.standard_purchase_price > 0
                            THEN s.sales_qty * sp.standard_purchase_price
                            ELSE NULL
                        END) AS cost_amount,
                        SUM(s.sales_amount) - SUM(CASE
                            WHEN p.supplier_code = 'GY1229'
                             AND sp.standard_purchase_price = 1
                            THEN s.sales_amount * 0.60
                            WHEN sp.standard_purchase_price > 0
                            THEN s.sales_qty * sp.standard_purchase_price
                            ELSE NULL
                        END) AS gross_profit
                    FROM dwd.dwd_pos_sale_goods s
                    JOIN latest l ON l.stat_date = s.biz_date
                    LEFT JOIN dim.dim_product p
                      ON s.product_code = p.product_code
                    LEFT JOIN dim.v_baison_sku_standard_purchase_price sp
                      ON sp.product_code = s.product_code
                     AND sp.color_code = COALESCE(BTRIM(split_part(s.sku_code, '|', 2)), '')
                     AND sp.size_code = COALESCE(BTRIM(split_part(s.sku_code, '|', 3)), '')
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


def test_latest_product_daily_uses_standard_purchase_price():
    totals = asyncio.run(_load_latest_cost_totals())

    assert totals["expected_cost"] is not None
    assert totals["expected_cost"] > Decimal("0")
    assert totals["actual_cost"] == totals["expected_cost"]
    assert totals["actual_gross"] == totals["expected_gross"]


def test_production_rebuild_script_uses_the_same_standard_purchase_price_policy():
    source = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "rebuild_pos_sale_goods_from_tickets.sh"
    ).read_text(encoding="utf-8")

    assert "v_baison_sku_standard_purchase_price" in source
    assert "baison_standard_purchase_price" in source
    assert "GY1229" in source
    assert "sales_amount * 0.60" in source
    assert "NULLIF(sk.cost_price" not in source
    assert "NULLIF(sk.market_price" not in source
    assert "NULLIF(p.cost_price" not in source
    assert "('GZ001')" not in source
    assert "('GZ002')" not in source
    assert "('GYNG')" not in source
