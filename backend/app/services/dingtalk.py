"""钉钉推送服务（工作通知 + 频率限制 + 指数退避重试 + 日志）"""
import asyncio
import httpx
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.redis import rate_limit_check
from app.models.log import LogDingtalkPush

logger = logging.getLogger(__name__)

DINGTALK_TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
DINGTALK_SEND_URL = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
DINGTALK_WORK_NOTIFY_URL = "https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2"

MAX_RETRY = 3
RETRY_DELAYS = [2, 5, 15]  # 秒，指数退避


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

        for attempt in range(MAX_RETRY):
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
                        self._token_expires_at = now + timedelta(seconds=expire_in - 60)
                        return token
                    logger.error(f"获取钉钉token失败: {data}")
                    return None
            except Exception as e:
                if attempt < MAX_RETRY - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(f"钉钉token请求异常(第{attempt+1}次)，{delay}s后重试: {e}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"钉钉token请求最终失败: {e}")
                    return None
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
            logger.info(f"钉钉推送已关闭，跳过: {title}")
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
            message_content=content[:500],
        )

        if not allowed:
            log.status = "skipped"
            log.is_rate_limited = True
            log.error_message = "频率限制，本小时内已推送过"
            self.db.add(log)
            return {"success": False, "user_id": user_id, "reason": "频率限制"}

        # 指数退避重试
        last_error = ""
        for attempt in range(MAX_RETRY):
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
                    log.retry_count = attempt

                    if resp_data.get("errcode", -1) == 0:
                        log.status = "success"
                        self.db.add(log)
                        return {"success": True, "user_id": user_id, "attempt": attempt + 1}
                    else:
                        last_error = f"errcode:{resp_data.get('errcode')} {resp_data.get('errmsg')}"
                        # errcode=88 是token过期，重置token后重试
                        if resp_data.get("errcode") in (88, 40001):
                            self._access_token = None

                        if attempt < MAX_RETRY - 1:
                            delay = RETRY_DELAYS[attempt]
                            logger.warning(f"钉钉推送失败(第{attempt+1}次)，{delay}s后重试: {last_error}")
                            await asyncio.sleep(delay)

            except Exception as e:
                last_error = str(e)
                if attempt < MAX_RETRY - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(f"钉钉推送异常(第{attempt+1}次)，{delay}s后重试: {e}")
                    await asyncio.sleep(delay)

        log.status = "failed"
        log.error_message = last_error
        log.retry_count = MAX_RETRY
        self.db.add(log)
        logger.error(f"钉钉推送最终失败 user:{user_id}: {last_error}")
        return {"success": False, "user_id": user_id, "error": last_error}

    async def send_test_message(self, user_id: str) -> dict:
        """测试推送"""
        return await self._send_to_user(
            user_id=user_id,
            title="华邦AI中台 - 测试推送",
            content="## 测试消息\n\n这是华邦AI中台的测试推送消息，如收到请忽略。\n\n---\n*发送时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "*",
            push_type="test",
            template_code="test",
        )

    async def send_daily_report(self, stat_date: str, user_id_list: list[str]) -> dict:
        """发送老板日报（自动从DB读数据，生成Markdown）"""
        from sqlalchemy import text
        from datetime import date

        d = date.fromisoformat(stat_date)
        r = await self.db.execute(text("""
            SELECT total_sales, offline_sales, online_sales, order_count,
                   avg_order_value, gross_margin, total_inventory_amount,
                   age_90_plus_amount, cash_safety_days, exception_count,
                   ai_summary, ai_today_focus, ai_risk_summary
            FROM dm.dm_boss_daily_report WHERE report_date = :d
        """), {"d": d})
        row = r.fetchone()

        if not row:
            return {"success": False, "reason": f"{stat_date}日报数据未生成"}

        total_sales = float(row[0] or 0)
        offline_sales = float(row[1] or 0)
        online_sales = float(row[2] or 0)
        order_count = int(row[3] or 0)
        aov = float(row[4] or 0)
        margin = float(row[5] or 0) * 100
        inventory = float(row[6] or 0)
        age_90_plus = float(row[7] or 0)
        cash_days = int(row[8] or 0)
        exception_count = int(row[9] or 0)
        ai_summary = row[10] or "(暂无AI摘要)"
        today_focus = row[11] or ""
        risk_summary = row[12] or ""

        content = f"""## 华邦服饰 {stat_date} 经营日报

**📊 今日销售**
- 总销售额：**{total_sales:,.0f}元**（线下{offline_sales:,.0f} | 线上{online_sales:,.0f}）
- 订单{order_count}单，客单价{aov:.0f}元，毛利率{margin:.1f}%

**📦 库存状况**
- 库存总额：{inventory:,.0f}元（90天+滞销：{age_90_plus:,.0f}元）

**💰 资金安全**
- 现金安全天数：{cash_days if cash_days < 9999 else '暂无数据'}天
- 当日预警：{exception_count}条

**🤖 AI摘要**
{ai_summary}
"""
        if today_focus:
            content += f"\n**📌 今日重点**\n{today_focus}\n"
        if risk_summary:
            content += f"\n**⚠️ 风险提示**\n{risk_summary}\n"

        content += f"\n---\n*华邦AI中台 · {datetime.now().strftime('%H:%M')}*"

        return await self.send_work_notification(
            user_id_list=user_id_list,
            title=f"华邦 {stat_date} 经营日报",
            content=content,
            push_type="daily_report",
            template_code="daily_report",
        )

    async def get_push_user_ids(self, role_filter: Optional[str] = None) -> list[str]:
        """获取启用推送的用户钉钉ID列表"""
        from sqlalchemy import text
        r = await self.db.execute(text("""
            SELECT u.dingtalk_user_id
            FROM sys.sys_user u
            WHERE u.dingtalk_user_id IS NOT NULL
              AND u.is_active = TRUE
              AND u.push_enabled = TRUE
        """))
        return [row[0] for row in r.fetchall() if row[0]]
