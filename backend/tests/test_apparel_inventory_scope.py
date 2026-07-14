import asyncio
from decimal import Decimal

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine


INVENTORY_CODES = [
    "134681", "185805", "185808", "285101", "285102",
    "285204", "285702", "GZ001", "GZ002", "GYNG",
]


async def _scope_stats():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        stats = (
            await db.execute(
                text(
                    """
                    SELECT
                      (SELECT COALESCE(SUM(qty), 0)
                       FROM dwd.dwd_inventory_balance
                       WHERE UPPER(warehouse_code) = ANY(:codes) AND qty > 0) AS raw_qty,
                      (SELECT COALESCE(SUM(qty), 0)
                       FROM dwd.v_apparel_inventory_balance
                       WHERE UPPER(warehouse_code) = ANY(:codes) AND qty > 0) AS apparel_qty,
                      (SELECT COUNT(*)
                       FROM dwd.v_apparel_inventory_balance i
                       LEFT JOIN dim.dim_product p ON p.product_code = i.product_code
                       WHERE COALESCE(NULLIF(p.category_name, ''), NULLIF(p.top_category_name, ''), '未分类')
                             IN ('袜子','鞋子','皮带','围巾','包类','赠品','内裤','保暖内衣')) AS excluded_rows,
                      (SELECT COUNT(*)
                       FROM dwd.v_apparel_inventory_balance i
                       LEFT JOIN dim.dim_product p ON p.product_code = i.product_code
                       WHERE COALESCE(NULLIF(p.category_name, ''), NULLIF(p.top_category_name, ''), '未分类')
                             IN ('未定义','未分类')
                         AND COALESCE(p.product_name, i.goods_name, '') IN ('T恤','休闲裤')) AS fallback_rows,
                      to_regclass('dwd.v_apparel_inventory_snapshot') IS NOT NULL AS snapshot_view_exists
                    """
                ),
                {"codes": INVENTORY_CODES},
            )
        ).mappings().one()
    await engine.dispose()
    return stats


def test_apparel_inventory_views_apply_the_confirmed_scope():
    stats = asyncio.run(_scope_stats())

    assert stats["raw_qty"] > 0
    assert stats["apparel_qty"] > 0
    assert stats["apparel_qty"] < stats["raw_qty"]
    assert stats["raw_qty"] - stats["apparel_qty"] > Decimal("1000")
    assert Decimal("0.6") < stats["apparel_qty"] / stats["raw_qty"] < Decimal("0.9")
    assert stats["excluded_rows"] == 0
    assert stats["fallback_rows"] > 0
    assert stats["snapshot_view_exists"] is True
