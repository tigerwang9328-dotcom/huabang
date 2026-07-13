"""同步钉钉部门与员工 -> dingtalk_departments / dingtalk_employees。"""
import logging

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.models.dingtalk_hr_finance import DingtalkDepartment, DingtalkEmployee
from app.modules.dingtalk.sync._common import (
    DingtalkApiError, get_access_token, get_all_dept_ids,
    get_user_ids_of_dept, post_oapi, print_permission_help,
)

logger = logging.getLogger("dingtalk.sync")


async def fetch_departments(client, token) -> list:
    """返回 [{dept_id, name, parent_id, raw}]。"""
    out = []
    for d in await get_all_dept_ids(client, token):
        try:
            data = await post_oapi(client, "/topapi/v2/department/get", token, {"dept_id": d})
            r = data.get("result") or {}
            out.append({"dept_id": str(d), "name": r.get("name"),
                        "parent_id": str(r.get("parent_id")) if r.get("parent_id") else None, "raw": r})
        except DingtalkApiError:
            out.append({"dept_id": str(d), "name": None, "parent_id": None, "raw": {}})
    return out


async def fetch_employees(client, token, department_names: dict[str, str] | None = None) -> list:
    """遍历部门取 userId，再取员工详情。"""
    seen, out = set(), []
    for d in await get_all_dept_ids(client, token):
        for uid in await get_user_ids_of_dept(client, token, d):
            if uid in seen:
                continue
            seen.add(uid)
            try:
                data = await post_oapi(client, "/topapi/v2/user/get", token, {"userid": uid})
                r = data.get("result") or {}
                dept_ids = r.get("dept_id_list") or []
                out.append({
                    "dingtalk_user_id": uid,
                    "name": r.get("name"),
                    "mobile": r.get("mobile"),
                    "department_ids": dept_ids,
                    "department_names": [department_names[str(x)] for x in dept_ids if department_names and str(x) in department_names] or None,
                    "position": r.get("title"),
                    "job_number": r.get("job_number"),
                    "email": r.get("email"),
                    "active": bool(r.get("active", True)),
                    "raw_payload": r,
                })
            except DingtalkApiError as e:
                logger.warning("员工详情获取失败 uid=*** : %s", e)
    return out


async def save_departments(rows: list) -> int:
    async with AsyncSessionLocal() as s:
        for r in rows:
            stmt = pg_insert(DingtalkDepartment).values(
                dingtalk_dept_id=r["dept_id"], name=r["name"],
                parent_id=r["parent_id"], raw_payload=r["raw"])
            stmt = stmt.on_conflict_do_update(
                index_elements=["dingtalk_dept_id"],
                set_={"name": stmt.excluded.name, "parent_id": stmt.excluded.parent_id,
                      "raw_payload": stmt.excluded.raw_payload})
            await s.execute(stmt)
        await s.commit()
    return len(rows)


async def save_employees(rows: list) -> int:
    async with AsyncSessionLocal() as s:
        for r in rows:
            stmt = pg_insert(DingtalkEmployee).values(**r)
            stmt = stmt.on_conflict_do_update(
                index_elements=["dingtalk_user_id"],
                set_={k: getattr(stmt.excluded, k) for k in
                      ("name", "mobile", "department_ids", "department_names", "position", "job_number", "email", "active", "raw_payload")})
            await s.execute(stmt)
        await s.commit()
    return len(rows)


async def run(dry_run: bool = False) -> dict:
    token = await get_access_token()
    if not token:
        logger.error("无法获取 access_token，终止员工同步。")
        return {"departments": 0, "employees": 0}
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            depts = await fetch_departments(client, token)
            dept_names = {str(d["dept_id"]): d["name"] for d in depts if d.get("name")}
            emps = await fetch_employees(client, token, dept_names)
        except DingtalkApiError as e:
            print_permission_help("通讯录/部门", e)
            return {"departments": 0, "employees": 0, "error": "permission"}
    stats = {"departments": len(depts), "employees": len(emps)}
    logger.info("员工同步统计: %s", stats)
    if dry_run:
        logger.info("[dry-run] 员工/部门 不入库。")
        return stats
    await save_departments(depts)
    await save_employees(emps)
    logger.info("员工/部门 已落库。")
    return stats
