from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.services.command_center_health_service import (
    build_health_task_no,
    evaluate_command_center_health,
    health_dates,
)


BJT = ZoneInfo("Asia/Shanghai")
REPO = Path(__file__).resolve().parents[2]


def test_healthy_daily_cycle_has_no_alerts() -> None:
    now = datetime(2026, 7, 15, 6, 40, tzinfo=BJT)
    report_date, inventory_date = health_dates(now)

    issues = evaluate_command_center_health(
        report_date=report_date,
        inventory_date=inventory_date,
        observed={
            "pos_status": "success",
            "pos_start_date": date(2026, 7, 9),
            "pos_end_date": date(2026, 7, 15),
            "pos_completed_at": datetime(2026, 7, 15, 4, 0, tzinfo=BJT),
            "inventory_stat_date": inventory_date,
            "inventory_store_count": 10,
            "inventory_updated_at": datetime(2026, 7, 15, 5, 35, tzinfo=BJT),
            "snapshot_report_date": report_date,
            "snapshot_generated_at": datetime(2026, 7, 15, 6, 31, tzinfo=BJT),
            "metric_status": {
                "sales": "ready",
                "returns": "ready",
                "inventory": "ready",
                "vip_balance": "ready",
            },
        },
        expected_inventory_store_count=10,
    )

    assert issues == []
    assert build_health_task_no(report_date) == "HEALTH-20260714"


def test_missing_jobs_return_specific_health_issues() -> None:
    issues = evaluate_command_center_health(
        report_date=date(2026, 7, 14),
        inventory_date=date(2026, 7, 15),
        observed={
            "pos_status": "failed",
            "inventory_stat_date": date(2026, 7, 14),
            "inventory_store_count": 9,
            "snapshot_report_date": None,
        },
        expected_inventory_store_count=10,
    )

    assert {item["code"] for item in issues} == {
        "pos_sync_missing_or_failed",
        "inventory_business_date_mismatch",
        "inventory_scope_incomplete",
        "command_center_missing",
    }


def test_stale_core_source_becomes_health_issue() -> None:
    issues = evaluate_command_center_health(
        report_date=date(2026, 7, 14),
        inventory_date=date(2026, 7, 15),
        observed={
            "pos_status": "success",
            "pos_start_date": date(2026, 7, 14),
            "pos_end_date": date(2026, 7, 14),
            "pos_completed_at": datetime(2026, 7, 15, 4, 0, tzinfo=BJT),
            "inventory_stat_date": date(2026, 7, 15),
            "inventory_store_count": 10,
            "inventory_updated_at": datetime(2026, 7, 15, 5, 35, tzinfo=BJT),
            "snapshot_report_date": date(2026, 7, 14),
            "snapshot_generated_at": datetime(2026, 7, 15, 6, 31, tzinfo=BJT),
            "metric_status": {
                "sales": "ready",
                "returns": "stale",
                "inventory": "ready",
                "vip_balance": "ready",
            },
        },
        expected_inventory_store_count=10,
    )

    assert [item["code"] for item in issues] == ["command_center_source_stale:returns"]


def test_same_business_dates_still_require_the_scheduled_refresh_times() -> None:
    issues = evaluate_command_center_health(
        report_date=date(2026, 7, 14),
        inventory_date=date(2026, 7, 15),
        observed={
            "pos_status": "success",
            "pos_start_date": date(2026, 7, 14),
            "pos_end_date": date(2026, 7, 14),
            "pos_completed_at": datetime(2026, 7, 15, 3, 50, tzinfo=BJT),
            "inventory_stat_date": date(2026, 7, 15),
            "inventory_store_count": 10,
            "inventory_updated_at": datetime(2026, 7, 15, 5, 0, tzinfo=BJT),
            "snapshot_report_date": date(2026, 7, 14),
            "snapshot_generated_at": datetime(2026, 7, 15, 6, 0, tzinfo=BJT),
            "metric_status": {key: "ready" for key in ("sales", "returns", "inventory", "vip_balance")},
        },
        expected_inventory_store_count=10,
    )

    assert {item["code"] for item in issues} == {
        "pos_sync_stale",
        "inventory_sync_stale",
        "command_center_stale",
    }


def test_monitor_is_scheduled_after_command_center_and_creates_only_drafts() -> None:
    scheduler = (REPO / "backend" / "app" / "jobs" / "scheduler.py").read_text(encoding="utf-8")
    service = (
        REPO / "backend" / "app" / "services" / "command_center_health_service.py"
    ).read_text(encoding="utf-8")

    assert "run_command_center_health_monitor" in scheduler
    assert "CronTrigger(hour=6, minute=40" in scheduler
    assert "ON CONFLICT(task_no) DO UPDATE" in service
    assert "SELECT status pos_status" in service
    assert "'draft'" in service
    assert "requires_human_confirm" in service
