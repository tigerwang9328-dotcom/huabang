"""Authenticated ingest API for the frozen Douyin color analysis v3.1 contract."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import secrets
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission, require_any_permission
from app.core.config import settings
from app.core.database import get_db
from app.models.douyin_color_analytics import (
    CalculationJob,
    CollectionBatch,
    CollectionBatchPart,
    CollectionItem,
    CollectorEvent,
    CollectorExpectedSchedule,
    CollectorInstance,
    DouyinCreatorAccount,
    DouyinUploadToken,
    GarmentStyle,
    OutfitColorMetric,
    OutfitCombination,
    ReleaseStageConfiguration,
    Video,
    VideoAnalysisSnapshot,
    VideoClip,
    VideoColorMetric,
)
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.schemas.douyin_color_analytics import BatchPartEnvelope, CollectorEventRequest, CollectorHeartbeatRequest
from app.services.douyin_color_ingest_service import (
    IngestProtocolError,
    batch_is_expired,
    compute_batch_hash,
    canonical_snapshot_hash,
    response_snapshot_hash,
    summarize_item_statuses,
    derive_collector_status,
    expand_collection_record,
    is_expected_online,
    normalize_analysis_response,
    validate_part_contract,
    validate_part_number,
    whitelist_raw_response,
)
from app.services.douyin_color_security_service import (
    DouyinPayloadSecurityError,
    decode_gzip_json,
    hash_upload_token,
    creator_fingerprint,
    validate_collector_metadata,
    validate_gzip_content_encoding,
    validate_observed_creator,
    validate_payload_safety,
    validate_schema_version,
    sanitize_douyin_text,
    read_bounded_body,
)
from app.services.douyin_color_annotation_service import (
    AnnotationConflictError,
    AnnotationPermissionError,
    resolve_single_active_account,
)
from app.services.douyin_color_report_query_service import (
    export_rankings,
    query_outfit_rankings,
    query_single_garment_rankings,
)
from app.services.douyin_color_release_service import (
    advance_stage,
    can_enable_bounce_report,
    disable_bounce_report,
    enable_bounce_report,
)
from app.services.douyin_color_metrics_service import (
    compute_outfit_metric,
    compute_video_color_metric,
    select_bounce_snapshot,
    select_retention_snapshot,
)
from app.services.operation_audit_service import write_operation_audit


router = APIRouter(prefix="/douyin-color-analytics", tags=["抖音颜色分析"])
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_MAX_COMPRESSED_UPLOAD_BYTES = 1 * 1024 * 1024
_MINIMUM_SCRIPT_VERSION = "3.1.0"


# ---------------------------------------------------------------------------
# Permission role registry — maps each Douyin role to its granted permission
# codes.  ``douyin.admin`` is the superset; ``douyin.viewer`` is the minimal
# read-only grant every role inherits.
# ---------------------------------------------------------------------------

DOUYIN_PERMISSION_CODES = frozenset({
    "douyin.admin",
    "douyin.auditor",
    "douyin.operator",
    "douyin.annotator",
    "douyin.analyst",
    "douyin.viewer",
    "douyin.annotation.edit",
    "douyin.annotation.approve",
})

DOUYIN_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "douyin.admin": set(DOUYIN_PERMISSION_CODES),
    "douyin.auditor": {"douyin.auditor", "douyin.viewer"},
    "douyin.operator": {"douyin.operator", "douyin.viewer"},
    "douyin.annotator": {"douyin.annotator", "douyin.annotation.edit", "douyin.viewer"},
    "douyin.analyst": {"douyin.analyst", "douyin.viewer"},
    "douyin.viewer": {"douyin.viewer"},
}



def collector_config_payload(*, account_key: str) -> dict[str, object]:
    """Return the versioned, non-sensitive collector control-plane contract."""
    return {
        "account_key": account_key,
        "schema_version": 1,
        "supported_schema_versions": [1],
        "minimum_script_version": _MINIMUM_SCRIPT_VERSION,
        "recommended_script_version": _MINIMUM_SCRIPT_VERSION,
        "collection_enabled": settings.DOUYIN_COLOR_COLLECTION_ENABLED,
        "max_part_records": 50,
        "max_part_uncompressed_bytes": _MAX_UPLOAD_BYTES,
        "max_local_batches": 100,
        "max_local_bytes": 500 * 1024 * 1024,
        "global_start_interval_ms": 1000,
        "max_in_flight_requests": 2,
        "batch_expiry_hours": 24,
    }


class CreatorAccountCreateRequest(BaseModel):
    account_key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    observed_creator_id: str = Field(min_length=1, max_length=128)
    expected_account_name: str | None = Field(default=None, max_length=128)
    status: str = Field(default="preconfigured", pattern="^(preconfigured|inactive|active|disabled)$")


class UploadTokenIssueRequest(BaseModel):
    expires_in_days: int = Field(default=30, ge=1, le=365)


class CollectorExpectedScheduleRequest(BaseModel):
    weekday_mask: int = Field(ge=1, le=127)
    expected_start_local: time
    expected_end_local: time
    timezone: str = Field(default="Asia/Shanghai", pattern="^Asia/Shanghai$")
    enabled: bool = True


async def _collector_account(
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)
) -> DouyinCreatorAccount:
    """Resolve a short-lived collector token without ever persisting its plaintext."""

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="collector_token_invalid")
    token_value = authorization.removeprefix("Bearer ").strip()
    if not token_value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="collector_token_invalid")
    result = await db.execute(
        select(DouyinUploadToken, DouyinCreatorAccount)
        .join(DouyinCreatorAccount, DouyinCreatorAccount.id == DouyinUploadToken.account_id)
        .where(DouyinUploadToken.token_hash == hash_upload_token(token_value))
    )
    pair = result.one_or_none()
    if pair is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="collector_token_invalid")
    token, account = pair
    now = datetime.now(timezone.utc)
    if token.status != "active" or account.status != "active" or (token.expires_at and token.expires_at <= now):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="collector_token_invalid")
    token.last_used_at = now
    return account


def _bad_payload(error: DouyinPayloadSecurityError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error).split(":", 1)[0])


def _expired_batch_response() -> JSONResponse:
    """Return a 409 without raising, so get_db commits the state transition."""

    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=ApiResponse.fail("batch_expired", code=409).model_dump())


async def _insert_or_select_by_unique(
    *, db: AsyncSession, model: type, values: dict[str, object], lookup
) -> tuple[object | None, bool]:
    """Use the database unique index as the concurrency arbiter, then return its winner."""

    inserted_id = (await db.execute(
        pg_insert(model).values(**values).on_conflict_do_nothing().returning(model.id)
    )).scalar_one_or_none()
    if inserted_id is not None:
        return await db.get(model, inserted_id), True
    return (await db.execute(select(model).where(*lookup))).scalar_one_or_none(), False


async def _materialize_record(
    *, db: AsyncSession, account_id: int, batch: CollectionBatch, part: CollectionBatchPart, record: dict[str, object]
) -> tuple[str, bool]:
    """Create an auditable collection-item reference, reusing content-identical snapshots."""

    record_hash = canonical_snapshot_hash(record)
    video_id_string = str(record["video_id"])
    direct_status = record.get("item_status")
    if direct_status == "skipped_non_video":
        item, item_created = await _insert_or_select_by_unique(
            db=db,
            model=CollectionItem,
            values={
                "account_id": account_id, "batch_id": batch.id, "part_id": part.id,
                "video_id_string": video_id_string, "item_status": "skipped_non_video",
                "error_category": str(record.get("error_category")), "raw_record_hash": record_hash,
            },
            lookup=[CollectionItem.part_id == part.id, CollectionItem.raw_record_hash == record_hash],
        )
        if item is None:
            raise RuntimeError("collection_item_insert_conflict_unresolved")
        return str(item.item_status), item_created
    now = datetime.now(timezone.utc)
    published_at = None
    if isinstance(record.get("published_at_epoch_seconds"), int):
        published_at = datetime.fromtimestamp(int(record["published_at_epoch_seconds"]), tz=timezone.utc)
    sanitized_title = record.get("sanitized_title")
    video, _ = await _insert_or_select_by_unique(
        db=db,
        model=Video,
        values={
            "account_id": account_id, "video_id_string": video_id_string,
            "title": sanitize_douyin_text(sanitized_title if isinstance(sanitized_title, str) else None),
            "published_at": published_at, "duration_ms": record.get("duration_ms"),
            "creator_detail_path": f"/creator-micro/work-management/work-detail/{video_id_string}",
            "source_type": "video", "first_collected_at": now, "last_collected_at": now,
            "collection_status": "pending",
        },
        lookup=[Video.account_id == account_id, Video.video_id_string == video_id_string],
    )
    if video is None:
        raise RuntimeError("video_insert_conflict_unresolved")
    video.last_collected_at = now
    # Backfill NULL fields when re-collecting an existing video
    # (on_conflict_do_nothing prevents INSERT update, so we patch here)
    if video.duration_ms is None and record.get("duration_ms") is not None:
        video.duration_ms = record.get("duration_ms")
    if video.published_at is None and published_at is not None:
        video.published_at = published_at
    if not video.title and record.get("sanitized_title"):
        sanitized = record.get("sanitized_title")
        if isinstance(sanitized, str):
            video.title = sanitize_douyin_text(sanitized)
    normalized = normalize_analysis_response(record)
    item_status = str(normalized["item_status"])
    snapshot_id = None
    if item_status in {"success", "empty_curve"}:
        raw_response = whitelist_raw_response(record)
        snapshot_hash = response_snapshot_hash(record)
        snapshot, _ = await _insert_or_select_by_unique(
            db=db,
            model=VideoAnalysisSnapshot,
            values={
                "account_id": account_id, "video_id": video.id, "analysis_type": normalized["analysis_type"],
                "collected_at": now, "source_snapshot_hash": snapshot_hash, "raw_response_json": raw_response,
                "normalized_curve_json": normalized["normalized_curve"], "normalization_version": "v1",
                "original_value_unit": "ratio_or_percent", "curve_quality_status": item_status,
                "observation_window": "ad_hoc", "http_status": record.get("http_status"),
                "business_status_code": record.get("business_status_code"), "first_seen_batch_id": batch.id,
            },
            lookup=[
                VideoAnalysisSnapshot.account_id == account_id,
                VideoAnalysisSnapshot.video_id == video.id,
                VideoAnalysisSnapshot.analysis_type == normalized["analysis_type"],
                VideoAnalysisSnapshot.source_snapshot_hash == snapshot_hash,
            ],
        )
        if snapshot is None:
            raise RuntimeError("snapshot_insert_conflict_unresolved")
        snapshot_id = snapshot.id
    item, item_created = await _insert_or_select_by_unique(
        db=db,
        model=CollectionItem,
        values={
            "account_id": account_id, "batch_id": batch.id, "part_id": part.id,
            "video_id_string": video_id_string, "analysis_type": normalized["analysis_type"],
            "item_status": item_status, "http_status": record.get("http_status"),
            "business_status_code": record.get("business_status_code"), "raw_record_hash": record_hash,
            "snapshot_id": snapshot_id,
        },
        lookup=[CollectionItem.part_id == part.id, CollectionItem.raw_record_hash == record_hash],
    )
    if item is None:
        raise RuntimeError("collection_item_insert_conflict_unresolved")
    return str(item.item_status), item_created


@router.get("/collector-config", response_model=ApiResponse)
async def collector_config(account: DouyinCreatorAccount = Depends(_collector_account)):
    return ApiResponse.ok(collector_config_payload(account_key=account.account_key))


@router.post("/collector-heartbeats", response_model=ApiResponse)
async def collector_heartbeat(
    payload: CollectorHeartbeatRequest,
    account: DouyinCreatorAccount = Depends(_collector_account),
    db: AsyncSession = Depends(get_db),
):
    try:
        validate_collector_metadata(
            script_version=payload.script_version,
            minimum_script_version=_MINIMUM_SCRIPT_VERSION,
            current_page_path=payload.current_page_path,
        )
        validate_schema_version(schema_version=payload.schema_version, supported_versions={1})
        if payload.observed_creator_id:
            validate_observed_creator(
                expected_fingerprint=account.expected_creator_fingerprint,
                observed_creator_id=payload.observed_creator_id,
            )
    except DouyinPayloadSecurityError as error:
        raise _bad_payload(error) from None
    now = datetime.now(timezone.utc)
    schedules = (await db.execute(select(CollectorExpectedSchedule).where(
        CollectorExpectedSchedule.account_id == account.id,
        CollectorExpectedSchedule.enabled.is_(True),
    ))).scalars().all()
    local_now = now.astimezone(ZoneInfo("Asia/Shanghai"))
    expected_online = is_expected_online(
        now_local=local_now,
        schedules=[{"weekday_mask": schedule.weekday_mask, "start": schedule.expected_start_local,
                    "end": schedule.expected_end_local} for schedule in schedules],
    ) if schedules else time(9) <= local_now.time().replace(tzinfo=None) < time(18)
    collector_status = derive_collector_status(
        last_heartbeat_at=now, now=now, expected_online=expected_online,
        document_visibility=payload.document_visibility, auth_failed=False,
        upload_blocked=False, suspended=bool(payload.drift_ms and abs(payload.drift_ms) > 120_000),
    )
    fields = {
        "script_version": payload.script_version, "schema_version": payload.schema_version,
        "last_heartbeat_at": now, "current_status": collector_status,
        "current_page_path": payload.current_page_path, "current_page_type": payload.current_page_type,
        "document_visibility": payload.document_visibility, "queued_batch_count": payload.queued_batch_count,
        "queued_bytes": payload.queued_bytes, "observed_creator_fingerprint": (
            account.expected_creator_fingerprint if payload.observed_creator_id else None
        ), "observed_account_name": sanitize_douyin_text(payload.observed_account_name),
    }
    collector, collector_created = await _insert_or_select_by_unique(
        db=db,
        model=CollectorInstance,
        values={"account_id": account.id, "installation_id": payload.installation_id, **fields},
        lookup=[
            CollectorInstance.account_id == account.id,
            CollectorInstance.installation_id == payload.installation_id,
        ],
    )
    if collector is None:
        raise RuntimeError("collector_insert_conflict_unresolved")
    if not collector_created:
        for field, value in fields.items():
            setattr(collector, field, value)
    return ApiResponse.ok({"status": collector_status})


@router.post("/collector-events", response_model=ApiResponse)
async def collector_event(
    payload: CollectorEventRequest,
    account: DouyinCreatorAccount = Depends(_collector_account),
    db: AsyncSession = Depends(get_db),
):
    collector = (await db.execute(select(CollectorInstance).where(
        CollectorInstance.account_id == account.id,
        CollectorInstance.installation_id == payload.installation_id,
    ))).scalar_one_or_none()
    db.add(CollectorEvent(
        account_id=account.id, collector_instance_id=collector.id if collector else None,
        installation_id=payload.installation_id, event_type=payload.event_type,
        occurred_at=payload.occurred_at, error_category=payload.error_category,
        endpoint_name=payload.endpoint_name, http_status=payload.http_status,
        business_status_code=payload.business_status_code, retry_count=payload.retry_count,
        sanitized_message=sanitize_douyin_text(payload.message),
    ))
    if collector and payload.error_category:
        collector.last_error_category = payload.error_category
    return ApiResponse.ok({"accepted": True})


@router.post("/collection-batches/{client_batch_id}/parts", response_model=ApiResponse)
async def upload_part(
    client_batch_id: str,
    request: Request,
    account: DouyinCreatorAccount = Depends(_collector_account),
    db: AsyncSession = Depends(get_db),
):
    try:
        validate_gzip_content_encoding(request.headers.get("content-encoding"))
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > _MAX_COMPRESSED_UPLOAD_BYTES:
            raise DouyinPayloadSecurityError("compressed_payload_too_large")
        body = await read_bounded_body(request.stream(), max_bytes=_MAX_COMPRESSED_UPLOAD_BYTES)
        raw = decode_gzip_json(body, max_uncompressed_bytes=_MAX_UPLOAD_BYTES)
        validate_payload_safety(raw)
        payload = BatchPartEnvelope.model_validate(raw)
        if payload.client_batch_id != client_batch_id:
            raise DouyinPayloadSecurityError("client_batch_id_mismatch")
        validate_collector_metadata(
            script_version=payload.script_version,
            minimum_script_version=_MINIMUM_SCRIPT_VERSION,
            current_page_path="/creator-micro/data-center/content",
        )
        validate_schema_version(schema_version=payload.schema_version, supported_versions={1})
        validate_observed_creator(
            expected_fingerprint=account.expected_creator_fingerprint,
            observed_creator_id=payload.observed_creator_id,
        )
    except DouyinPayloadSecurityError as error:
        raise _bad_payload(error) from None
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_payload") from None

    try:
        validate_part_number(part_number=payload.part_number, part_count=payload.part_count)
    except IngestProtocolError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None

    now = datetime.now(timezone.utc)
    batch, _ = await _insert_or_select_by_unique(
        db=db,
        model=CollectionBatch,
        values={
            "account_id": account.id, "client_batch_id": client_batch_id, "schema_version": payload.schema_version,
            "script_version": payload.script_version, "source_date_start": payload.source_date_start,
            "source_date_end": payload.source_date_end, "created_at_client": payload.created_at,
            "expires_at": now + timedelta(hours=24), "part_count": payload.part_count,
            "observed_creator_fingerprint": account.expected_creator_fingerprint,
            "installation_id": payload.installation_id,
        },
        lookup=[CollectionBatch.account_id == account.id, CollectionBatch.client_batch_id == client_batch_id],
    )
    if batch is None:
        raise RuntimeError("batch_insert_conflict_unresolved")
    if batch.status != "receiving":
        raise HTTPException(status_code=409, detail="batch_not_receiving")
    elif batch.expires_at <= now:
        batch.status = "expired"
        return _expired_batch_response()

    try:
        validate_part_contract(
            {
                "account_id": account.id,
                "part_count": batch.part_count,
                "schema_version": batch.schema_version,
                "observed_creator_fingerprint": batch.observed_creator_fingerprint,
                "installation_id": batch.installation_id,
            },
            {
                "account_id": account.id,
                "part_count": payload.part_count,
                "schema_version": payload.schema_version,
                "observed_creator_fingerprint": account.expected_creator_fingerprint,
                "installation_id": payload.installation_id,
                "part_hash": payload.part_hash,
            },
            existing_part_hash=None,
        )
    except IngestProtocolError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None

    part, part_created = await _insert_or_select_by_unique(
        db=db,
        model=CollectionBatchPart,
        values={
            "account_id": account.id, "batch_id": batch.id, "part_number": payload.part_number,
            "part_hash": payload.part_hash, "record_count": len(payload.records), "uncompressed_bytes": len(body),
        },
        lookup=[CollectionBatchPart.batch_id == batch.id, CollectionBatchPart.part_number == payload.part_number],
    )
    if part is None:
        duplicate_hash = (await db.execute(select(CollectionBatchPart.id).where(
            CollectionBatchPart.batch_id == batch.id, CollectionBatchPart.part_hash == payload.part_hash,
        ))).scalar_one_or_none()
        if duplicate_hash is not None:
            raise HTTPException(status_code=409, detail="part_content_conflict")
        raise RuntimeError("part_insert_conflict_unresolved")
    if not part_created:
        if part.part_hash != payload.part_hash:
            raise HTTPException(status_code=409, detail="part_content_conflict")
        return ApiResponse.ok({"idempotent": True, "part_number": payload.part_number})
    statuses: list[str] = []
    newly_materialized_statuses: list[str] = []
    try:
        for input_record in payload.records:
            for expanded_record in expand_collection_record(input_record):
                item_status, item_created = await _materialize_record(
                    db=db, account_id=account.id, batch=batch, part=part, record=expanded_record,
                )
                statuses.append(item_status)
                if item_created:
                    newly_materialized_statuses.append(item_status)
    except IngestProtocolError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    counters = summarize_item_statuses(newly_materialized_statuses)
    await db.execute(update(CollectionBatch).where(
        CollectionBatch.id == batch.id, CollectionBatch.account_id == account.id,
    ).values(
        item_count=CollectionBatch.item_count + counters["item_count"],
        success_count=CollectionBatch.success_count + counters["success_count"],
        skipped_count=CollectionBatch.skipped_count + counters["skipped_count"],
        failure_count=CollectionBatch.failure_count + counters["failure_count"],
        last_part_received_at=now,
    ))
    return ApiResponse.ok({"idempotent": False, "part_number": payload.part_number, "item_statuses": statuses})


@router.get("/collection-batches/{client_batch_id}/missing-parts", response_model=ApiResponse)
async def missing_parts(
    client_batch_id: str, account: DouyinCreatorAccount = Depends(_collector_account), db: AsyncSession = Depends(get_db)
):
    batch = (await db.execute(select(CollectionBatch).where(
        CollectionBatch.account_id == account.id, CollectionBatch.client_batch_id == client_batch_id,
    ))).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="batch_not_found")
    numbers = set((await db.execute(select(CollectionBatchPart.part_number).where(
        CollectionBatchPart.batch_id == batch.id,
    ))).scalars())
    return ApiResponse.ok({"missing_parts": [n for n in range(1, batch.part_count + 1) if n not in numbers]})


@router.get("/collection-batches/{client_batch_id}", response_model=ApiResponse)
async def get_collection_batch(
    client_batch_id: str, account: DouyinCreatorAccount = Depends(_collector_account), db: AsyncSession = Depends(get_db)
):
    batch = (await db.execute(select(CollectionBatch).where(
        CollectionBatch.account_id == account.id, CollectionBatch.client_batch_id == client_batch_id,
    ))).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="batch_not_found")
    items = (await db.execute(select(CollectionItem).where(CollectionItem.batch_id == batch.id))).scalars().all()
    return ApiResponse.ok({
        "client_batch_id": batch.client_batch_id, "status": batch.status, "part_count": batch.part_count,
        "item_count": batch.item_count, "success_count": batch.success_count,
        "skipped_count": batch.skipped_count, "failure_count": batch.failure_count,
        "items": [{"video_id_string": item.video_id_string, "analysis_type": item.analysis_type,
                   "item_status": item.item_status, "snapshot_id": item.snapshot_id} for item in items],
    })


@router.get("/videos/{video_id_string}/analysis-snapshots", response_model=ApiResponse)
async def list_video_analysis_snapshots(
    video_id_string: str,
    account_id: int,
    _: SysUser = Depends(require_permission("douyin.annotation.edit")),
    db: AsyncSession = Depends(get_db),
):
    try:
        account = await resolve_single_active_account(db, account_hint=account_id)
    except AnnotationPermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from None
    except AnnotationConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from None
    video = (await db.execute(select(Video).where(
        Video.account_id == account.id, Video.video_id_string == video_id_string,
    ))).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="video_not_found")
    snapshots = (await db.execute(select(VideoAnalysisSnapshot).where(
        VideoAnalysisSnapshot.account_id == video.account_id, VideoAnalysisSnapshot.video_id == video.id,
    ).order_by(VideoAnalysisSnapshot.collected_at.desc()))).scalars().all()
    return ApiResponse.ok([{
        "id": snapshot.id, "analysis_type": snapshot.analysis_type, "collected_at": snapshot.collected_at,
        "normalized_curve": snapshot.normalized_curve_json, "curve_quality_status": snapshot.curve_quality_status,
        "observation_window": snapshot.observation_window,
    } for snapshot in snapshots])


@router.post("/collection-batches/{client_batch_id}/finalize", response_model=ApiResponse)
async def finalize_batch(
    client_batch_id: str, account: DouyinCreatorAccount = Depends(_collector_account), db: AsyncSession = Depends(get_db)
):
    batch = (await db.execute(select(CollectionBatch).where(
        CollectionBatch.account_id == account.id, CollectionBatch.client_batch_id == client_batch_id,
    ))).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="batch_not_found")
    if batch_is_expired(batch.status, batch.expires_at, datetime.now(timezone.utc)):
        batch.status = "expired"
        return _expired_batch_response()
    parts = (await db.execute(select(CollectionBatchPart.part_number, CollectionBatchPart.part_hash).where(
        CollectionBatchPart.batch_id == batch.id,
    ))).all()
    try:
        batch.batch_hash = compute_batch_hash(parts, expected_part_count=batch.part_count)
    except ValueError:
        raise HTTPException(status_code=409, detail="missing_parts") from None
    batch.status = "completed"
    batch.finalized_at = datetime.now(timezone.utc)
    return ApiResponse.ok({"batch_hash": batch.batch_hash, "status": batch.status})


@router.post("/collection-batches/{client_batch_id}/abandon", response_model=ApiResponse)
async def abandon_batch(
    client_batch_id: str, account: DouyinCreatorAccount = Depends(_collector_account), db: AsyncSession = Depends(get_db)
):
    batch = (await db.execute(select(CollectionBatch).where(
        CollectionBatch.account_id == account.id, CollectionBatch.client_batch_id == client_batch_id,
    ))).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="batch_not_found")
    if batch.status != "receiving":
        raise HTTPException(status_code=409, detail="batch_not_receiving")
    batch.status = "abandoned"
    return ApiResponse.ok({"status": batch.status})


@router.get("/accounts", response_model=ApiResponse)
async def list_accounts(
    _: SysUser = Depends(require_permission("douyin.admin")), db: AsyncSession = Depends(get_db)
):
    accounts = (await db.execute(select(DouyinCreatorAccount).order_by(DouyinCreatorAccount.id))).scalars().all()
    return ApiResponse.ok([{"id": account.id, "account_key": account.account_key, "status": account.status} for account in accounts])


@router.post("/accounts", response_model=ApiResponse)
async def create_account(
    payload: CreatorAccountCreateRequest,
    request: Request,
    current_user: SysUser = Depends(require_permission("douyin.admin")),
    db: AsyncSession = Depends(get_db),
):
    if payload.status == "active":
        active_exists = (await db.execute(select(DouyinCreatorAccount.id).where(
            DouyinCreatorAccount.status == "active",
        ))).scalar_one_or_none()
        if active_exists is not None:
            raise HTTPException(status_code=409, detail="second_active_account_forbidden")
    account = DouyinCreatorAccount(
        account_key=payload.account_key, display_name=sanitize_douyin_text(payload.display_name),
        expected_creator_fingerprint=creator_fingerprint(payload.observed_creator_id),
        expected_account_name=sanitize_douyin_text(payload.expected_account_name), status=payload.status,
    )
    db.add(account)
    await db.flush()
    await write_operation_audit(
        db, actor=current_user, module="douyin_color_analytics", action="create_account",
        target_type="douyin_creator_account", target_id=account.id,
        after_data={"account_key": account.account_key, "status": account.status}, request=request,
    )
    return ApiResponse.ok({"id": account.id, "account_key": account.account_key, "status": account.status})


@router.post("/accounts/{account_id}/upload-tokens", response_model=ApiResponse)
async def issue_upload_token(
    account_id: int,
    payload: UploadTokenIssueRequest,
    request: Request,
    current_user: SysUser = Depends(require_permission("douyin.admin")),
    db: AsyncSession = Depends(get_db),
):
    account = (await db.execute(select(DouyinCreatorAccount).where(
        DouyinCreatorAccount.id == account_id,
    ))).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="account_not_found")
    token_value = f"dyup_{secrets.token_urlsafe(32)}"
    token = DouyinUploadToken(
        account_id=account.id, token_hash=hash_upload_token(token_value), token_prefix=token_value[:12],
        created_by=current_user.id, expires_at=datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days),
    )
    db.add(token)
    await db.flush()
    await write_operation_audit(
        db, actor=current_user, module="douyin_color_analytics", action="issue_upload_token",
        target_type="douyin_upload_token", target_id=token.id,
        after_data={"account_id": account.id, "token_prefix": token.token_prefix, "expires_at": token.expires_at.isoformat()},
        request=request,
    )
    return ApiResponse.ok({"upload_token": token_value, "expires_at": token.expires_at})


@router.post("/accounts/{account_id}/expected-schedules", response_model=ApiResponse)
async def create_expected_schedule(
    account_id: int,
    payload: CollectorExpectedScheduleRequest,
    request: Request,
    current_user: SysUser = Depends(require_permission("douyin.admin")),
    db: AsyncSession = Depends(get_db),
):
    account = (await db.execute(select(DouyinCreatorAccount).where(
        DouyinCreatorAccount.id == account_id,
    ))).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="account_not_found")
    schedule = CollectorExpectedSchedule(
        account_id=account.id, timezone=payload.timezone, weekday_mask=payload.weekday_mask,
        expected_start_local=payload.expected_start_local, expected_end_local=payload.expected_end_local,
        enabled=payload.enabled,
    )
    db.add(schedule)
    await db.flush()
    await write_operation_audit(
        db, actor=current_user, module="douyin_color_analytics", action="create_expected_schedule",
        target_type="collector_expected_schedule", target_id=schedule.id,
        after_data={"account_id": account.id, "weekday_mask": schedule.weekday_mask,
                    "timezone": schedule.timezone, "enabled": schedule.enabled}, request=request,
    )
    return ApiResponse.ok({"id": schedule.id, "account_id": schedule.account_id})



@router.get("/health", response_model=ApiResponse)
async def get_health(
    request: Request,
    current_user: SysUser = Depends(require_any_permission("douyin.admin", "douyin.operator", "douyin.viewer")),
    db: AsyncSession = Depends(get_db),
):
    """Return collector status, queue capacity, and feature flags for operators."""
    collectors = (await db.execute(
        select(CollectorInstance)
        .join(DouyinCreatorAccount, DouyinCreatorAccount.id == CollectorInstance.account_id)
        .where(DouyinCreatorAccount.status == "active")
    )).scalars().all()
    collector_status = [
        {
            "account_id": c.account_id,
            "current_status": c.current_status,
            "queued_batch_count": c.queued_batch_count,
            "queued_bytes": c.queued_bytes,
            "script_version": getattr(c, "script_version", None),
            "last_heartbeat_at": (
                c.last_heartbeat_at.isoformat()
                if getattr(c, "last_heartbeat_at", None)
                else None
            ),
        }
        for c in collectors
    ]
    queued_count = (await db.execute(
        select(func.count()).select_from(CalculationJob).where(CalculationJob.status == "queued")
    )).scalar() or 0
    return ApiResponse.ok({
        "collector_status": collector_status,
        "queue_capacity": {"queued_jobs": queued_count},
        "feature_flags": {"color_analysis_enabled": True, "annotation_review_enabled": True},
    })


async def _active_account_for_dashboard(db: AsyncSession, account_id: int) -> DouyinCreatorAccount:
    account = (await db.execute(select(DouyinCreatorAccount).where(
        DouyinCreatorAccount.id == account_id,
        DouyinCreatorAccount.status == "active",
    ))).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="active_account_not_found")
    return account


async def _release_stage_payload(db: AsyncSession, account_id: int) -> dict[str, object]:
    configuration = (await db.execute(select(ReleaseStageConfiguration).where(
        ReleaseStageConfiguration.account_id == account_id,
    ))).scalar_one_or_none()
    token = (await db.execute(select(DouyinUploadToken).where(
        DouyinUploadToken.account_id == account_id,
        DouyinUploadToken.status == "active",
    ).order_by(DouyinUploadToken.created_at.desc()).limit(1))).scalar_one_or_none()
    token_is_active = bool(token and (token.expires_at is None or token.expires_at > datetime.now(timezone.utc)))
    return {
        "current_stage": configuration.current_stage if configuration else "A",
        "bounce_report_enabled": configuration.bounce_report_enabled if configuration else False,
        "bounce_semantics_status": configuration.bounce_semantics_status if configuration else "pending",
        "active_token": ({"token_prefix": token.token_prefix, "expires_at": token.expires_at, "is_active": token_is_active} if token else None),
    }


@router.get("/accounts/{account_id}/release-stage", response_model=ApiResponse)
async def get_release_stage(
    account_id: int,
    _: SysUser = Depends(require_any_permission("douyin.admin", "douyin.operator", "douyin.viewer")),
    db: AsyncSession = Depends(get_db),
):
    await _active_account_for_dashboard(db, account_id)
    return ApiResponse.ok(await _release_stage_payload(db, account_id))




@router.post("/accounts/{account_id}/upload-tokens/rotate", response_model=ApiResponse)
async def rotate_upload_tokens(
    account_id: int,
    request: Request,
    current_user: SysUser = Depends(require_permission("douyin.admin")),
    db: AsyncSession = Depends(get_db),
):
    """Revoke all active upload tokens for an account and issue a fresh one."""
    account = (await db.execute(select(DouyinCreatorAccount).where(
        DouyinCreatorAccount.id == account_id,
    ))).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="account_not_found")

    active_tokens = (await db.execute(
        select(DouyinUploadToken).where(
            DouyinUploadToken.account_id == account_id,
            DouyinUploadToken.status == "active",
        )
    )).scalars().all()

    revoked_prefixes = []
    now = datetime.now(timezone.utc)
    for token in active_tokens:
        token.status = "revoked"
        token.revoked_by = current_user.id
        token.revoked_at = now
        revoked_prefixes.append(token.token_prefix)
    await db.flush()

    token_value = f"dyup_{secrets.token_urlsafe(32)}"
    new_token = DouyinUploadToken(
        account_id=account.id, token_hash=hash_upload_token(token_value), token_prefix=token_value[:12],
        created_by=current_user.id, status="active", expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(new_token)
    await db.flush()
    await write_operation_audit(
        db, actor=current_user, module="douyin_color_analytics", action="rotate_upload_token",
        target_type="douyin_upload_token", target_id=new_token.id,
        before_data={"revoked_token_prefixes": revoked_prefixes},
        after_data={"account_id": account.id, "new_token_prefix": new_token.token_prefix,
                    "expires_at": new_token.expires_at.isoformat()},
        request=request,
    )
    return ApiResponse.ok({
        "upload_token": token_value,
        "expires_at": new_token.expires_at,
        "revoked_count": len(revoked_prefixes),
    })


# ---------------------------------------------------------------------------
# v4.0 report query / export / release-stage / compute-metrics routes
# ---------------------------------------------------------------------------

class AdvanceStageRequest(BaseModel):
    target_stage: str = Field(pattern="^(A|B|C|D)$")


class ToggleBounceReportRequest(BaseModel):
    enabled: bool


class ExportReportRequest(BaseModel):
    format: str = Field(pattern="^(csv|xlsx)$")
    tab: str = Field(pattern="^(outfit|top|bottom)$")
    observation_window: str = Field(pattern="^(t2|t7|t30|ad_hoc)$")
    position_segment: str = Field(default="all", pattern="^(all|front|middle|rear)$")


@router.get("/accounts/{account_id}/report/outfit", response_model=ApiResponse)
async def get_outfit_report(
    account_id: int,
    observation_window: str = Query(..., pattern="^(t2|t7|t30|ad_hoc)$"),
    position_segment: str = Query("all", pattern="^(all|front|middle|rear)$"),
    as_of_date: date | None = Query(None),
    current_user: SysUser = Depends(require_any_permission("douyin.analyst", "douyin.admin")),
    db: AsyncSession = Depends(get_db),
):
    """整套穿搭排名报告（主要排名）。"""
    await _active_account_for_dashboard(db, account_id)
    result = await db.run_sync(lambda sync_session: query_outfit_rankings(
        session=sync_session,
        account_id=account_id,
        observation_window=observation_window,
        position_segment=position_segment,
        as_of_date=as_of_date,
    ))
    return ApiResponse.ok(result)


@router.get("/accounts/{account_id}/report/top", response_model=ApiResponse)
async def get_top_report(
    account_id: int,
    observation_window: str = Query(..., pattern="^(t2|t7|t30|ad_hoc)$"),
    position_segment: str = Query("all", pattern="^(all|front|middle|rear)$"),
    as_of_date: date | None = Query(None),
    current_user: SysUser = Depends(require_any_permission("douyin.analyst", "douyin.admin")),
    db: AsyncSession = Depends(get_db),
):
    """单件分榜——上装排名（outer + top）。"""
    await _active_account_for_dashboard(db, account_id)
    result = await db.run_sync(lambda sync_session: query_single_garment_rankings(
        session=sync_session,
        account_id=account_id,
        ranking_bucket="top",
        observation_window=observation_window,
        position_segment=position_segment,
        as_of_date=as_of_date,
    ))
    return ApiResponse.ok(result)


@router.get("/accounts/{account_id}/report/bottom", response_model=ApiResponse)
async def get_bottom_report(
    account_id: int,
    observation_window: str = Query(..., pattern="^(t2|t7|t30|ad_hoc)$"),
    position_segment: str = Query("all", pattern="^(all|front|middle|rear)$"),
    as_of_date: date | None = Query(None),
    current_user: SysUser = Depends(require_any_permission("douyin.analyst", "douyin.admin")),
    db: AsyncSession = Depends(get_db),
):
    """单件分榜——下装排名（bottom）。"""
    await _active_account_for_dashboard(db, account_id)
    result = await db.run_sync(lambda sync_session: query_single_garment_rankings(
        session=sync_session,
        account_id=account_id,
        ranking_bucket="bottom",
        observation_window=observation_window,
        position_segment=position_segment,
        as_of_date=as_of_date,
    ))
    return ApiResponse.ok(result)


@router.post("/accounts/{account_id}/report/export", response_model=ApiResponse)
async def export_report(
    account_id: int,
    payload: ExportReportRequest,
    request: Request,
    current_user: SysUser = Depends(require_any_permission("douyin.analyst", "douyin.admin")),
    db: AsyncSession = Depends(get_db),
):
    """导出排名报告为 CSV/XLSX（含公式注入防护）。"""
    await _active_account_for_dashboard(db, account_id)

    def _query(sync_session):
        if payload.tab == "outfit":
            return query_outfit_rankings(
                session=sync_session, account_id=account_id,
                observation_window=payload.observation_window,
                position_segment=payload.position_segment,
            )
        return query_single_garment_rankings(
            session=sync_session, account_id=account_id,
            ranking_bucket=payload.tab,
            observation_window=payload.observation_window,
            position_segment=payload.position_segment,
        )

    rankings = await db.run_sync(_query)
    export_result = export_rankings(rankings=rankings, format=payload.format, tab=payload.tab)
    await write_operation_audit(
        db, actor=current_user, module="douyin_color_analytics", action="export_report",
        target_type="douyin_color_report", target_id=account_id,
        after_data={"format": payload.format, "tab": payload.tab,
                    "observation_window": payload.observation_window,
                    "filename": export_result["filename"]},
        request=request,
    )
    return ApiResponse.ok({
        "content": export_result["content"],
        "filename": export_result["filename"],
        "metadata": export_result["metadata"],
    })


@router.post("/accounts/{account_id}/release-stage/advance", response_model=ApiResponse)
async def advance_release_stage(
    account_id: int,
    payload: AdvanceStageRequest,
    request: Request,
    current_user: SysUser = Depends(require_permission("douyin.admin")),
    db: AsyncSession = Depends(get_db),
):
    """推进发布阶段（A→B→C→D，只能向前）。"""
    await _active_account_for_dashboard(db, account_id)
    config = (await db.execute(select(ReleaseStageConfiguration).where(
        ReleaseStageConfiguration.account_id == account_id,
    ))).scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="release_stage_not_configured")
    before = {"current_stage": config.current_stage, "bounce_report_enabled": config.bounce_report_enabled,
              "bounce_semantics_status": config.bounce_semantics_status}
    try:
        updated = advance_stage(
            config={
                "current_stage": config.current_stage,
                "bounce_report_enabled": config.bounce_report_enabled,
                "bounce_semantics_status": config.bounce_semantics_status,
            },
            target_stage=payload.target_stage,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    config.current_stage = updated["current_stage"]
    await db.flush()
    await write_operation_audit(
        db, actor=current_user, module="douyin_color_analytics", action="advance_release_stage",
        target_type="release_stage_configuration", target_id=config.id,
        before_data=before, after_data={"current_stage": config.current_stage}, request=request,
    )
    return ApiResponse.ok(await _release_stage_payload(db, account_id))


@router.post("/accounts/{account_id}/release-stage/bounce-report", response_model=ApiResponse)
async def toggle_bounce_report(
    account_id: int,
    payload: ToggleBounceReportRequest,
    request: Request,
    current_user: SysUser = Depends(require_permission("douyin.admin")),
    db: AsyncSession = Depends(get_db),
):
    """开启/关闭跳出率报告（开启需 bounce_semantics_status 已验证）。"""
    await _active_account_for_dashboard(db, account_id)
    config = (await db.execute(select(ReleaseStageConfiguration).where(
        ReleaseStageConfiguration.account_id == account_id,
    ))).scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="release_stage_not_configured")
    before = {"bounce_report_enabled": config.bounce_report_enabled,
              "bounce_semantics_status": config.bounce_semantics_status}
    config_snapshot = {
        "current_stage": config.current_stage,
        "bounce_report_enabled": config.bounce_report_enabled,
        "bounce_semantics_status": config.bounce_semantics_status,
    }
    try:
        if payload.enabled:
            updated = enable_bounce_report(
                config=config_snapshot,
                bounce_semantics_status=config.bounce_semantics_status,
            )
        else:
            updated = disable_bounce_report(config=config_snapshot)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    config.bounce_report_enabled = updated["bounce_report_enabled"]
    if payload.enabled:
        config.bounce_semantics_status = updated["bounce_semantics_status"]
    await db.flush()
    await write_operation_audit(
        db, actor=current_user, module="douyin_color_analytics", action="toggle_bounce_report",
        target_type="release_stage_configuration", target_id=config.id,
        before_data=before,
        after_data={"bounce_report_enabled": config.bounce_report_enabled,
                    "bounce_semantics_status": config.bounce_semantics_status},
        request=request,
    )
    return ApiResponse.ok(await _release_stage_payload(db, account_id))


@router.post("/accounts/{account_id}/compute-metrics", response_model=ApiResponse)
async def compute_metrics(
    account_id: int,
    request: Request,
    current_user: SysUser = Depends(require_permission("douyin.admin")),
    db: AsyncSession = Depends(get_db),
):
    """触发指标计算：为该账号所有 approved 片段计算 outfit 和 per-garment 指标。"""
    await _active_account_for_dashboard(db, account_id)

    config = (await db.execute(select(ReleaseStageConfiguration).where(
        ReleaseStageConfiguration.account_id == account_id,
    ))).scalar_one_or_none()
    bounce_semantics_status = config.bounce_semantics_status if config else "unverified"

    clips = (await db.execute(select(VideoClip).where(
        VideoClip.account_id == account_id,
        VideoClip.annotation_status == "approved",
        VideoClip.deleted_at.is_(None),
    ))).scalars().all()

    video_ids = sorted({clip.video_id for clip in clips})
    outfit_count = 0
    video_metric_count = 0

    for video_id in video_ids:
        video_clips = [c for c in clips if c.video_id == video_id]
        video = (await db.execute(select(Video).where(
            Video.account_id == account_id, Video.id == video_id,
        ))).scalar_one_or_none()
        if video is None:
            continue
        snapshots = (await db.execute(select(VideoAnalysisSnapshot).where(
            VideoAnalysisSnapshot.account_id == account_id,
            VideoAnalysisSnapshot.video_id == video_id,
        ))).scalars().all()
        snapshot_dicts = [{
            "id": s.id, "analysis_type": s.analysis_type,
            "curve_quality_status": s.curve_quality_status,
            "item_status": s.curve_quality_status,
            "collected_at": s.collected_at,
            "normalized_curve_json": s.normalized_curve_json,
            "source_snapshot_hash": s.source_snapshot_hash,
        } for s in snapshots]
        retention_snap = select_retention_snapshot(snapshot_dicts, source_data_cutoff_at=None)
        bounce_snap = select_bounce_snapshot(snapshot_dicts, source_data_cutoff_at=None)
        clip_dicts = [{
            "id": c.id, "version": c.version,
            "start_ms": c.start_ms, "end_ms": c.end_ms,
            "input_start_ms": c.input_start_ms, "input_end_ms": c.input_end_ms,
            "curve_resolution_ms": c.curve_resolution_ms,
            "focus_status": c.focus_status,
            "annotation_status": c.annotation_status,
            "overlap_status": c.overlap_status,
            "outfit_parts_json": c.outfit_parts_json,
        } for c in video_clips]

        outfit_metric = compute_outfit_metric(
            clips=clip_dicts,
            retention_snapshot=retention_snap,
            bounce_snapshot=bounce_snap,
            video_duration_ms=video.duration_ms or 0,
            observation_window="ad_hoc",
            metric_version="v4.0",
            bounce_semantics_status=bounce_semantics_status,
        )
        if outfit_metric is not None:
            db.add(OutfitColorMetric(
                account_id=account_id,
                combination_key=outfit_metric["combination_key"],
                observation_window="ad_hoc",
                metric_version=outfit_metric["metric_version"],
                metric_input_hash=outfit_metric["metric_input_hash"],
                average_retention=outfit_metric.get("average_retention"),
                retention_drop=outfit_metric.get("retention_drop"),
                average_platform_bounce_curve_value=outfit_metric.get("average_platform_bounce_curve_value"),
                max_platform_bounce_curve_value=outfit_metric.get("max_platform_bounce_curve_value"),
                participant_count=outfit_metric["participant_count"],
                total_clip_duration_ms=outfit_metric.get("total_clip_duration_ms", 0),
                video_duration_ms=outfit_metric.get("video_duration_ms", 0),
                dominant_position_segment=outfit_metric.get("dominant_position_segment"),
                retention_calculation_status=outfit_metric.get("retention_calculation_status", "pending"),
                bounce_calculation_status=outfit_metric.get("bounce_calculation_status", "pending"),
                calculated_at=outfit_metric.get("calculated_at"),
            ))
            outfit_count += 1

        outfit_parts = []
        for clip in video_clips:
            for part in (clip.outfit_parts_json or []):
                outfit_parts.append({
                    "position": part.get("position") or part.get("garment_position"),
                    "style_id": part.get("style_id"),
                    "sku_code": part.get("sku_code"),
                })
        garment_metrics = compute_video_color_metric(
            clips=clip_dicts,
            outfit_parts=outfit_parts,
            retention_snapshot=retention_snap,
            bounce_snapshot=bounce_snap,
            video_duration_ms=video.duration_ms or 0,
            observation_window="ad_hoc",
            metric_version="v4.0",
            bounce_semantics_status=bounce_semantics_status,
        )
        for gm in garment_metrics:
            db.add(VideoColorMetric(
                account_id=account_id,
                video_id=video_id,
                style_id=gm.get("style_id") or 0,
                color_id=None,
                observation_window="ad_hoc",
                retention_snapshot_id=gm.get("retention_snapshot_id"),
                bounce_snapshot_id=gm.get("bounce_snapshot_id"),
                retention_source_hash=gm.get("retention_source_hash") or "",
                bounce_source_hash=gm.get("bounce_source_hash"),
                annotation_set_hash=gm.get("annotation_set_hash") or "",
                metric_input_hash=gm.get("metric_input_hash") or "",
                metric_version=gm.get("metric_version") or "v4.0",
                garment_position=gm.get("garment_position") or "none",
                sku_code=gm.get("sku_code"),
                average_retention=gm.get("average_retention"),
                retention_drop=gm.get("retention_drop"),
                average_platform_bounce_curve_value=gm.get("average_platform_bounce_curve_value"),
                max_platform_bounce_curve_value=gm.get("max_platform_bounce_curve_value"),
                clip_count=gm.get("clip_count", 0),
                total_clip_duration_ms=gm.get("total_clip_duration_ms", 0),
                average_relative_position=gm.get("average_relative_position"),
                earliest_relative_position=gm.get("earliest_relative_position"),
                latest_relative_position=gm.get("latest_relative_position"),
                average_clip_duration_ms=gm.get("average_clip_duration_ms"),
                video_duration_ms=gm.get("video_duration_ms", 0),
                dominant_position_segment=gm.get("dominant_position_segment"),
                retention_calculation_status=gm.get("retention_calculation_status", "pending"),
                bounce_calculation_status=gm.get("bounce_calculation_status", "pending"),
                calculated_at=gm.get("calculated_at"),
            ))
            video_metric_count += 1

    await db.flush()
    await write_operation_audit(
        db, actor=current_user, module="douyin_color_analytics", action="compute_metrics",
        target_type="douyin_creator_account", target_id=account_id,
        after_data={"outfit_metrics_count": outfit_count,
                    "video_color_metrics_count": video_metric_count},
        request=request,
    )
    return ApiResponse.ok({
        "outfit_metrics_count": outfit_count,
        "video_color_metrics_count": video_metric_count,
    })


from app.api.v1.douyin_color_annotation_routes import annotation_router
router.include_router(annotation_router)
