"""Scheduled command-center health monitor."""

import logging

from app.core.database import AsyncSessionLocal
from app.services.command_center_health_service import monitor_command_center_health


logger = logging.getLogger(__name__)


async def run_command_center_health_monitor() -> dict:
    async with AsyncSessionLocal() as db:
        try:
            result = await monitor_command_center_health(db)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("经营指挥台每日健康检查失败")
            raise
    logger.info("经营指挥台每日健康检查完成: %s", result)
    return result
