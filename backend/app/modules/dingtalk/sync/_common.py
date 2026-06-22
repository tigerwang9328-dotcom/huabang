"""同步公共工具：access_token、oapi 调用、脱敏日志、权限提示。"""
import logging
from typing import Optional

import httpx

from app.core.database import AsyncSessionLocal
from app.services.dingtalk import DingtalkService

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


async def post_oapi(client: httpx.AsyncClient, path: str, token: str, body: dict) -> dict:
    """调用 oapi.dingtalk.com（access_token 走 query），errcode!=0 抛错。"""
    resp = await client.post(OAPI + path, params={"access_token": token}, json=body)
    data = resp.json()
    if isinstance(data, dict) and data.get("errcode") not in (0, None):
        raise DingtalkApiError(data.get("errcode"), data.get("errmsg"))
    return data


async def get_all_dept_ids(client: httpx.AsyncClient, token: str) -> list:
    """BFS 遍历所有部门 id（含根 1）。"""
    dept_ids = [1]
    queue = [1]
    while queue:
        d = queue.pop()
        data = await post_oapi(client, "/topapi/v2/department/listsub", token, {"dept_id": d})
        for item in data.get("result", []) or []:
            did = item.get("dept_id")
            if did and did not in dept_ids:
                dept_ids.append(did)
                queue.append(did)
    return dept_ids


async def get_user_ids_of_dept(client: httpx.AsyncClient, token: str, dept_id) -> list:
    data = await post_oapi(client, "/topapi/user/listid", token, {"dept_id": dept_id})
    return (data.get("result") or {}).get("userid_list", []) or []
