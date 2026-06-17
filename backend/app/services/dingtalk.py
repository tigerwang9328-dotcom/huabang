"""钉钉推送服务（工作通知 + 频率限制 + 重试 + 日志）"""
import httpx
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.redis import rate_limit_check
from app.models.log import LogDingtalkPush

logger = logging.getLogger(__name__)

DINGTALK_TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
DINGTALK_SEND_URL = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
DINGTALK_WORK_NOTIFY_URL = "https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2"


class DingtalkService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    async def _get_access_token(self) -> Optional[str]:
        """获取钉钉 access_token（有效期2小时，缓存复用）"""
        if not settings.DINGTALK_CLIENT_ID or not settings.DINGTALK_CLIENT_SECRET:
            logger.warning("钉钉 ClientID/Secret 未配置")
            return None

        now = datetime.now(timezone.utc)
        if self._access_token and self._token_expires_at and now < self._token_expires_at:
            return self._access_token

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    DINGTALK_TOKEN_URL,
                    json={
                        "appKey": settings.DINGTALK_CLIENT_ID,
                        "appSecret": settings.DINGTALK_CLIENT_SECRET,
                    },
                )
                data = resp.json()
                token = data.get("accessToken")
                if token:
                    self._access_token = token
                    expire_in = data.get("expireIn", 7200)
                    from datetime import timedelta
                    self._token_expires_at = now + timedelta(seconds=expire_in - 60)
                    return token
                logger.error(f"获取钉钉token失败: {data}")
                return None
        except Exception as e:
            logger.error(f"钉钉token请求异常: {e}")
            return None

    async def send_work_notification(
        self,
        user_id_list: list[str],
        title: str,
        content: str,
        push_type: str = "daily_report",
        template_code: str = "",
    ) -> dict:
        """发送钉钉工作通知"""
        if not settings.DINGTALK_PUSH_ENABLED:
            logger.info(f"钉钉推送已关闭 (DINGTALK_PUSH_ENABLED=false), 跳过: {title}")
            return {"success": False, "skipped": True, "reason": "推送开关未开启"}

        results = []
        for user_id in user_id_list:
            result = await self._send_to_user(user_id, title, content, push_type, template_code)
            results.append(result)

        success_count = sum(1 for r in results if r.get("success"))
        return {
            "success": success_count > 0,
            "total": len(user_id_list),
            "success_count": success_count,
            "results": results,
        }

    async def _send_to_user(
        self,
        user_id: str,
        title: str,
        content: str,
        push_type: str,
        template_code: str,
    ) -> dict:
        # 频率限制：同类型消息同一用户1小时最多N次
        rate_key = f"dingtalk_push:{user_id}:{push_type}"
        allowed = await rate_limit_check(
            rate_key,
            max_count=settings.DINGTALK_MAX_PUSH_PER_HOUR,
            window_seconds=3600,
        )

        log = LogDingtalkPush(
            push_type=push_type,
            target_user_id=user_id,
            template_code=template_code,
            message_title=title,
            message_content=content[:500],  # 只存前500字符
        )

        if not allowed:
            log.status = "skipped"
            log.is_rate_limited = True
            log.error_message = "频率限制，本小时内已推送过"
            self.db.add(log)
            return {"success": False, "user_id": user_id, "reason": "频率限制"}

        token = await self._get_access_token()
        if not token:
            log.status = "failed"
            log.error_message = "无法获取access_token"
            self.db.add(log)
            return {"success": False, "user_id": user_id, "reason": "token获取失败"}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    DINGTALK_WORK_NOTIFY_URL,
                    params={"access_token": token},
                    json={
                        "agent_id": settings.DINGTALK_AGENT_ID,
                        "userid_list": user_id,
                        "msg": {
                            "msgtype": "markdown",
                            "markdown": {
                                "title": title,
                                "text": content,
                            },
                        },
                    },
                )
                resp_data = resp.json()
                log.dingtalk_response = str(resp_data)

                if resp_data.get("errcode", -1) == 0:
                    log.status = "success"
                    self.db.add(log)
                    return {"success": True, "user_id": user_id}
                else:
                    log.status = "failed"
                    log.error_message = f"errcode:{resp_data.get(errcode)} {resp_data.get(errmsg)}"
                    self.db.add(log)
                    return {"success": False, "user_id": user_id, "error": log.error_message}

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            self.db.add(log)
            logger.error(f"钉钉推送异常 user:{user_id}: {e}")
            return {"success": False, "user_id": user_id, "error": str(e)}

    async def send_test_message(self, user_id: str) -> dict:
        """测试推送"""
        return await self._send_to_user(
            user_id=user_id,
            title="华邦AI中台 - 测试推送",
            content="## 测试消息\n\n这是华邦AI中台的测试推送消息，如收到请忽略。\n\n---\n*发送时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "*",
            push_type="test",
            template_code="test",
        )
