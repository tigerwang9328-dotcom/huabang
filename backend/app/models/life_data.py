"""Persistence models for data collected from life-data.cn."""

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.core.database import Base


class LifeDataCapture(Base):
    __tablename__ = "life_data_capture"
    __table_args__ = (UniqueConstraint("event_id"), {"schema": "app"})

    id = Column(BigInteger, primary_key=True)
    event_id = Column(String(64), nullable=False)
    account_id = Column(String(32), nullable=False, index=True)
    page_path = Column(String(256), nullable=False)
    endpoint = Column(String(256), nullable=False)
    request_payload = Column(JSON, nullable=False)
    response_payload = Column(JSON, nullable=False)
    response_hash = Column(String(64), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LifeDataVideoSnapshot(Base):
    __tablename__ = "life_data_video_snapshot"
    __table_args__ = (
        UniqueConstraint("account_id", "item_id", "metrics_hash"),
        {"schema": "app"},
    )

    id = Column(BigInteger, primary_key=True)
    account_id = Column(String(32), nullable=False, index=True)
    item_id = Column(String(96), nullable=False, index=True)
    title = Column(Text, nullable=False)
    author_id = Column(String(64))
    author_name = Column(String(128))
    published_at = Column(DateTime(timezone=True))
    stat_start = Column(Date, nullable=False)
    stat_end = Column(Date, nullable=False)
    play_count = Column(BigInteger, nullable=False, default=0)
    pay_gmv_fen = Column(BigInteger, nullable=False, default=0)
    verify_gmv_fen = Column(BigInteger, nullable=False, default=0)
    refund_gmv_fen = Column(BigInteger, nullable=False, default=0)
    metrics_hash = Column(String(64), nullable=False)
    metrics = Column(JSON, nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)


class LifeDataAlertEvent(Base):
    __tablename__ = "life_data_alert_event"
    __table_args__ = (
        UniqueConstraint("account_id", "item_id", "rule_code"),
        {"schema": "app"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(String(32), nullable=False)
    item_id = Column(String(96), nullable=False)
    rule_code = Column(String(64), nullable=False)
    snapshot_id = Column(BigInteger)
    task_id = Column(BigInteger)
    play_count = Column(BigInteger, nullable=False)
    triggered_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LifeDataCollectorState(Base):
    __tablename__ = "life_data_collector_state"
    __table_args__ = {"schema": "app"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(String(32), nullable=False, unique=True)
    status = Column(String(16), nullable=False, default="offline")
    last_seen_at = Column(DateTime(timezone=True))
    last_success_at = Column(DateTime(timezone=True))
    last_error_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    last_event_id = Column(String(64))
    queue_depth = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
