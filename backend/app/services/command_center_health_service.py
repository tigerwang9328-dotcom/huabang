"""Daily command-center data health checks and idempotent alert drafts."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.store_whitelist import ALLOWED_INVENTORY_CODES


BJT = ZoneInfo("Asia/Shanghai")
CORE_READY_METRICS = ("sales", "returns", "inventory", "vip_balance")


def health_dates(now: datetime | None = None) -> tuple[date, date]:
    current = now.astimezone(BJT) if now else datetime.now(BJT)
    return current.date() - timedelta(days=1), current.date()


def build_health_task_no(report_date: date) -> str:
    return f"HEALTH-{report_date:%Y%m%d}"


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _before_schedule(value: Any, *, business_date: date, hour: int, minute: int) -> bool:
    if not isinstance(value, datetime):
        return True
    aware_value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    threshold = datetime.combine(business_date, time(hour, minute), tzinfo=BJT)
    return aware_value.astimezone(BJT) < threshold


def evaluate_command_center_health(
    *,
    report_date: date,
    inventory_date: date,
    observed: dict[str, Any],
    expected_inventory_store_count: int,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    pos_covers_date = (
        observed.get("pos_start_date") is not None
        and observed.get("pos_end_date") is not None
        and observed["pos_start_date"] <= report_date <= observed["pos_end_date"]
    )
    if observed.get("pos_status") != "success" or not pos_covers_date:
        issues.append(_issue("pos_sync_missing_or_failed", f"{report_date} 百胜小票/退货同步未成功覆盖"))
    elif _before_schedule(
        observed.get("pos_completed_at"), business_date=inventory_date, hour=4, minute=0
    ):
        issues.append(_issue("pos_sync_stale", f"{report_date} 小票/退货数据不是当日 04:00 批次"))

    if observed.get("inventory_stat_date") != inventory_date:
        issues.append(_issue(
            "inventory_business_date_mismatch",
            f"库存业务日应为 {inventory_date}，实际为 {observed.get('inventory_stat_date') or '无'}",
        ))
    elif _before_schedule(
        observed.get("inventory_updated_at"), business_date=inventory_date, hour=5, minute=30
    ):
        issues.append(_issue("inventory_sync_stale", f"{inventory_date} 库存不是当日 05:30 后快照"))
    if int(observed.get("inventory_store_count") or 0) != expected_inventory_store_count:
        issues.append(_issue(
            "inventory_scope_incomplete",
            f"库存范围应为 {expected_inventory_store_count} 个编码，实际为 {int(observed.get('inventory_store_count') or 0)} 个",
        ))

    if observed.get("snapshot_report_date") != report_date:
        issues.append(_issue("command_center_missing", f"{report_date} 老板经营快照未生成"))
        return issues
    if _before_schedule(
        observed.get("snapshot_generated_at"), business_date=inventory_date, hour=6, minute=30
    ):
        issues.append(_issue("command_center_stale", f"{report_date} 经营快照不是当日 06:30 后生成"))

    statuses = observed.get("metric_status") or {}
    for metric in CORE_READY_METRICS:
        if statuses.get(metric) != "ready":
            issues.append(_issue(
                f"command_center_source_stale:{metric}",
                f"经营快照核心来源 {metric} 状态为 {statuses.get(metric) or '缺失'}",
            ))
    return issues


async def monitor_command_center_health(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    creator_id: int = 1,
) -> dict[str, Any]:
    locked = (await db.execute(text(
        "SELECT pg_try_advisory_xact_lock(hashtext('huabang_command_center_health'))"
    ))).scalar()
    if not locked:
        return {"ok": True, "skipped": True, "reason": "another monitor is active"}

    report_date, inventory_date = health_dates(now)
    pos = (await db.execute(text("""
        SELECT status pos_status, biz_start_time::date pos_start_date,
               biz_end_time::date pos_end_date, completed_at pos_completed_at
        FROM ods.ods_baison_pos_ticket_sync_run
        WHERE biz_start_time < CAST(:report_date AS date) + INTERVAL '1 day'
          AND biz_end_time >= CAST(:report_date AS date)
        ORDER BY started_at DESC, id DESC
        LIMIT 1
    """), {"report_date": report_date})).mappings().first() or {}
    inventory = (await db.execute(text("""
        SELECT stat_date inventory_stat_date,
               COUNT(DISTINCT UPPER(store_code))::int inventory_store_count,
               MAX(etl_at) inventory_updated_at
        FROM dws.dws_inventory_daily
        WHERE stat_date=(SELECT MAX(stat_date) FROM dws.dws_inventory_daily WHERE stat_date<=:inventory_date)
          AND UPPER(store_code)=ANY(:codes)
        GROUP BY stat_date
    """), {
        "inventory_date": inventory_date,
        "codes": sorted(ALLOWED_INVENTORY_CODES),
    })).mappings().first() or {}
    snapshot = (await db.execute(text("""
        SELECT report_date snapshot_report_date, generated_at snapshot_generated_at,
               metric_status
        FROM dm.dm_boss_daily_report
        WHERE report_date=:report_date
    """), {"report_date": report_date})).mappings().first() or {}

    observed = {**dict(pos), **dict(inventory), **dict(snapshot)}
    issues = evaluate_command_center_health(
        report_date=report_date,
        inventory_date=inventory_date,
        observed=observed,
        expected_inventory_store_count=len(ALLOWED_INVENTORY_CODES),
    )
    if not issues:
        return {
            "ok": True,
            "skipped": False,
            "healthy": True,
            "report_date": str(report_date),
            "inventory_date": str(inventory_date),
            "issues": [],
        }

    task_no = build_health_task_no(report_date)
    evidence = {
        "report_date": str(report_date),
        "inventory_date": str(inventory_date),
        "checked_at": (now.astimezone(BJT) if now else datetime.now(BJT)).isoformat(),
        "issues": issues,
        "observed": observed,
    }
    messages = "；".join(item["message"] for item in issues)
    task = (await db.execute(text("""
        INSERT INTO app.app_action_task(
            task_no, title, description, data_evidence, data_evidence_text,
            suggested_actions, feedback_requirement, source_type, source_id,
            related_date, creator_id, status, priority, risk_level,
            requires_human_confirm, due_date, is_deleted
        ) VALUES (
            :task_no, :title, :description, CAST(:evidence AS json), :evidence_text,
            CAST(:actions AS json), '核对同步日志、修复数据源并重新生成经营快照',
            'data_freshness', :source_id, :report_date, :creator_id, 'draft', 10,
            'critical', true, :due_date, false
        ) ON CONFLICT(task_no) DO UPDATE SET
            description=EXCLUDED.description,
            data_evidence=EXCLUDED.data_evidence,
            data_evidence_text=EXCLUDED.data_evidence_text,
            suggested_actions=EXCLUDED.suggested_actions,
            updated_at=now()
        RETURNING id, task_no, status
    """), {
        "task_no": task_no,
        "title": f"【数据健康】{report_date} 经营快照异常",
        "description": messages,
        "evidence": json.dumps(evidence, ensure_ascii=False, default=str),
        "evidence_text": messages,
        "actions": json.dumps([
            "检查 04:00 小票与退货同步",
            "检查 05:30 十编码库存同步",
            "修复后幂等重跑 06:30 经营快照",
        ], ensure_ascii=False),
        "source_id": int(report_date.strftime("%Y%m%d")),
        "report_date": report_date,
        "creator_id": creator_id,
        "due_date": inventory_date,
    })).mappings().one()
    return {
        "ok": True,
        "skipped": False,
        "healthy": False,
        "report_date": str(report_date),
        "inventory_date": str(inventory_date),
        "issues": issues,
        "task": dict(task),
    }
