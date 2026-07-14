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
    from app.jobs.sync_jobs import run_daily_sync, run_dingtalk_approval_sync, run_dingtalk_attendance_sync
    from app.jobs.report_jobs import run_morning_report
    from app.jobs.push_jobs import (
        run_member_visit_push,
        run_overdue_reminder,
        run_replenishment_push,
        run_task_assignment_notifications,
    )
    from app.jobs.review_jobs import run_evening_diagnosis
    from app.jobs.life_data_jobs import (
        cleanup_life_data_captures,
        mark_stale_life_data_collectors_offline,
    )
    from app.jobs.command_center_health_jobs import run_command_center_health_monitor

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

    # 每天06:40 - 核对04:00销售/退货、05:30库存和06:30经营快照。
    # 异常只生成待人工确认的幂等任务草稿，不依赖钉钉开关。
    scheduler.add_job(
        run_command_center_health_monitor,
        CronTrigger(hour=6, minute=40, timezone="Asia/Shanghai"),
        id="command_center_health_monitor",
        name="经营指挥台每日健康检查",
        replace_existing=True,
        misfire_grace_time=1800,
        coalesce=True,
        max_instances=1,
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

    # 每天12:00 - 钉钉审批数据同步（考勤模块审批中心）
    scheduler.add_job(
        run_dingtalk_approval_sync,
        CronTrigger(hour=12, minute=0),
        id="dingtalk_approval_sync",
        name="钉钉审批同步",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
    )

    # 每天9/13/18/23点 - 钉钉考勤数据同步
    # API预算：考勤 4 * 12 = 48 次/天；审批 100 次/天；全局限额仍为160次/天。
    scheduler.add_job(
        run_dingtalk_attendance_sync,
        CronTrigger(hour="9,13,18,23", minute=5),
        id="dingtalk_attendance_sync",
        name="钉钉考勤同步",
        replace_existing=True,
        misfire_grace_time=1800,
        coalesce=True,
        max_instances=1,
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

    # 每分钟清空任务通知队列；API进程中断后也不会丢失已派发通知。
    scheduler.add_job(
        run_task_assignment_notifications,
        CronTrigger(minute="*"),
        id="task_assignment_notifications",
        name="任务通知队列",
        replace_existing=True,
        misfire_grace_time=60,
        coalesce=True,
        max_instances=1,
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

    # 每天03:20 - 清理超过90天的LifeData原始采集数据
    scheduler.add_job(
        cleanup_life_data_captures,
        CronTrigger(hour=3, minute=20, timezone="Asia/Shanghai"),
        id="life_data_capture_cleanup",
        name="LifeData原始采集数据清理",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
    )

    # 每5分钟检查采集器心跳，超过15分钟未上报即标记离线
    scheduler.add_job(
        mark_stale_life_data_collectors_offline,
        CronTrigger(minute="*/5", timezone="Asia/Shanghai"),
        id="life_data_collector_offline",
        name="LifeData采集器离线检查",
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
        max_instances=1,
    )

    logger.info("✅ 定时任务已注册: %d个任务", len(scheduler.get_jobs()))
