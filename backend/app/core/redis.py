import redis.asyncio as aioredis
from typing import Optional
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
    return _redis_client


async def check_redis_connection() -> bool:
    try:
        r = await get_redis()
        await r.ping()
        return True
    except Exception as e:
        logger.warning(f"Redis连接失败（非致命，继续运行）: {e}")
        return False


async def rate_limit_check(key: str, max_count: int, window_seconds: int) -> bool:
    """检查频率限制，返回True表示未超限可继续，False表示已超限"""
    try:
        r = await get_redis()
        allowed = await r.eval(
            """
            local count = redis.call('INCR', KEYS[1])
            if count == 1 then
                redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
            end
            if count <= tonumber(ARGV[1]) then
                return 1
            end
            return 0
            """,
            1,
            key,
            max_count,
            window_seconds,
        )
        return bool(allowed)
    except Exception:
        return True  # Redis不可用时放行
