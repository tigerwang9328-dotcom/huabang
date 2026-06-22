"""同步钉钉审批实例 -> dingtalk_approval_instances，并把报销/付款写入 finance_expense_records。"""
import logging
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.models.dingtalk_hr_finance import DingtalkApprovalInstance, FinanceExpenseRecord
from app.modules.dingtalk.sync._common import (
    DingtalkApiError, get_access_token, get_all_dept_ids,
    get_user_ids_of_dept, post_oapi, print_permission_help,
)
from app.modules.dingtalk.sync.finance_parser import categorize, parse_finance_record

logger = logging.getLogger("dingtalk.sync")
CST = timezone(timedelta(hours=8))

MAX_INSTANCES_PER_PROCESS = 200


async def list_process_codes(client, token, sample_user_ids) -> dict:
    """通过若干用户可见的审批模板，收集 {process_code: name}。"""
    codes = {}
    for uid in sample_user_ids[:10]:
        try:
            data = await post_oapi(client, "/topapi/process/listbyuserid", token,
                                   {"userid": uid, "offset": 0, "size": 100})
        except DingtalkApiError:
            continue
        for p in (data.get("result") or {}).get("process_list", []) or []:
            code = p.get("process_code")
            if code and code not in codes:
                codes[code] = p.get("name")
    return codes


async def list_instance_ids(client, token, process_code, start_ms, end_ms) -> list:
    ids, cursor = [], 0
    while True:
        data = await post_oapi(client, "/topapi/processinstance/listids", token, {
            "process_code": process_code, "start_time": start_ms,
            "end_time": end_ms, "size": 20, "cursor": cursor})
        result = data.get("result") or {}
        ids.extend(result.get("list") or [])
        cursor = result.get("next_cursor")
        if not cursor or len(ids) >= MAX_INSTANCES_PER_PROCESS:
            break
    return ids[:MAX_INSTANCES_PER_PROCESS]


def _parse_dt(v):
    if not v:
        return None
    try:
        return datetime.strptime(str(v).replace("T", " ")[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


async def get_instance(client, token, pid, process_name) -> dict:
    data = await post_oapi(client, "/topapi/processinstance/get", token, {"process_instance_id": pid})
    pi = data.get("process_instance") or {}
    pi["_process_instance_id"] = pid
    pi["_process_name"] = process_name
    pi["_category"] = categorize(process_name, pi.get("title"))
    pi["_originator_name"] = None
    return pi


def to_approval_row(pi: dict, process_code: str) -> dict:
    ct = _parse_dt(pi.get("create_time"))
    ft = _parse_dt(pi.get("finish_time"))
    amount = None
    fin = parse_finance_record(pi)
    if fin:
        amount = fin.get("amount")
    return {
        "process_instance_id": pi.get("_process_instance_id"),
        "process_code": process_code,
        "process_name": pi.get("_process_name"),
        "business_id": pi.get("business_id"),
        "title": pi.get("title"),
        "originator_user_id": pi.get("originator_userid"),
        "originator_name": pi.get("_originator_name"),
        "originator_dept_id": str(pi.get("originator_dept_id")) if pi.get("originator_dept_id") else None,
        "originator_dept_name": pi.get("originator_dept_name"),
        "status": pi.get("status"),
        "result": pi.get("result"),
        "create_time": ct.replace(tzinfo=CST) if ct else None,
        "finish_time": ft.replace(tzinfo=CST) if ft else None,
        "category": pi.get("_category"),
        "amount": amount,
        "raw_payload": pi,
    }


async def save_instances(rows: list) -> int:
    async with AsyncSessionLocal() as s:
        for r in rows:
            stmt = pg_insert(DingtalkApprovalInstance).values(**r)
            stmt = stmt.on_conflict_do_update(
                index_elements=["process_instance_id"],
                set_={k: getattr(stmt.excluded, k) for k in
                      ("process_name", "title", "status", "result", "finish_time",
                       "category", "amount", "raw_payload")})
            await s.execute(stmt)
        await s.commit()
    return len(rows)


async def save_finance(rows: list) -> int:
    async with AsyncSessionLocal() as s:
        for r in rows:
            stmt = pg_insert(FinanceExpenseRecord).values(**r)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_finance_expense_source",
                set_={k: getattr(stmt.excluded, k) for k in
                      ("amount", "approval_status", "payment_status", "category", "raw_payload")})
            await s.execute(stmt)
        await s.commit()
    return len(rows)


async def run(days: int = 30, dry_run: bool = False) -> dict:
    today = datetime.now(CST)
    start = today - timedelta(days=days)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(today.timestamp() * 1000)
    token = await get_access_token()
    if not token:
        logger.error("无法获取 access_token，终止审批同步。")
        return {"instances": 0}

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            sample_users = []
            for d in await get_all_dept_ids(client, token):
                sample_users.extend(await get_user_ids_of_dept(client, token, d))
                if len(sample_users) >= 10:
                    break
            codes = await list_process_codes(client, token, sample_users)
            logger.info("可见审批模板数: %d", len(codes))
            if not codes:
                logger.warning("未获取到审批模板（可能缺少『审批模板读取』权限），跳过审批同步。")
                return {"instances": 0, "finance": 0, "templates": 0}

            approval_rows, finance_rows = [], []
            for code, name in codes.items():
                try:
                    ids = await list_instance_ids(client, token, code, start_ms, end_ms)
                except DingtalkApiError as e:
                    logger.warning("审批实例列表失败 process=%s: %s", name, e)
                    continue
                for pid in ids:
                    try:
                        pi = await get_instance(client, token, pid, name)
                    except DingtalkApiError as e:
                        logger.warning("审批详情失败: %s", e)
                        continue
                    approval_rows.append(to_approval_row(pi, code))
                    fin = parse_finance_record(pi)
                    if fin:
                        finance_rows.append(fin)
        except DingtalkApiError as e:
            print_permission_help("审批", e)
            return {"instances": 0, "finance": 0, "error": "permission"}

    cat_stat = {}
    for r in approval_rows:
        cat_stat[r["category"]] = cat_stat.get(r["category"], 0) + 1
    stats = {"templates": len(codes), "instances": len(approval_rows),
             "finance": len(finance_rows), "by_category": cat_stat}
    logger.info("审批同步统计: %s", stats)
    if dry_run:
        logger.info("[dry-run] 审批不入库。")
        return stats
    await save_instances(approval_rows)
    await save_finance(finance_rows)
    logger.info("审批/财务 已落库。")
    return stats
