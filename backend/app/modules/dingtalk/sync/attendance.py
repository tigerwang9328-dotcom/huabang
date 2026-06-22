"""同步钉钉考勤 -> dingtalk_attendance_records，并聚合 hr_attendance_daily。"""
import logging
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.models.dingtalk_attendance import DingtalkAttendanceRecord
from app.modules.dingtalk.sync._common import (
    DingtalkApiError, get_access_token, get_all_dept_ids,
    get_user_ids_of_dept, post_oapi, print_permission_help,
)

logger = logging.getLogger("dingtalk.sync")
CST = timezone(timedelta(hours=8))
LATE = ("Late", "SeriousLate", "VeryLate")
MISSING = ("NotSigned", "Absenteeism")


async def _all_user_ids(client, token) -> list:
    seen, out = set(), []
    for d in await get_all_dept_ids(client, token):
        for uid in await get_user_ids_of_dept(client, token, d):
            if uid not in seen:
                seen.add(uid)
                out.append(uid)
    return out


async def fetch_attendance(client, token, user_ids, date_from, date_to) -> list:
    out = []
    for i in range(0, len(user_ids), 50):
        chunk = user_ids[i:i + 50]
        offset = 0
        while True:
            body = {"workDateFrom": date_from, "workDateTo": date_to,
                    "userIdList": chunk, "offset": offset, "limit": 50, "isI18n": False}
            data = await post_oapi(client, "/attendance/list", token, body)
            recs = data.get("recordresult") or []
            out.extend(recs)
            if data.get("hasMore") and recs:
                offset += 50
            else:
                break
    return out


def _to_date(v):
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v / 1000, tz=CST).date()
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except (ValueError, OSError, OverflowError):
        return None


def _ms_to_dt(v):
    if not v:
        return None
    try:
        return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc)
    except (ValueError, OSError, OverflowError, TypeError):
        return None


def parse_record(rec: dict) -> dict:
    return {
        "dingtalk_user_id": rec.get("userId"),
        "user_name": rec.get("userName") or None,
        "work_date": _to_date(rec.get("workDate")),
        "check_time": _ms_to_dt(rec.get("userCheckTime")),
        "check_type": rec.get("checkType"),
        "time_result": rec.get("timeResult"),
        "location_result": rec.get("locationResult"),
        "source_type": rec.get("sourceType"),
        "approve_id": str(rec.get("approveId")) if rec.get("approveId") else None,
        "raw_payload": rec,
    }


def _stats(parsed):
    users = {p["dingtalk_user_id"] for p in parsed if p["dingtalk_user_id"]}
    late = sum(1 for p in parsed if p["time_result"] in LATE)
    early = sum(1 for p in parsed if p["time_result"] == "Early")
    miss = sum(1 for p in parsed if p["time_result"] in MISSING or p["location_result"] == "NotSigned")
    return {"records": len(parsed), "users": len(users), "late": late, "early_leave": early, "missing_check": miss}


async def save_records(parsed) -> int:
    async with AsyncSessionLocal() as s:
        for rec in parsed:
            stmt = pg_insert(DingtalkAttendanceRecord).values(**rec)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_dt_attendance",
                set_={k: getattr(stmt.excluded, k) for k in
                      ("time_result", "location_result", "source_type", "approve_id", "raw_payload")})
            await s.execute(stmt)
        await s.commit()
    return len(parsed)


_DAILY_SQL = text("""
INSERT INTO hr_attendance_daily
  (work_date, dingtalk_user_id, employee_name, department_name,
   normal_count, late_count, early_leave_count, missing_check_count, leave_count, attendance_status)
SELECT a.work_date, a.dingtalk_user_id, max(e.name), NULL,
  count(*) FILTER (WHERE a.time_result='Normal'),
  count(*) FILTER (WHERE a.time_result IN ('Late','SeriousLate','VeryLate')),
  count(*) FILTER (WHERE a.time_result='Early'),
  count(*) FILTER (WHERE a.time_result IN ('NotSigned','Absenteeism') OR a.location_result='NotSigned'),
  0,
  CASE WHEN count(*) FILTER (WHERE a.time_result <> 'Normal' OR a.location_result='NotSigned') > 0
       THEN 'abnormal' ELSE 'normal' END
FROM dingtalk_attendance_records a
LEFT JOIN dingtalk_employees e ON e.dingtalk_user_id = a.dingtalk_user_id
WHERE a.work_date BETWEEN :dfrom AND :dto AND a.work_date IS NOT NULL
GROUP BY a.work_date, a.dingtalk_user_id
ON CONFLICT (work_date, dingtalk_user_id) DO UPDATE SET
  employee_name=EXCLUDED.employee_name,
  normal_count=EXCLUDED.normal_count, late_count=EXCLUDED.late_count,
  early_leave_count=EXCLUDED.early_leave_count, missing_check_count=EXCLUDED.missing_check_count,
  attendance_status=EXCLUDED.attendance_status, updated_at=now()
""")


async def build_daily(dfrom, dto) -> int:
    async with AsyncSessionLocal() as s:
        await s.execute(_DAILY_SQL, {"dfrom": dfrom, "dto": dto})
        await s.commit()
        n = (await s.execute(text(
            "SELECT count(*) FROM hr_attendance_daily WHERE work_date BETWEEN :a AND :b"),
            {"a": dfrom, "b": dto})).scalar()
    return n or 0


async def run(days: int = 7, dry_run: bool = False) -> dict:
    days = max(1, min(days, 7))
    today = datetime.now(CST).date()
    dfrom_d = today - timedelta(days=days - 1)
    date_from = dfrom_d.strftime("%Y-%m-%d") + " 00:00:00"
    date_to = today.strftime("%Y-%m-%d") + " 23:59:59"
    token = await get_access_token()
    if not token:
        logger.error("无法获取 access_token，终止考勤同步。")
        return {"records": 0}
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            user_ids = await _all_user_ids(client, token)
            raw = await fetch_attendance(client, token, user_ids, date_from, date_to)
        except DingtalkApiError as e:
            print_permission_help("考勤", e)
            return {"records": 0, "error": "permission"}
    parsed = [parse_record(r) for r in raw]
    stats = _stats(parsed)
    logger.info("考勤同步统计: %s", stats)
    if dry_run:
        logger.info("[dry-run] 考勤不入库。")
        return stats
    await save_records(parsed)
    daily = await build_daily(dfrom_d, today)
    logger.info("考勤已落库，hr_attendance_daily 汇总行: %d", daily)
    stats["daily_rows"] = daily
    return stats
