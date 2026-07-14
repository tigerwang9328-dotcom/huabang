"""钉钉考勤数据主动同步（拉取已有历史考勤打卡记录）。

用法:
    cd /srv/huabang-ai-center/backend
    .venv/bin/python -m app.modules.dingtalk.attendance_sync --days 7
    .venv/bin/python -m app.modules.dingtalk.attendance_sync --days 1 --dry-run

流程：复用 DingtalkService 取 access_token -> 遍历部门拿 userId -> 调考勤接口拉打卡记录 -> 幂等落库。
日志脱敏：不打印 token、不打印完整 userId 列表，只打印计数。
"""
import argparse
import asyncio
import logging
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.core.logger import setup_logging
from app.models.dingtalk_attendance import DingtalkAttendanceRecord
from app.services.dingtalk import DingtalkService
from app.modules.dingtalk.sync._common import DingtalkApiError, post_oapi

logger = logging.getLogger("dingtalk.attendance")

CST = timezone(timedelta(hours=8))

DEPT_LISTSUB_PATH = "/topapi/v2/department/listsub"
USER_LISTID_PATH = "/topapi/user/listid"
ATTENDANCE_LIST_PATH = "/attendance/list"

LATE_RESULTS = ("Late", "SeriousLate", "VeryLate")
MISSING_RESULTS = ("NotSigned", "Absenteeism")


async def get_all_user_ids(client: httpx.AsyncClient, token: str) -> list:
    """从根部门 BFS 遍历所有部门，收集去重 userId。"""
    dept_ids = [1]
    queue = [1]
    while queue:
        d = queue.pop()
        data = await post_oapi(client, DEPT_LISTSUB_PATH, token, {"dept_id": d})
        for item in data.get("result", []) or []:
            did = item.get("dept_id")
            if did and did not in dept_ids:
                dept_ids.append(did)
                queue.append(did)

    user_ids, seen = [], set()
    for d in dept_ids:
        data = await post_oapi(client, USER_LISTID_PATH, token, {"dept_id": d})
        for uid in (data.get("result") or {}).get("userid_list", []) or []:
            if uid not in seen:
                seen.add(uid)
                user_ids.append(uid)
    return user_ids


async def fetch_attendance(client: httpx.AsyncClient, token: str, user_ids: list,
                           date_from: str, date_to: str) -> list:
    """分批(<=50 userId)+分页拉取考勤打卡记录。"""
    out = []
    for i in range(0, len(user_ids), 50):
        chunk = user_ids[i:i + 50]
        offset = 0
        while True:
            body = {
                "workDateFrom": date_from,
                "workDateTo": date_to,
                "userIdList": chunk,
                "offset": offset,
                "limit": 50,
                "isI18n": False,
            }
            data = await post_oapi(client, ATTENDANCE_LIST_PATH, token, body)
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


def _stats(parsed: list) -> dict:
    users = {p["dingtalk_user_id"] for p in parsed if p["dingtalk_user_id"]}
    late = sum(1 for p in parsed if p["time_result"] in LATE_RESULTS)
    early = sum(1 for p in parsed if p["time_result"] == "Early")
    missing = sum(1 for p in parsed if p["time_result"] in MISSING_RESULTS or p["location_result"] == "NotSigned")
    normal = sum(1 for p in parsed if p["time_result"] == "Normal")
    return {"records": len(parsed), "users": len(users), "late": late,
            "early_leave": early, "missing_check": missing, "normal": normal}


async def save_all(parsed: list) -> int:
    """幂等落库，返回写入(含更新)行数。"""
    written = 0
    async with AsyncSessionLocal() as session:
        for rec in parsed:
            stmt = pg_insert(DingtalkAttendanceRecord).values(**rec)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_dt_attendance",
                set_={
                    "time_result": stmt.excluded.time_result,
                    "location_result": stmt.excluded.location_result,
                    "source_type": stmt.excluded.source_type,
                    "approve_id": stmt.excluded.approve_id,
                    "raw_payload": stmt.excluded.raw_payload,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await session.execute(stmt)
            written += 1
        await session.commit()
    return written


def _print_permission_help(scope: str, err: "DingtalkApiError") -> None:
    logger.error("钉钉接口[%s]调用失败：%s", scope, err)
    logger.error(
        "可能缺少权限，请在钉钉开放平台『应用权限管理』为本应用开通：\n"
        "  1) 考勤数据读取权限（考勤排班/打卡结果）\n"
        "  2) 通讯录用户信息读取权限（成员 userId）\n"
        "  3) 部门信息读取权限\n"
        "开通后等待生效，再重新执行同步。"
    )


async def run(days: int, dry_run: bool) -> None:
    days = max(1, min(days, 7))  # 钉钉考勤接口单次跨度上限 7 天
    today = datetime.now(CST).date()
    date_from = (today - timedelta(days=days - 1)).strftime("%Y-%m-%d") + " 00:00:00"
    date_to = today.strftime("%Y-%m-%d") + " 23:59:59"
    logger.info("考勤同步窗口: %s ~ %s (dry_run=%s)", date_from, date_to, dry_run)

    async with AsyncSessionLocal() as db:
        token = await DingtalkService(db)._get_access_token()
    if not token:
        logger.error("无法获取钉钉 access_token（检查 DINGTALK_CLIENT_ID/SECRET 或网络），终止。")
        return

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            user_ids = await get_all_user_ids(client, token)
        except DingtalkApiError as e:
            _print_permission_help("通讯录/部门", e)
            return
        logger.info("获取到 %d 个员工 userId", len(user_ids))
        if not user_ids:
            logger.warning("未获取到任何员工 userId（通讯录权限不足或组织为空），终止。")
            return

        try:
            raw_records = await fetch_attendance(client, token, user_ids, date_from, date_to)
        except DingtalkApiError as e:
            _print_permission_help("考勤", e)
            return

    parsed = [parse_record(r) for r in raw_records]
    stats = _stats(parsed)
    logger.info("拉取考勤记录: %s", stats)

    if dry_run:
        logger.info("[dry-run] 仅统计，不入库。")
        return

    written = await save_all(parsed)
    logger.info("考勤记录已落库(幂等): %d 条", written)


def main() -> None:
    setup_logging()
    # 关键：压低 httpx 日志级别，避免把含 access_token 的请求 URL 打进日志（脱敏）
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description="钉钉考勤数据主动同步")
    parser.add_argument("--days", type=int, default=7, help="同步最近 N 天（1-7），默认 7")
    parser.add_argument("--dry-run", action="store_true", help="只统计不入库")
    args = parser.parse_args()
    asyncio.run(run(args.days, args.dry_run))


if __name__ == "__main__":
    main()
