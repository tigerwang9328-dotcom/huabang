from pathlib import Path
import runpy


BACKEND_ROOT = Path(__file__).resolve().parents[1]
CONSUMERS = [
    "app/api/v1/mobile.py",
    "app/api/v1/product.py",
    "app/services/ai_diagnosis_service.py",
    "app/services/business_overview_service.py",
    "app/services/etl/dwd_to_dws.py",
    "app/services/etl/dws_to_dm.py",
    "app/services/inventory_analysis_service.py",
    "app/services/product_analysis_service.py",
    "app/services/report_service.py",
    "app/services/rule_engine.py",
    "app/services/size_wall_service.py",
]


def test_user_facing_inventory_consumers_use_apparel_views():
    violations = []
    for relative_path in CONSUMERS:
        content = (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")
        if "dwd.dwd_inventory_balance" in content or "dwd.dwd_inventory_snapshot" in content:
            violations.append(relative_path)

    assert violations == []


def test_apparel_view_migration_includes_supported_outerwear_categories():
    migration_path = (
        BACKEND_ROOT / "alembic/versions/e5f6a7b8c9d0_expand_apparel_inventory_categories.py"
    )
    migration = runpy.run_path(str(migration_path))
    expected = {"套装", "裙子", "夹克", "衬衫", "长T", "外套", "毛衫"}

    assert expected <= set(migration["EXPANDED_CATEGORIES"])
