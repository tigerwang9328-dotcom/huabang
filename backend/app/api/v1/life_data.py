"""Token-authenticated write-only API for life-data captures."""

import hashlib
import hmac
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.schemas.common import ApiResponse
from app.schemas.life_data import LifeDataIngestRequest, LifeDataIngestResponse
from app.services.life_data_service import LifeDataIngestService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/life-data", tags=["生意经采集"])

_RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""
_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_REQUESTS = 60


def verify_collector_token(
    x_collector_token: Annotated[
        str | None,
        Header(alias="X-Collector-Token"),
    ] = None,
) -> None:
    """Verify the collector token without storing or logging the raw value."""

    if not x_collector_token:
        raise HTTPException(status_code=401, detail="采集令牌无效")

    digest = hashlib.sha256(x_collector_token.encode()).hexdigest()
    if not settings.LIFE_DATA_COLLECTOR_TOKEN_SHA256:
        raise HTTPException(status_code=503, detail="采集令牌未配置")
    if not hmac.compare_digest(
        digest,
        settings.LIFE_DATA_COLLECTOR_TOKEN_SHA256,
    ):
        raise HTTPException(status_code=401, detail="采集令牌无效")


async def enforce_content_length(request: Request) -> None:
    """Reject oversized raw requests without relying on JSON re-serialization."""

    raw_content_length = request.headers.get("content-length")
    if raw_content_length is not None:
        normalized_length = raw_content_length.strip()
        if not normalized_length.isdecimal():
            raise HTTPException(status_code=400, detail="Content-Length 无效")
        if int(normalized_length) > settings.LIFE_DATA_MAX_PAYLOAD_BYTES:
            raise HTTPException(status_code=413, detail="采集数据超过大小限制")

    raw_body = await request.body()
    if len(raw_body) > settings.LIFE_DATA_MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="采集数据超过大小限制")


async def enforce_collector_rate_limit() -> None:
    """Apply one atomic 60-request/minute limit for the configured account."""

    key = f"rate_limit:life_data_ingest:{settings.LIFE_DATA_ACCOUNT_ID}"
    try:
        redis = await get_redis()
        current = await redis.eval(
            _RATE_LIMIT_SCRIPT,
            1,
            key,
            _RATE_LIMIT_WINDOW_SECONDS,
        )
    except Exception:
        logger.warning("生意经采集限流 Redis 不可用，已降级放行")
        return

    if int(current) > _RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="采集请求过于频繁")


@router.post("/ingest", response_model=ApiResponse[LifeDataIngestResponse])
async def ingest_life_data(
    body: LifeDataIngestRequest,
    _content_length: None = Depends(enforce_content_length),
    _: None = Depends(verify_collector_token),
    _rate_limit: None = Depends(enforce_collector_rate_limit),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LifeDataIngestResponse]:
    """Validate and persist one collector event."""

    if body.account_id != settings.LIFE_DATA_ACCOUNT_ID:
        raise HTTPException(status_code=403, detail="采集账号无权限")

    service = LifeDataIngestService(
        task_creator_id=settings.LIFE_DATA_TASK_CREATOR_ID,
        alert_threshold=2_000,
    )
    result = await service.ingest(db, body)
    data = LifeDataIngestResponse(
        duplicate=result.duplicate,
        videos_seen=result.videos_seen,
        snapshots_created=result.snapshots_created,
        tasks_created=result.tasks_created,
    )
    logger.info(
        "生意经采集完成 event_id=%s account_id=%s endpoint=%s "
        "duplicate=%s videos_seen=%s snapshots_created=%s tasks_created=%s",
        body.event_id,
        body.account_id,
        body.endpoint,
        data.duplicate,
        data.videos_seen,
        data.snapshots_created,
        data.tasks_created,
    )
    return ApiResponse.ok(data=data)
