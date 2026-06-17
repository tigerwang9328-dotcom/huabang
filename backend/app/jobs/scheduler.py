"""APScheduler 定时任务调度器"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore
import logging

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(
    jobstores={"default": MemoryJobStore()},
    timezone="Asia/Shanghai",
)


def setup_jobs():
    """注册所有定时任务"""
    from app.jobs.sync_jobs import run_daily_sync
    from app.jobs.report_jobs import run_morning_report
    from app.jobs.push_jobs import run_member_visit_push, run_replenishment_push, run_overdue_reminder
    from app.jobs.review_jobs import run_evening_diagnosis

    # 每天凌晨1:00 - 同步百盛数据 + ETL
    scheduler.add_job(
        run_daily_sync,
        CronTrigger(hour=1, minute=0),
        id="daily_sync",
        name="每日数据同步+ETL",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # 每天8:30 - 老板经营日报
    scheduler.add_job(
        run_morning_report,
        CronTrigger(hour=8, minute=30),
        id="morning_report",
        name="早间老板日报",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # 每天10:00 - 会员回访名单
    scheduler.add_job(
        run_member_visit_push,
        CronTrigger(hour=10, minute=0),
        id="member_visit",
        name="会员回访名单推送",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # 每天14:00 - 商品补货/调拨提醒
    scheduler.add_job(
        run_replenishment_push,
        CronTrigger(hour=14, minute=0),
        id="replenishment_push",
        name="补货调拨提醒",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # 每天18:00 - 任务逾期提醒
    scheduler.add_job(
        run_overdue_reminder,
        CronTrigger(hour=18, minute=0),
        id="overdue_reminder",
        name="任务逾期提醒",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # 每天21:30 - 门店诊断复查
    scheduler.add_job(
        run_evening_diagnosis,
        CronTrigger(hour=21, minute=30),
        id="evening_diagnosis",
        name="晚间门店诊断",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    logger.info("✅ 定时任务已注册: %d个任务", len(scheduler.get_jobs()))
