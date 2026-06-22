"""钉钉 Stream 入站事件原始存档表。

仅做原始事件落库（幂等去重 + 原文留底），不做业务解析。
"""
from sqlalchemy import Column, String, BigInteger, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class DingtalkEvent(Base):
    """钉钉 Stream 事件原始记录。"""

    __tablename__ = "dingtalk_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(String(128), unique=True, nullable=True, comment="钉钉 eventId，幂等去重键（可空）")
    event_type = Column(String(128), index=True, nullable=True, comment="事件类型，如 bpms_instance_change")
    corp_id = Column(String(128), nullable=True, comment="企业 corpId")
    event_born_time = Column(BigInteger, nullable=True, comment="事件产生时间(ms)")
    topic = Column(String(128), nullable=True, comment="Stream topic")
    payload = Column(JSONB, nullable=False, comment="完整原始事件数据")
    status = Column(String(32), default="received", index=True, nullable=False, comment="received/processed/failed")
    error_message = Column(Text, nullable=True, comment="处理失败原因")
    processed_at = Column(DateTime(timezone=True), nullable=True, comment="业务处理完成时间")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
