from datetime import date
from pathlib import Path

from app.services.command_center_service import inventory_warning_source_id


BACKEND = Path(__file__).resolve().parents[1]


def test_inventory_warning_identity_is_stable_and_date_scoped():
    first = inventory_warning_source_id(date(2026, 7, 14), "GZ001", "P1", "S1", "size_break")
    assert first == inventory_warning_source_id(date(2026, 7, 14), "GZ001", "P1", "S1", "size_break")
    assert first != inventory_warning_source_id(date(2026, 7, 15), "GZ001", "P1", "S1", "size_break")


def test_warning_rebuild_covers_phase_one_inventory_rules_with_evidence():
    source = (BACKEND / "app" / "services" / "command_center_service.py").read_text(encoding="utf-8")
    for warning_type in (
        "age_90", "age_180", "seasonal", "size_break", "low_motion_high_stock",
        "low_sellable_days", "stockout", "store_imbalance", "transfer", "clearance_return",
    ):
        assert f"'{warning_type}'" in source

    assert "app.app_business_rule_config" in source
    assert "thresholds" in source
    assert "evidence" in source
    assert "source_name" in source


def test_warning_evidence_columns_are_migrated_and_returned_by_api():
    migration = BACKEND / "alembic" / "versions" / "0a9b0c1d2e3f_inventory_warning_evidence.py"
    model = (BACKEND / "app" / "models" / "dm.py").read_text(encoding="utf-8")
    api = (BACKEND / "app" / "api" / "v1" / "inventory.py").read_text(encoding="utf-8")

    assert migration.exists()
    content = migration.read_text(encoding="utf-8")
    for field in ("rule_id", "thresholds", "evidence", "source_name"):
        assert field in content
        assert field in model
        assert field in api


def test_warning_rebuild_preserves_other_historical_dates():
    source = (BACKEND / "app" / "services" / "command_center_service.py").read_text(encoding="utf-8")
    assert "DELETE FROM dm.dm_inventory_warning WHERE warning_date=:snapshot_date" in source
    assert "DELETE FROM dm.dm_inventory_warning" not in source.replace(
        "DELETE FROM dm.dm_inventory_warning WHERE warning_date=:snapshot_date", ""
    )


def test_inventory_summary_discloses_standard_price_coverage_without_pricing_missing_skus():
    source = (BACKEND / "app" / "services" / "inventory_analysis_service.py").read_text(encoding="utf-8")
    assert '"standard_purchase_price_coverage_rate"' in source
    assert '"standard_purchase_price_ready_sku_count"' in source
    assert '"inventory_sku_count"' in source
    assert "priced.unit_price IS NULL" in source
    assert "v_baison_sku_standard_purchase_price" in source
    assert "p.cost_price" not in source
