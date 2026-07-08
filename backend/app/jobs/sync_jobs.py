import logging
import fcntl
from datetime import date, timedelta

logger = logging.getLogger(__name__)

async def run_etl_pipeline(stat_date: str = None):
    """定时触发ETL Pipeline"""
    if not stat_date:
        stat_date = (date.today() - timedelta(days=1)).isoformat()
    try:
        from app.services.etl.pipeline import ETLPipeline
        from app.core.database import AsyncSessionLocal
        pipeline = ETLPipeline()
        async with AsyncSessionLocal() as db:
            result = await pipeline.run_full(stat_date, db)
            logger.info(f"定时ETL完成: {result}")
    except Exception as e:
        logger.error(f"定时ETL失败: {e}", exc_info=True)


async def run_daily_sync():
    """scheduler入口：每日凌晨数据同步+ETL"""
    await run_etl_pipeline()


async def run_dingtalk_approval_sync(days: int = 30):
    """scheduler入口：每日同步钉钉审批数据。

    生产环境使用多个 uvicorn worker，调度器可能在多个进程同时触发；
    这里用非阻塞文件锁保证同一时间只有一个审批同步任务真正执行。
    """
    lock_path = "/tmp/huabang_dingtalk_approval_sync.lock"
    with open(lock_path, "w") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.info("钉钉审批同步已在其他进程执行，本次跳过")
            return {"skipped": True, "reason": "locked"}

        try:
            from app.modules.dingtalk.sync import approvals

            max_api_calls = 100
            logger.info("开始定时同步钉钉审批数据: days=%s max_api_calls=%s", days, max_api_calls)
            result = await approvals.run(days=days, dry_run=False, max_api_calls=max_api_calls)
            logger.info("钉钉审批定时同步完成: %s", result)
            return result
        except Exception as exc:
            logger.error("钉钉审批定时同步失败: %s", exc, exc_info=True)
            return {"error": str(exc)}
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


async def run_dingtalk_attendance_sync(days: int = 1, max_api_calls: int = 12):
    """scheduler入口：同步钉钉考勤数据。

    考勤页需要当天数据多次刷新；使用本地员工表作为 userId 来源，避免每次扫描通讯录。
    每次任务再用文件锁防止多 worker 重复触发消耗钉钉接口。
    """
    lock_path = "/tmp/huabang_dingtalk_attendance_sync.lock"
    with open(lock_path, "w") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.info("钉钉考勤同步已在其他进程执行，本次跳过")
            return {"skipped": True, "reason": "locked"}

        try:
            from app.modules.dingtalk.sync import attendance

            logger.info("开始定时同步钉钉考勤数据: days=%s max_api_calls=%s", days, max_api_calls)
            result = await attendance.run(
                days=days,
                dry_run=False,
                max_api_calls=max_api_calls,
                prefer_local_users=True,
            )
            logger.info("钉钉考勤定时同步完成: %s", result)
            return result
        except Exception as exc:
            logger.error("钉钉考勤定时同步失败: %s", exc, exc_info=True)
            return {"error": str(exc)}
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
