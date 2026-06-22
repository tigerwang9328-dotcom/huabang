"""钉钉 Stream 客户端。

复用 settings.DINGTALK_CLIENT_ID / DINGTALK_CLIENT_SECRET（AppKey / AppSecret），
不在任何地方打印密钥值。注册通用事件 handler，收到事件 -> dispatcher 落库 -> 快速 ACK。
"""
import logging

import dingtalk_stream
from dingtalk_stream import AckMessage

from app.core.config import settings
from app.modules.dingtalk import dispatcher

logger = logging.getLogger("dingtalk.stream")


class DingtalkEventHandler(dingtalk_stream.EventHandler):
    """接收所有钉钉事件 -> 幂等落库 -> 返回 STATUS_OK 快速 ACK（避免重复投递）。"""

    async def process(self, event: dingtalk_stream.EventMessage):
        hdr = event.headers
        topic = getattr(hdr, "topic", None)
        # 组装完整原始事件：头部规范字段 + 业务数据，整体存档
        payload = {
            "eventId": getattr(hdr, "event_id", None),
            "eventType": getattr(hdr, "event_type", None),
            "eventCorpId": getattr(hdr, "event_corp_id", None),
            "eventBornTime": getattr(hdr, "event_born_time", None),
            "eventUnifiedAppId": getattr(hdr, "event_unified_app_id", None),
            "data": getattr(event, "data", None),
        }
        try:
            await dispatcher.dispatch_event(payload, topic)
        except Exception:
            logger.exception(
                "处理钉钉事件失败 event_id=%s type=%s topic=%s",
                payload.get("eventId"), payload.get("eventType"), topic,
            )
        return AckMessage.STATUS_OK, "OK"


def build_client() -> dingtalk_stream.DingTalkStreamClient:
    """构建并返回已注册 handler 的 Stream 客户端。缺凭证时抛清晰错误（不含真实值）。"""
    client_id = settings.DINGTALK_CLIENT_ID
    client_secret = settings.DINGTALK_CLIENT_SECRET
    if not client_id or not client_secret:
        raise RuntimeError("DingTalk Stream credentials missing")

    credential = dingtalk_stream.Credential(client_id, client_secret)
    client = dingtalk_stream.DingTalkStreamClient(credential)
    client.register_all_event_handler(DingtalkEventHandler())
    return client
