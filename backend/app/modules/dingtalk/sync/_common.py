"""同步公共工具：access_token、oapi 调用、脱敏日志、权限提示。"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.core.database import AsyncSessionLocal
from app.core.redis import get_redis
from app.services.dingtalk import DingtalkService

logger = logging.getLogger("dingtalk.sync")

OAPI = "https://oapi.dingtalk.com"
CST = timezone(timedelta(hours=8))
DINGTALK_DAILY_API_LIMIT = 160


def quiet_http_logs() -> None:
    """压低 httpx 日志，避免把含 access_token 的 URL 打进日志。"""
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


class DingtalkApiError(Exception):
    def __init__(self, errcode, errmsg):
        super().__init__(f"errcode={errcode} errmsg={errmsg}")
        self.errcode = errcode
        self.errmsg = errmsg


class DingtalkApiBudgetExceeded(Exception):
    """Raised before a DingTalk request when the configured daily budget is spent."""


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


def _daily_budget_key(now: Optional[datetime] = None) -> tuple[str, int]:
    now = now or datetime.now(CST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=CST)
    today = now.astimezone(CST).date().isoformat()
    tomorrow = (now.astimezone(CST).date() + timedelta(days=1))
    reset_at = datetime.combine(tomorrow, datetime.min.time(), tzinfo=CST)
    ttl = max(60, int((reset_at - now.astimezone(CST)).total_seconds()) + 300)
    return f"dingtalk:oapi:daily:{today}", ttl


async def consume_daily_dingtalk_budget(path: str, limit: int = DINGTALK_DAILY_API_LIMIT) -> int:
    """Consume one DingTalk daily API call from the shared Beijing-date budget."""
    key, ttl = _daily_budget_key()
    try:
        r = await get_redis()
        used = int(await r.incr(key))
        if used == 1:
            await r.expire(key, ttl)
        elif used > limit:
            await r.decr(key)
            raise DingtalkApiBudgetExceeded(f"dingtalk daily api budget exhausted: {limit}/{limit}")
        logger.info("钉钉每日接口预算: %s/%s path=%s", used, limit, path)
        return used
    except DingtalkApiBudgetExceeded:
        raise
    except Exception as exc:
        raise DingtalkApiBudgetExceeded(f"dingtalk daily api budget unavailable: {exc}") from exc


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
        await consume_daily_dingtalk_budget(path)
    except DingtalkApiBudgetExceeded:
        if budget:
            budget.refund()
        raise
    resp = await client.post(OAPI + path, params={"access_token": token}, json=body)
    data = resp.json()
    if isinstance(data, dict) and data.get("errcode") not in (0, None):
        raise DingtalkApiError(data.get("errcode"), data.get("errmsg"))
    return data


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
