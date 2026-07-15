import asyncio
import inspect
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from app.api.v1.product import _product_metrics
from app.api.v1.mobile import mobile_inventory_styles
from app.core.database import AsyncSessionLocal, engine
from app.services.command_center_service import rebuild_inventory_age
from app.services.inventory_analysis_service import get_inventory_analysis_summary
from app.services.size_wall_service import SizeWallService


BACKEND_ROOT = Path(__file__).resolve().parents[1]


async def _load_summary_and_expected():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        summary = await get_inventory_analysis_summary(db)
        expected = (await db.execute(text("""
            WITH inv AS (
                SELECT product_code,
                       COALESCE(BTRIM(color_code::text), '') AS color_code,
                       COALESCE(BTRIM(size_code::text), '') AS size_code,
                       GREATEST(SUM(qty), 0) AS qty
                FROM dwd.v_apparel_inventory_balance
                WHERE UPPER(COALESCE(warehouse_code, '')::text) = ANY(:codes)
                GROUP BY product_code,
                         COALESCE(BTRIM(color_code::text), ''),
                         COALESCE(BTRIM(size_code::text), '')
            )
            SELECT
                COALESCE(SUM(i.qty * sp.standard_purchase_price)
                    FILTER (WHERE sp.standard_purchase_price IS NOT NULL), 0) AS amount,
                COALESCE(SUM(i.qty), 0) AS total_qty,
                COALESCE(SUM(i.qty)
                    FILTER (WHERE sp.standard_purchase_price IS NULL), 0) AS missing_qty,
                COUNT(*) FILTER (
                    WHERE i.qty > 0 AND sp.standard_purchase_price IS NULL
                ) AS missing_sku_count
            FROM inv i
            LEFT JOIN dim.v_baison_sku_standard_purchase_price sp
              ON sp.product_code = i.product_code
             AND sp.color_code = i.color_code
             AND sp.size_code = i.size_code
            WHERE i.qty > 0
        """), {
            "codes": ["134681", "185805", "185808", "285101", "285102",
                      "285204", "285702", "GZ001", "GZ002", "GYNG"],
        })).mappings().one()
    await engine.dispose()
    return summary["summary"], expected


def test_inventory_summary_matches_canonical_standard_purchase_price():
    summary, expected = asyncio.run(_load_summary_and_expected())

    assert Decimal(str(summary["inventory_amount"]["value"])) == expected["amount"]
    assert summary["missing_standard_purchase_price_qty"]["value"] == float(expected["missing_qty"])
    assert summary["missing_standard_purchase_price_sku_count"]["value"] == expected["missing_sku_count"]
    expected_rate = (
        (expected["total_qty"] - expected["missing_qty"]) / expected["total_qty"] * 100
        if expected["total_qty"] else Decimal("0")
    )
    assert summary["standard_purchase_price_coverage_rate"]["value"] == round(float(expected_rate), 1)


def test_user_facing_inventory_functions_use_canonical_view():
    sources = {
        "product": inspect.getsource(_product_metrics),
        "inventory": (BACKEND_ROOT / "app/services/inventory_analysis_service.py").read_text(),
        "command_center": inspect.getsource(rebuild_inventory_age),
        "size_wall": inspect.getsource(SizeWallService.build_snapshot),
        "inventory_etl": (BACKEND_ROOT / "app/services/etl/ods_to_dwd.py").read_text(),
        "mobile_inventory": inspect.getsource(mobile_inventory_styles),
        "inventory_sync": (
            BACKEND_ROOT.parent / "scripts/sync_baison_inventory_daily.sh"
        ).read_text(),
    }

    for name, source in sources.items():
        assert "v_baison_sku_standard_purchase_price" in source, name

    assert "COALESCE(NULLIF(s.cost_price" not in sources["product"]
    assert "s.cost_price AS sku_cost_price" not in sources["inventory"]
    assert "NULLIF(sk.cost_price" not in sources["command_center"]
    assert "nullif(s.cost_price" not in sources["size_wall"]
    assert "NULLIF(sk.cost_price" not in sources["inventory_sync"]
    assert "NULLIF(sk.market_price" not in sources["inventory_sync"]
    assert "NULLIF(p.cost_price" not in sources["inventory_sync"]
    assert "GREATEST(b.qty, 0)" in sources["inventory_sync"]
    assert "COALESCE(p.tag_price, p.market_price, 0)" not in sources["mobile_inventory"]


def test_legacy_ods_sales_and_returns_do_not_reintroduce_old_cost_fields():
    source = (BACKEND_ROOT / "app/services/etl/ods_to_dwd.py").read_text()

    assert "v_baison_sku_standard_purchase_price" in source
    assert "effective_sales_standard_cost_sql" in source
    assert "s.cost_price" not in source
    assert "s.cost_amount" not in source
    assert "r.cost_price" not in source
    assert "r.cost_amount" not in source
