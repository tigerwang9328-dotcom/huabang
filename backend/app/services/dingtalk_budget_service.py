"""Shared Beijing-day budget for every DingTalk HTTP request."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.redis import get_redis

logger = logging.getLogger("dingtalk.budget")

CST = timezone(timedelta(hours=8))
DINGTALK_DAILY_API_LIMIT = 160
DINGTALK_TASK_RESERVED_CALLS = 20


class DingtalkApiBudgetExceeded(Exception):
    """Raised before a request when its shared daily budget is exhausted."""


def budget_ceiling(priority: str = "normal") -> int:
    if priority == "task":
        return DINGTALK_DAILY_API_LIMIT
    return DINGTALK_DAILY_API_LIMIT - DINGTALK_TASK_RESERVED_CALLS


def _daily_budget_key(now: Optional[datetime] = None) -> tuple[str, int, str]:
    current = now or datetime.now(CST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=CST)
    current = current.astimezone(CST)
    budget_date = current.date().isoformat()
    reset_at = datetime.combine(current.date() + timedelta(days=1), datetime.min.time(), tzinfo=CST)
    ttl = max(60, int((reset_at - current).total_seconds()) + 300)
    return f"dingtalk:oapi:daily:{budget_date}", ttl, budget_date


async def consume_daily_dingtalk_budget(
    path: str,
    *,
    category: str = "sync",
    priority: str = "normal",
    now: Optional[datetime] = None,
) -> int:
    """Reserve one actual DingTalk request, preserving the final calls for tasks."""
    key, ttl, _ = _daily_budget_key(now)
    ceiling = budget_ceiling(priority)
    try:
        redis = await get_redis()
        used = int(await redis.incr(key))
        if used == 1:
            await redis.expire(key, ttl)
        if used > ceiling:
            await redis.decr(key)
            raise DingtalkApiBudgetExceeded(
                f"dingtalk daily api budget exhausted for {priority}: {ceiling}/{DINGTALK_DAILY_API_LIMIT}"
            )
        logger.info(
            "DingTalk daily budget used=%s limit=%s category=%s priority=%s path=%s",
            used,
            DINGTALK_DAILY_API_LIMIT,
            category,
            priority,
            path,
        )
        return used
    except DingtalkApiBudgetExceeded:
        raise
    except Exception as exc:
        raise DingtalkApiBudgetExceeded(f"dingtalk daily api budget unavailable: {exc}") from exc


async def record_dingtalk_api_call(
    *,
    path: str,
    category: str,
    priority: str,
    status: str,
    used_after: Optional[int] = None,
    error_message: Optional[str] = None,
    now: Optional[datetime] = None,
) -> None:
    """Persist actual call/denial evidence without breaking the business workflow."""
    _, _, budget_date = _daily_budget_key(now)
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                INSERT INTO log.log_dingtalk_api_call
                    (budget_date, path, category, priority, status, used_after,
                     error_message, requested_at)
                VALUES
                    (CAST(:budget_date AS date), :path, :category, :priority, :status,
                     :used_after, :error_message, now())
            """), {
                "budget_date": budget_date,
                "path": path,
                "category": category,
                "priority": priority,
                "status": status,
                "used_after": used_after,
                "error_message": (error_message or "")[:500] or None,
            })
            await db.commit()
    except Exception:
        logger.exception("Failed to record DingTalk API budget evidence path=%s", path)
