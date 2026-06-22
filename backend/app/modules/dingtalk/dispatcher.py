"""事件分发。

MVP 阶段仅调用 repository.save_event 做原始落库，不做业务解析。
日志只输出 event_type / event_id / topic，不输出敏感字段。
"""
import logging
from typing import Optional

from app.modules.dingtalk import repository

logger = logging.getLogger("dingtalk.stream")


async def dispatch_event(payload: dict, topic: Optional[str] = None) -> bool:
    """分发一条钉钉事件，返回是否为新插入。"""
    event_id = event_type = None
    if isinstance(payload, dict):
        event_id = payload.get("eventId") or payload.get("event_id")
        event_type = payload.get("eventType") or payload.get("event_type")

    inserted = await repository.save_event(payload, topic=topic)
    logger.info(
        "dingtalk event dispatched type=%s event_id=%s topic=%s inserted=%s",
        event_type, event_id, topic, inserted,
    )
    return inserted
