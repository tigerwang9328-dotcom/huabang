"""LifeData collector maintenance jobs."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.models.life_data import LifeDataCapture


logger = logging.getLogger(__name__)

CAPTURE_RETENTION_DAYS = 90


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
