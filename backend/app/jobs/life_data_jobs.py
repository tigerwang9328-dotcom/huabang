"""LifeData collector maintenance jobs."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, update

from app.core.database import AsyncSessionLocal
from app.models.life_data import LifeDataCapture, LifeDataCollectorState


logger = logging.getLogger(__name__)

CAPTURE_RETENTION_DAYS = 90
COLLECTOR_OFFLINE_AFTER_MINUTES = 15


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def cleanup_life_data_captures() -> int:
    """Delete raw captures older than the retention window."""
    cutoff = _utc_now() - timedelta(days=CAPTURE_RETENTION_DAYS)

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                delete(LifeDataCapture).where(LifeDataCapture.created_at < cutoff)
            )
            deleted_count = result.rowcount or 0
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("LifeData原始采集数据清理失败")
            raise

    logger.info(
        "LifeData原始采集数据清理完成: cutoff=%s deleted=%d",
        cutoff.isoformat(),
        deleted_count,
    )
    return deleted_count


async def mark_stale_life_data_collectors_offline() -> int:
    """Mark collectors offline after 15 minutes without a server heartbeat."""

    now = _utc_now()
    cutoff = now - timedelta(minutes=COLLECTOR_OFFLINE_AFTER_MINUTES)
    statement = (
        update(LifeDataCollectorState)
        .where(
            LifeDataCollectorState.last_seen_at < cutoff,
            LifeDataCollectorState.status != "offline",
        )
        .values(status="offline", updated_at=now)
    )

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(statement)
            updated_count = result.rowcount or 0
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("LifeData采集器离线状态检查失败")
            raise

    logger.info(
        "LifeData采集器离线状态检查完成: cutoff=%s updated=%d",
        cutoff.isoformat(),
        updated_count,
    )
    return updated_count
