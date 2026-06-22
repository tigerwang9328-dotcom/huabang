"""钉钉事件幂等入库。

从 payload 容错提取 eventId / eventType / corpId / eventBornTime（兼容多种大小写与嵌套），
按 event_id 做幂等插入；event_id 为空也允许落库（不会因唯一约束失败，Postgres 允许多个 NULL）。
完整 payload 原样存入 JSONB。
"""
import logging
from typing import Any, Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.models.dingtalk_event import DingtalkEvent

logger = logging.getLogger("dingtalk.stream")


def _pick(payload: dict, *names: str) -> Optional[Any]:
    """从 payload 顶层及常见嵌套层（header/headers/data）容错取值。"""
    if not isinstance(payload, dict):
        return None
    for n in names:
        v = payload.get(n)
        if v not in (None, ""):
            return v
    for sub in ("header", "headers", "data"):
        d = payload.get(sub)
        if isinstance(d, dict):
            for n in names:
                v = d.get(n)
                if v not in (None, ""):
                    return v
    return None


def _to_int(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


async def save_event(payload: dict, topic: Optional[str] = None) -> bool:
    """幂等写入一条钉钉事件。

    :return: True=新插入；False=已存在（重复，被跳过）。
    """
    event_id = _pick(payload, "eventId", "event_id", "EventId")
    event_type = _pick(payload, "eventType", "event_type", "EventType")
    corp_id = _pick(payload, "corpId", "corp_id", "CorpId", "eventCorpId")
    born_time = _to_int(_pick(payload, "eventBornTime", "event_born_time", "EventBornTime"))

    values = dict(
        event_id=event_id,
        event_type=event_type,
        corp_id=corp_id,
        event_born_time=born_time,
        topic=topic,
        payload=payload if isinstance(payload, dict) else {"raw": payload},
        status="received",
    )
    async with AsyncSessionLocal() as session:
        try:
            stmt = pg_insert(DingtalkEvent).values(**values)
            if event_id:
                stmt = stmt.on_conflict_do_nothing(index_elements=["event_id"])
            result = await session.execute(stmt)
            await session.commit()
            return (result.rowcount or 0) > 0
        except Exception:
            await session.rollback()
            raise
