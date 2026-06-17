"""早间老板日报定时任务"""
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


async def run_morning_report():
    """8:30 生成前日日报 + 推送老板"""
    stat_date = (date.today() - timedelta(days=1)).isoformat()
    logger.info(f"[定时] 早间日报开始: {stat_date}")
    try:
        from app.services.report_service import ReportService
        from app.services.dingtalk import DingtalkService
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            svc = ReportService()
            await svc.generate_boss_daily(stat_date, db, force=False)

            dt_svc = DingtalkService(db)
            user_ids = await dt_svc.get_push_user_ids()
            if user_ids:
                result = await dt_svc.send_daily_report(stat_date, user_ids)
                await db.commit()
                logger.info(f"[定时] 日报推送: {result.get('success_count', 0)}/{len(user_ids)}")
            else:
                logger.info("[定时] 无推送目标用户")
    except Exception as e:
        logger.error(f"[定时] 早间日报失败: {e}", exc_info=True)
