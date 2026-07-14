"""同步公共工具：access_token、oapi 调用、脱敏日志、权限提示。"""
import logging
from typing import Optional

import httpx

from app.core.database import AsyncSessionLocal
from app.services.dingtalk import DingtalkService
from app.services.dingtalk_budget_service import (
    DINGTALK_DAILY_API_LIMIT,
    DingtalkApiBudgetExceeded,
    consume_daily_dingtalk_budget,
    record_dingtalk_api_call,
)

logger = logging.getLogger("dingtalk.sync")

OAPI = "https://oapi.dingtalk.com"
def quiet_http_logs() -> None:
    """压低 httpx 日志，避免把含 access_token 的 URL 打进日志。"""
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


class DingtalkApiError(Exception):
    def __init__(self, errcode, errmsg):
        super().__init__(f"errcode={errcode} errmsg={errmsg}")
        self.errcode = errcode
        self.errmsg = errmsg


class DingtalkApiBudget:
    def __init__(self, limit: int, name: str = "dingtalk"):
        self.limit = max(0, int(limit))
        self.name = name
        self.used = 0

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def consume(self, path: str) -> None:
        if self.used >= self.limit:
            raise DingtalkApiBudgetExceeded(f"{self.name} api budget exhausted: {self.used}/{self.limit}")
        self.used += 1
        logger.info("钉钉接口预算 %s: %s/%s path=%s", self.name, self.used, self.limit, path)

    def refund(self) -> None:
        if self.used > 0:
            self.used -= 1

PERMISSION_HELP = (
    "可能缺少钉钉权限，请在开放平台『应用权限管理』开通：\n"
    "  - 通讯录部门信息读取\n"
    "  - 通讯录成员信息读取\n"
    "  - 考勤数据读取\n"
    "  - 审批实例读取\n"
    "  - 审批模板读取\n"
    "开通生效后重试。"
)


def print_permission_help(scope: str, err: "DingtalkApiError") -> None:
    logger.error("钉钉接口[%s]调用失败：%s", scope, err)
    logger.error(PERMISSION_HELP)


async def get_access_token() -> Optional[str]:
    async with AsyncSessionLocal() as db:
        return await DingtalkService(db)._get_access_token()


async def post_oapi(client: httpx.AsyncClient, path: str, token: str, body: dict,
                    budget: Optional[DingtalkApiBudget] = None) -> dict:
    """调用 oapi.dingtalk.com（access_token 走 query），errcode!=0 抛错。"""
    if budget:
        budget.consume(path)
    try:
        used = await consume_daily_dingtalk_budget(path, category="sync")
    except DingtalkApiBudgetExceeded as exc:
        if budget:
            budget.refund()
        await record_dingtalk_api_call(
            path=path, category="sync", priority="normal", status="denied",
            error_message=str(exc),
        )
        raise
    try:
        resp = await client.post(OAPI + path, params={"access_token": token}, json=body)
        data = resp.json()
        if isinstance(data, dict) and data.get("errcode") not in (0, None):
            raise DingtalkApiError(data.get("errcode"), data.get("errmsg"))
        await record_dingtalk_api_call(
            path=path, category="sync", priority="normal", status="success", used_after=used,
        )
        return data
    except Exception as exc:
        await record_dingtalk_api_call(
            path=path, category="sync", priority="normal", status="failed",
            used_after=used, error_message=str(exc),
        )
        raise


async def get_all_dept_ids(client: httpx.AsyncClient, token: str,
                           budget: Optional[DingtalkApiBudget] = None) -> list:
    """BFS 遍历所有部门 id（含根 1）。"""
    dept_ids = [1]
    queue = [1]
    while queue:
        d = queue.pop()
        data = await post_oapi(client, "/topapi/v2/department/listsub", token, {"dept_id": d}, budget)
        for item in data.get("result", []) or []:
            did = item.get("dept_id")
            if did and did not in dept_ids:
                dept_ids.append(did)
                queue.append(did)
    return dept_ids


async def get_user_ids_of_dept(client: httpx.AsyncClient, token: str, dept_id,
                               budget: Optional[DingtalkApiBudget] = None) -> list:
    data = await post_oapi(client, "/topapi/user/listid", token, {"dept_id": dept_id}, budget)
    return (data.get("result") or {}).get("userid_list", []) or []
