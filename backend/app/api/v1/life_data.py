"""Token-authenticated write-only API for life-data captures."""

import hashlib
import hmac
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.life_data import LifeDataIngestRequest, LifeDataIngestResponse
from app.services.life_data_service import LifeDataIngestService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/life-data", tags=["生意经采集"])


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


@router.post("/ingest", response_model=ApiResponse[LifeDataIngestResponse])
async def ingest_life_data(
    body: LifeDataIngestRequest,
    _: None = Depends(verify_collector_token),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LifeDataIngestResponse]:
    """Validate and persist one collector event."""

    if body.account_id != settings.LIFE_DATA_ACCOUNT_ID:
        raise HTTPException(status_code=403, detail="采集账号无权限")

    serialized = json.dumps(
        body.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(serialized) > settings.LIFE_DATA_MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="采集数据超过大小限制")

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
