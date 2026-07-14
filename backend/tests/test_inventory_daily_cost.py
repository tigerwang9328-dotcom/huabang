import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine


async def _load_inventory_cost_totals():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(
                """
                WITH target AS (
                    SELECT MAX(snapshot_date) AS stat_date
                    FROM dwd.v_apparel_inventory_snapshot
                ), expected AS (
                    SELECT SUM(b.cost_amount) AS amount
                    FROM dwd.v_apparel_inventory_snapshot b
                    CROSS JOIN target
                    WHERE b.snapshot_date = target.stat_date
                ), actual AS (
                    SELECT SUM(total_cost_amount) AS amount
                    FROM dws.dws_inventory_daily
                    WHERE stat_date = (SELECT stat_date FROM target)
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


def test_latest_complete_inventory_daily_matches_its_source_snapshot():
    totals = asyncio.run(_load_inventory_cost_totals())

    if totals["expected_amount"] is None:
        pytest.skip("当前没有可用于同日对账的完整库存快照")
    assert totals["expected_amount"] > Decimal("0")
    assert totals["actual_amount"] == totals["expected_amount"]
