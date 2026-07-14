from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]


def test_command_center_migration_defines_required_snapshot_tables():
    migration = BACKEND / "alembic" / "versions" / "e6f7a8b9c0d1_boss_command_center.py"
    content = migration.read_text(encoding="utf-8")

    assert "current_balance" in content
    assert "dm_inventory_age_daily" in content
    assert "actual_pay_amount" in content
    assert "source_freshness" in content
    assert "app_business_rule_config" in content


def test_vip_negative_balance_amount_has_follow_up_migration_and_model_field():
    migration = BACKEND / "alembic" / "versions" / "0a8b9c0d1e2f_vip_negative_balance_amount.py"
    model = BACKEND / "app" / "models" / "dm.py"

    assert "vip_negative_balance_amount" in migration.read_text(encoding="utf-8")
    assert "vip_negative_balance_amount" in model.read_text(encoding="utf-8")


def test_public_apis_expose_command_center_drilldowns():
    inventory_api = (BACKEND / "app" / "api" / "v1" / "inventory.py").read_text(encoding="utf-8")
    member_api = (BACKEND / "app" / "api" / "v1" / "member.py").read_text(encoding="utf-8")

    assert '@router.get("/inventory/warnings")' in inventory_api
    assert '@router.get("/assets/overview")' in member_api
    assert '@router.get("/assets/list")' in member_api
    assert '@router.get("/assets/transactions")' in member_api


def test_dashboard_and_store_share_the_confirmed_payment_formula():
    payment_source = (BACKEND / "app" / "services" / "sales_metric_service.py").read_text(encoding="utf-8")
    command_source = (BACKEND / "app" / "services" / "command_center_service.py").read_text(encoding="utf-8")
    store_source = (BACKEND / "app" / "api" / "v1" / "store.py").read_text(encoding="utf-8")

    assert 'SALES_PAYMENT_CODES = ("000", "003", "004", "011", "666", "971")' in payment_source
    assert 'ACTUAL_RECEIPT_PAYMENT_CODES = ("000", "011", "666", "971")' in payment_source
    assert "PAY_DETAIL_SQL" in command_source
    assert "dwd_store_recharge_daily" in command_source
    assert "PAY_DETAIL_SQL" in store_source
    assert "pay.recharge_amount" not in store_source


def test_daily_command_center_rebuilds_dws_before_running_rules():
    payment_source = (BACKEND / "app" / "services" / "sales_metric_service.py").read_text(encoding="utf-8")
    command_source = (BACKEND / "app" / "services" / "command_center_service.py").read_text(encoding="utf-8")

    assert "rebuild_confirmed_sales_dws" in payment_source
    assert "UPDATE dws.dws_store_daily" in payment_source
    assert "UPDATE dws.dws_company_daily" in payment_source
    assert "cost_coverage_rate" in command_source
    assert command_source.index("await rebuild_confirmed_sales_dws") < command_source.index("engine = RuleEngine()")


def test_daily_command_wrapper_forwards_manual_rebuild_arguments():
    wrapper = (BACKEND.parent / "scripts" / "generate_boss_command_center_daily.sh").read_text(
        encoding="utf-8"
    )
    runner = (BACKEND / "scripts" / "generate_boss_command_center.py").read_text(
        encoding="utf-8"
    )

    assert 'scripts/generate_boss_command_center.py "$@"' in wrapper
    assert 'ZoneInfo("Asia/Shanghai")' in runner
    assert 'parser.add_argument("--date"' in runner
    assert 'parser.add_argument("--inventory-date"' in runner


def test_boss_daily_history_exposes_operating_detail_metrics():
    report_api = (BACKEND / "app" / "api" / "v1" / "report.py").read_text(encoding="utf-8")

    for field in (
        "actual_pay_amount",
        "item_count",
        "avg_order_value",
        "items_per_order",
        "avg_discount_rate",
        "return_rate",
        "gross_profit",
        "vip_sales_amount",
        "vip_negative_balance_amount",
        "data_quality_status",
        "metric_status",
    ):
        assert field in report_api


def test_dashboard_command_center_exposes_full_phase_one_metric_contract():
    command_source = (BACKEND / "app" / "services" / "command_center_service.py").read_text(
        encoding="utf-8"
    )

    for field in (
        '"avg_discount_rate": build_metric',
        '"return_amount": build_metric',
        '"return_rate": build_metric',
        '"age_180_amount": build_metric',
    ):
        assert field in command_source


def test_dashboard_splits_baison_online_payment_from_offline_sales():
    payment_source = (BACKEND / "app" / "services" / "sales_metric_service.py").read_text(encoding="utf-8")
    command_source = (BACKEND / "app" / "services" / "command_center_service.py").read_text(encoding="utf-8")
    dashboard_source = (BACKEND / "app" / "api" / "v1" / "dashboard.py").read_text(encoding="utf-8")

    assert "AS online_sales_amount" in payment_source
    assert "AS offline_sales_amount" in payment_source
    assert '"online_sales": sales_status' in command_source
    assert 'build_metric(data.get("online_sales")' in command_source
    assert '"online_sales": float(r["online_sales"] or 0)' in dashboard_source
