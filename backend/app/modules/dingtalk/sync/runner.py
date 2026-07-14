"""钉钉历史数据同步统一入口。

    python -m app.modules.dingtalk.sync.runner employees
    python -m app.modules.dingtalk.sync.runner attendance --days 7
    python -m app.modules.dingtalk.sync.runner approvals --days 30
    python -m app.modules.dingtalk.sync.runner tasks
    python -m app.modules.dingtalk.sync.runner all --days 30
    python -m app.modules.dingtalk.sync.runner all --days 30 --dry-run
"""
import argparse
import asyncio
import logging

from app.core.logger import setup_logging
from app.modules.dingtalk.sync import approvals, attendance, employees
from app.modules.dingtalk.sync._common import quiet_http_logs

logger = logging.getLogger("dingtalk.sync")


async def _run(cmd: str, days: int, dry_run: bool) -> None:
    if cmd in ("employees", "all"):
        logger.info("=== 同步 员工/部门 ===")
        await employees.run(dry_run=dry_run)
    if cmd in ("attendance", "all"):
        logger.info("=== 同步 考勤 (days=%d) ===", days)
        await attendance.run(days=days, dry_run=dry_run)
    if cmd in ("approvals", "all"):
        logger.info("=== 同步 审批/财务 (days=%d) ===", days)
        await approvals.run(days=days, dry_run=dry_run)
    if cmd in ("tasks", "all") and not dry_run:
        logger.info("=== 标记逾期任务并发送优先提醒 ===")
        from app.jobs.push_jobs import run_overdue_reminder
        await run_overdue_reminder()


def main() -> None:
    setup_logging()
    quiet_http_logs()
    parser = argparse.ArgumentParser(description="钉钉历史数据同步")
    parser.add_argument("command", choices=["employees", "attendance", "approvals", "tasks", "all"])
    parser.add_argument("--days", type=int, default=None, help="天数；attendance 默认7，approvals 默认30")
    parser.add_argument("--dry-run", action="store_true", help="只统计不入库")
    args = parser.parse_args()

    days = args.days
    if days is None:
        days = 7 if args.command in ("employees", "attendance") else 30
    asyncio.run(_run(args.command, days, args.dry_run))


if __name__ == "__main__":
    main()
