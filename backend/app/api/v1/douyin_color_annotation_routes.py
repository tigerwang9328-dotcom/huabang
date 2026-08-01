"""Account-scoped v3.1 merchandise and single-primary clip annotation routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.models.douyin_color_analytics import (
    CollectorInstance,
    DouyinCreatorAccount,
    GarmentColor,
    GarmentSku,
    GarmentStyle,
    Video,
    VideoClip,
)
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.schemas.douyin_color_analytics import (
    AnnotationActionRequest,
    GarmentColorCreateRequest,
    GarmentColorUpdateRequest,
    GarmentSkuCreateRequest,
    GarmentSkuUpdateRequest,
    GarmentStyleCreateRequest,
    GarmentStyleUpdateRequest,
    VideoClipCreateRequest,
    VideoClipUpdateRequest,
)
from app.services.douyin_color_annotation_service import (
    AnnotationConflictError,
    AnnotationValidationError,
    assert_expected_version,
    overlap_requirement,
    snap_clip_bounds,
    validate_annotation_transition,
    validate_primary_assignment,
)
from app.services.douyin_color_security_service import sanitize_douyin_text
from app.services.operation_audit_service import write_operation_audit


annotation_router = APIRouter()


def _annotation_http_error(error: AnnotationValidationError) -> HTTPException:
    status_code = status.HTTP_409_CONFLICT if isinstance(error, AnnotationConflictError) else status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=status_code, detail=str(error))


async def _scoped_record(
    db: AsyncSession, model: type, *, account_id: int, record_id: int, error_code: str, lock: bool = False,
):
    query = select(model).where(model.account_id == account_id, model.id == record_id)
    if lock:
        query = query.with_for_update()
    record = (await db.execute(query)).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_code)
    return record


async def _ensure_unique(
    db: AsyncSession, model: type, *, account_id: int, field: str, value: str, error_code: str,
    exclude_id: int | None = None, style_id: int | None = None,
) -> None:
    query = select(model.id).where(model.account_id == account_id, getattr(model, field) == value)
    if style_id is not None:
        query = query.where(model.style_id == style_id)
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)
    if (await db.execute(query)).scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_code)


async def _annotation_account(
    db: AsyncSession, *, account_hint: int | None = None,
) -> DouyinCreatorAccount:
    """Derive the sole first-release account; request IDs are hints, never authority."""

    accounts = (await db.execute(select(DouyinCreatorAccount).where(
        DouyinCreatorAccount.status == "active",
    ))).scalars().all()
    if len(accounts) != 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="active_account_not_configured")
    account = accounts[0]
    if account_hint is not None and account_hint != account.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account_scope_mismatch")
    return account



async def _request_account(
    db: AsyncSession, *, query_account_id: int | None = None, payload_account_id: int | None = None,
) -> DouyinCreatorAccount:
    account = await _annotation_account(db, account_hint=query_account_id)
    if payload_account_id is not None and payload_account_id != account.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account_scope_mismatch")
    return account

def _clip_response(clip: VideoClip) -> dict[str, object]:
    return {
        "id": clip.id, "account_id": clip.account_id, "video_id": clip.video_id,
        "style_id": clip.style_id, "color_id": clip.color_id,
        "start_ms": clip.start_ms, "end_ms": clip.end_ms,
        "input_start_ms": clip.input_start_ms, "input_end_ms": clip.input_end_ms,
        "curve_resolution_ms": clip.curve_resolution_ms, "focus_status": clip.focus_status,
        "focus_note": clip.focus_note, "annotation_status": clip.annotation_status,
        "overlap_reason": clip.overlap_reason, "overlap_status": clip.overlap_status,
        "overlap_approved_by": clip.overlap_approved_by, "overlap_approved_at": clip.overlap_approved_at,
        "submitted_by": clip.submitted_by, "submitted_at": clip.submitted_at,
        "approved_by": clip.approved_by, "approved_at": clip.approved_at,
        "created_by": clip.created_by, "created_at": clip.created_at,
        "updated_by": clip.updated_by, "updated_at": clip.updated_at,
        "version": clip.version, "deleted_at": clip.deleted_at,
    }


async def _validate_clip_payload(
    *, db: AsyncSession, account_id: int, payload: VideoClipCreateRequest, exclude_clip_id: int | None = None,
) -> tuple[int, int, str]:
    if payload.account_id != account_id:
        raise AnnotationValidationError("account_scope_mismatch")
    validate_primary_assignment(payload.focus_status.value, style_id=payload.style_id, color_id=payload.color_id)
    video = (await db.execute(
        select(Video).where(Video.account_id == account_id, Video.id == payload.video_id).with_for_update()
    )).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="video_not_found")
    start_ms, end_ms = snap_clip_bounds(
        input_start_ms=payload.input_start_ms, input_end_ms=payload.input_end_ms,
        curve_resolution_ms=payload.curve_resolution_ms, video_duration_ms=video.duration_ms,
    )
    if payload.focus_status.value != "clear_primary":
        return start_ms, end_ms, "not_required"
    style = await _scoped_record(db, GarmentStyle, account_id=account_id, record_id=payload.style_id, error_code="style_not_found")
    color = await _scoped_record(db, GarmentColor, account_id=account_id, record_id=payload.color_id, error_code="color_not_found")
    if color.style_id != style.id:
        raise AnnotationValidationError("color_style_mismatch")
    query = select(VideoClip).where(
        VideoClip.account_id == account_id, VideoClip.video_id == video.id, VideoClip.deleted_at.is_(None),
    )
    if exclude_clip_id is not None:
        query = query.where(VideoClip.id != exclude_clip_id)
    overlap_status = "not_required"
    for other in (await db.execute(query)).scalars().all():
        if overlap_requirement(
            start_ms=start_ms, end_ms=end_ms, color_id=color.id,
            other_start_ms=other.start_ms, other_end_ms=other.end_ms, other_color_id=other.color_id,
        ) == "pending_approval":
            overlap_status = "pending_approval"
            break
    return start_ms, end_ms, overlap_status


@annotation_router.get("/annotation-context", response_model=ApiResponse)
async def annotation_context(_: SysUser = Depends(require_permission("douyin.annotation.edit")), db: AsyncSession = Depends(get_db)):
    account = await _annotation_account(db)
    latest_instance = (await db.execute(
        select(CollectorInstance)
        .where(CollectorInstance.account_id == account.id)
        .order_by(CollectorInstance.last_heartbeat_at.desc().nulls_last())
        .limit(1)
    )).scalar_one_or_none()
    return ApiResponse.ok({"account": {
        "id": account.id,
        "account_key": account.account_key,
        "display_name": account.display_name,
        "observed_account_name": latest_instance.observed_account_name if latest_instance else None,
        "last_heartbeat_at": latest_instance.last_heartbeat_at.isoformat() if latest_instance and latest_instance.last_heartbeat_at else None,
    }})


@annotation_router.get("/videos", response_model=ApiResponse)
async def list_annotation_videos(account_id: int, _: SysUser = Depends(require_permission("douyin.annotation.edit")), db: AsyncSession = Depends(get_db)):
    account_id = (await _request_account(db, query_account_id=account_id)).id
    videos = (await db.execute(select(Video).where(Video.account_id == account_id).order_by(Video.published_at.desc(), Video.id.desc()))).scalars().all()
    return ApiResponse.ok({"items": [{
        "id": video.id, "video_id_string": video.video_id_string, "title": video.title,
        "published_at": video.published_at, "duration_ms": video.duration_ms, "cover_path": video.cover_path,
        "creator_detail_path": video.creator_detail_path, "collection_status": video.collection_status,
    } for video in videos]})


@annotation_router.get("/videos/{video_id_string}", response_model=ApiResponse)
async def get_annotation_video(video_id_string: str, account_id: int, _: SysUser = Depends(require_permission("douyin.annotation.edit")), db: AsyncSession = Depends(get_db)):
    account_id = (await _request_account(db, query_account_id=account_id)).id
    video = (await db.execute(select(Video).where(
        Video.account_id == account_id, Video.video_id_string == video_id_string,
    ))).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="video_not_found")
    return ApiResponse.ok({
        "id": video.id, "video_id_string": video.video_id_string, "title": video.title,
        "published_at": video.published_at, "duration_ms": video.duration_ms, "cover_path": video.cover_path,
        "creator_detail_path": video.creator_detail_path, "collection_status": video.collection_status,
    })


@annotation_router.get("/styles", response_model=ApiResponse)
async def list_garment_styles(account_id: int, _: SysUser = Depends(require_permission("douyin.annotation.edit")), db: AsyncSession = Depends(get_db)):
    account_id = (await _request_account(db, query_account_id=account_id)).id
    items = (await db.execute(select(GarmentStyle).where(GarmentStyle.account_id == account_id).order_by(GarmentStyle.style_code))).scalars().all()
    return ApiResponse.ok({"items": [{
        "id": item.id, "account_id": item.account_id, "style_code": item.style_code, "style_name": item.style_name,
        "main_image": item.main_image, "status": item.status,
    } for item in items]})


@annotation_router.post("/styles", response_model=ApiResponse)
async def create_garment_style(payload: GarmentStyleCreateRequest, request: Request, current_user: SysUser = Depends(require_permission("douyin.admin")), db: AsyncSession = Depends(get_db)):
    account_id = (await _request_account(db, payload_account_id=payload.account_id)).id
    await _ensure_unique(db, GarmentStyle, account_id=payload.account_id, field="style_code", value=payload.style_code.strip(), error_code="style_code_conflict")
    item = GarmentStyle(
        account_id=payload.account_id, style_code=payload.style_code.strip(),
        style_name=sanitize_douyin_text(payload.style_name), main_image=payload.main_image, status=payload.status,
    )
    db.add(item)
    await db.flush()
    await write_operation_audit(db, actor=current_user, module="douyin_color_analytics", action="create_style", target_type="garment_style", target_id=item.id, after_data={"account_id": item.account_id, "style_code": item.style_code}, request=request)
    return ApiResponse.ok({"id": item.id})


@annotation_router.patch("/styles/{style_id}", response_model=ApiResponse)
async def update_garment_style(style_id: int, account_id: int, payload: GarmentStyleUpdateRequest, request: Request, current_user: SysUser = Depends(require_permission("douyin.admin")), db: AsyncSession = Depends(get_db)):
    account_id = (await _request_account(db, query_account_id=account_id)).id
    item = await _scoped_record(db, GarmentStyle, account_id=account_id, record_id=style_id, error_code="style_not_found")
    before = {"style_code": item.style_code, "style_name": item.style_name, "status": item.status}
    if payload.style_code is not None:
        await _ensure_unique(db, GarmentStyle, account_id=account_id, field="style_code", value=payload.style_code.strip(), error_code="style_code_conflict", exclude_id=item.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, sanitize_douyin_text(value) if field in {"style_name", "main_image"} else value)
    await write_operation_audit(db, actor=current_user, module="douyin_color_analytics", action="update_style", target_type="garment_style", target_id=item.id, before_data=before, after_data={"style_code": item.style_code, "style_name": item.style_name, "status": item.status}, request=request)
    return ApiResponse.ok({"id": item.id})


@annotation_router.get("/styles/{style_id}/colors", response_model=ApiResponse)
async def list_garment_colors(style_id: int, account_id: int, _: SysUser = Depends(require_permission("douyin.annotation.edit")), db: AsyncSession = Depends(get_db)):
    account_id = (await _request_account(db, query_account_id=account_id)).id
    await _scoped_record(db, GarmentStyle, account_id=account_id, record_id=style_id, error_code="style_not_found")
    items = (await db.execute(select(GarmentColor).where(
        GarmentColor.account_id == account_id, GarmentColor.style_id == style_id,
    ).order_by(GarmentColor.color_code))).scalars().all()
    return ApiResponse.ok({"items": [{
        "id": item.id, "account_id": item.account_id, "style_id": item.style_id, "color_code": item.color_code,
        "color_name": item.color_name, "color_image": item.color_image, "status": item.status,
    } for item in items]})


@annotation_router.post("/styles/{style_id}/colors", response_model=ApiResponse)
async def create_garment_color(style_id: int, payload: GarmentColorCreateRequest, request: Request, current_user: SysUser = Depends(require_permission("douyin.admin")), db: AsyncSession = Depends(get_db)):
    account_id = (await _request_account(db, payload_account_id=payload.account_id)).id
    style = await _scoped_record(db, GarmentStyle, account_id=payload.account_id, record_id=style_id, error_code="style_not_found")
    await _ensure_unique(db, GarmentColor, account_id=style.account_id, style_id=style.id, field="color_code", value=payload.color_code.strip(), error_code="color_code_conflict")
    item = GarmentColor(account_id=style.account_id, style_id=style.id, color_code=payload.color_code.strip(), color_name=sanitize_douyin_text(payload.color_name), color_image=payload.color_image, status=payload.status)
    db.add(item)
    await db.flush()
    await write_operation_audit(db, actor=current_user, module="douyin_color_analytics", action="create_color", target_type="garment_color", target_id=item.id, after_data={"account_id": item.account_id, "style_id": item.style_id, "color_code": item.color_code}, request=request)
    return ApiResponse.ok({"id": item.id})


@annotation_router.patch("/styles/{style_id}/colors/{color_id}", response_model=ApiResponse)
async def update_garment_color(style_id: int, color_id: int, account_id: int, payload: GarmentColorUpdateRequest, request: Request, current_user: SysUser = Depends(require_permission("douyin.admin")), db: AsyncSession = Depends(get_db)):
    account_id = (await _request_account(db, query_account_id=account_id)).id
    item = await _scoped_record(db, GarmentColor, account_id=account_id, record_id=color_id, error_code="color_not_found")
    if item.style_id != style_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="color_not_found")
    before = {"color_code": item.color_code, "color_name": item.color_name, "status": item.status}
    if payload.color_code is not None:
        await _ensure_unique(db, GarmentColor, account_id=account_id, style_id=style_id, field="color_code", value=payload.color_code.strip(), error_code="color_code_conflict", exclude_id=item.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, sanitize_douyin_text(value) if field in {"color_name", "color_image"} else value)
    await write_operation_audit(db, actor=current_user, module="douyin_color_analytics", action="update_color", target_type="garment_color", target_id=item.id, before_data=before, after_data={"color_code": item.color_code, "color_name": item.color_name, "status": item.status}, request=request)
    return ApiResponse.ok({"id": item.id})


@annotation_router.get("/skus", response_model=ApiResponse)
async def list_garment_skus(account_id: int, _: SysUser = Depends(require_permission("douyin.annotation.edit")), db: AsyncSession = Depends(get_db)):
    account_id = (await _request_account(db, query_account_id=account_id)).id
    items = (await db.execute(select(GarmentSku).where(GarmentSku.account_id == account_id).order_by(GarmentSku.sku_code))).scalars().all()
    return ApiResponse.ok({"items": [{
        "id": item.id, "account_id": item.account_id, "color_id": item.color_id, "sku_code": item.sku_code,
        "size_name": item.size_name, "status": item.status,
    } for item in items]})


@annotation_router.post("/skus", response_model=ApiResponse)
async def create_garment_sku(payload: GarmentSkuCreateRequest, request: Request, current_user: SysUser = Depends(require_permission("douyin.admin")), db: AsyncSession = Depends(get_db)):
    account_id = (await _request_account(db, payload_account_id=payload.account_id)).id
    color = await _scoped_record(db, GarmentColor, account_id=payload.account_id, record_id=payload.color_id, error_code="color_not_found")
    await _ensure_unique(db, GarmentSku, account_id=color.account_id, field="sku_code", value=payload.sku_code.strip(), error_code="sku_code_conflict")
    item = GarmentSku(account_id=color.account_id, color_id=color.id, sku_code=payload.sku_code.strip(), size_name=sanitize_douyin_text(payload.size_name), status=payload.status)
    db.add(item)
    await db.flush()
    await write_operation_audit(db, actor=current_user, module="douyin_color_analytics", action="create_sku", target_type="garment_sku", target_id=item.id, after_data={"account_id": item.account_id, "color_id": item.color_id, "sku_code": item.sku_code}, request=request)
    return ApiResponse.ok({"id": item.id})


@annotation_router.patch("/skus/{sku_id}", response_model=ApiResponse)
async def update_garment_sku(sku_id: int, account_id: int, payload: GarmentSkuUpdateRequest, request: Request, current_user: SysUser = Depends(require_permission("douyin.admin")), db: AsyncSession = Depends(get_db)):
    account_id = (await _request_account(db, query_account_id=account_id)).id
    item = await _scoped_record(db, GarmentSku, account_id=account_id, record_id=sku_id, error_code="sku_not_found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("color_id") is not None:
        await _scoped_record(db, GarmentColor, account_id=account_id, record_id=data["color_id"], error_code="color_not_found")
    before = {"color_id": item.color_id, "sku_code": item.sku_code, "status": item.status}
    if data.get("sku_code") is not None:
        await _ensure_unique(db, GarmentSku, account_id=account_id, field="sku_code", value=data["sku_code"].strip(), error_code="sku_code_conflict", exclude_id=item.id)
    for field, value in data.items():
        setattr(item, field, sanitize_douyin_text(value) if field == "size_name" else value)
    await write_operation_audit(db, actor=current_user, module="douyin_color_analytics", action="update_sku", target_type="garment_sku", target_id=item.id, before_data=before, after_data={"color_id": item.color_id, "sku_code": item.sku_code, "status": item.status}, request=request)
    return ApiResponse.ok({"id": item.id})


@annotation_router.get("/video-clips", response_model=ApiResponse)
async def list_video_clips(account_id: int, video_id: int | None = None, _: SysUser = Depends(require_permission("douyin.annotation.edit")), db: AsyncSession = Depends(get_db)):
    account_id = (await _request_account(db, query_account_id=account_id)).id
    query = select(VideoClip).where(VideoClip.account_id == account_id)
    if video_id is not None:
        query = query.where(VideoClip.video_id == video_id)
    items = (await db.execute(query.order_by(VideoClip.start_ms, VideoClip.id))).scalars().all()
    return ApiResponse.ok({"items": [_clip_response(item) for item in items]})


@annotation_router.post("/video-clips", response_model=ApiResponse)
async def create_video_clip(payload: VideoClipCreateRequest, request: Request, current_user: SysUser = Depends(require_permission("douyin.annotation.edit")), db: AsyncSession = Depends(get_db)):
    account_id = (await _request_account(db, payload_account_id=payload.account_id)).id
    try:
        start_ms, end_ms, overlap_status = await _validate_clip_payload(db=db, account_id=payload.account_id, payload=payload)
    except AnnotationValidationError as error:
        raise _annotation_http_error(error) from None
    clip = VideoClip(
        account_id=payload.account_id, video_id=payload.video_id, style_id=payload.style_id, color_id=payload.color_id,
        start_ms=start_ms, end_ms=end_ms, input_start_ms=payload.input_start_ms, input_end_ms=payload.input_end_ms,
        curve_resolution_ms=payload.curve_resolution_ms, focus_status=payload.focus_status.value,
        focus_note=sanitize_douyin_text(payload.focus_note), annotation_status="draft",
        overlap_reason=sanitize_douyin_text(payload.overlap_reason), overlap_status=overlap_status, created_by=current_user.id,
    )
    db.add(clip)
    await db.flush()
    await write_operation_audit(db, actor=current_user, module="douyin_color_analytics", action="create_video_clip", target_type="video_clip", target_id=clip.id, after_data=_clip_response(clip), request=request)
    return ApiResponse.ok(_clip_response(clip))


@annotation_router.patch("/video-clips/{clip_id}", response_model=ApiResponse)
async def update_video_clip(clip_id: int, account_id: int, payload: VideoClipUpdateRequest, request: Request, current_user: SysUser = Depends(require_permission("douyin.annotation.edit")), db: AsyncSession = Depends(get_db)):
    account_id = (await _request_account(db, query_account_id=account_id, payload_account_id=payload.account_id)).id
    clip = await _scoped_record(db, VideoClip, account_id=account_id, record_id=clip_id, error_code="video_clip_not_found", lock=True)
    try:
        assert_expected_version(current_version=clip.version, expected_version=payload.expected_version)
        if clip.annotation_status not in {"draft", "rejected"}:
            raise AnnotationValidationError("annotation_not_editable")
        start_ms, end_ms, overlap_status = await _validate_clip_payload(db=db, account_id=account_id, payload=payload, exclude_clip_id=clip.id)
    except AnnotationValidationError as error:
        raise _annotation_http_error(error) from None
    before = _clip_response(clip)
    for field in ("video_id", "style_id", "color_id", "input_start_ms", "input_end_ms", "curve_resolution_ms"):
        setattr(clip, field, getattr(payload, field))
    clip.start_ms, clip.end_ms, clip.focus_status = start_ms, end_ms, payload.focus_status.value
    clip.focus_note, clip.overlap_reason, clip.overlap_status = sanitize_douyin_text(payload.focus_note), sanitize_douyin_text(payload.overlap_reason), overlap_status
    clip.annotation_status, clip.updated_by, clip.version = "draft", current_user.id, clip.version + 1
    await write_operation_audit(db, actor=current_user, module="douyin_color_analytics", action="update_video_clip", target_type="video_clip", target_id=clip.id, before_data=before, after_data=_clip_response(clip), request=request)
    return ApiResponse.ok(_clip_response(clip))


@annotation_router.delete("/video-clips/{clip_id}", response_model=ApiResponse)
async def delete_video_clip(clip_id: int, account_id: int, payload: AnnotationActionRequest, request: Request, current_user: SysUser = Depends(require_permission("douyin.annotation.edit")), db: AsyncSession = Depends(get_db)):
    return await _transition_video_clip(clip_id=clip_id, account_id=account_id, payload=payload, target_status="deleted", action="delete_video_clip", request=request, current_user=current_user, db=db)


async def _transition_video_clip(*, clip_id: int, account_id: int, payload: AnnotationActionRequest, target_status: str, action: str, request: Request, current_user: SysUser, db: AsyncSession) -> ApiResponse:
    account_id = (await _request_account(db, query_account_id=account_id)).id
    clip = await _scoped_record(db, VideoClip, account_id=account_id, record_id=clip_id, error_code="video_clip_not_found", lock=True)
    try:
        assert_expected_version(current_version=clip.version, expected_version=payload.expected_version)
        validate_annotation_transition(clip.annotation_status, target_status)
    except AnnotationValidationError as error:
        raise _annotation_http_error(error) from None
    before, now = _clip_response(clip), datetime.now(timezone.utc)
    clip.annotation_status, clip.updated_by, clip.version = target_status, current_user.id, clip.version + 1
    if target_status == "submitted":
        clip.submitted_by, clip.submitted_at = current_user.id, now
    elif target_status == "approved":
        clip.approved_by, clip.approved_at = current_user.id, now
        if clip.overlap_status == "pending_approval":
            clip.overlap_status, clip.overlap_approved_by, clip.overlap_approved_at = "approved", current_user.id, now
    elif target_status == "deleted":
        clip.deleted_at = now
    elif target_status == "draft":
        clip.deleted_at = None
    await write_operation_audit(db, actor=current_user, module="douyin_color_analytics", action=action, target_type="video_clip", target_id=clip.id, before_data=before, after_data=_clip_response(clip), request=request)
    return ApiResponse.ok(_clip_response(clip))


@annotation_router.post("/video-clips/{clip_id}/submit", response_model=ApiResponse)
async def submit_video_clip(clip_id: int, account_id: int, payload: AnnotationActionRequest, request: Request, current_user: SysUser = Depends(require_permission("douyin.annotation.edit")), db: AsyncSession = Depends(get_db)):
    return await _transition_video_clip(clip_id=clip_id, account_id=account_id, payload=payload, target_status="submitted", action="submit_video_clip", request=request, current_user=current_user, db=db)


@annotation_router.post("/video-clips/{clip_id}/approve", response_model=ApiResponse)
async def approve_video_clip(clip_id: int, account_id: int, payload: AnnotationActionRequest, request: Request, current_user: SysUser = Depends(require_permission("douyin.annotation.approve")), db: AsyncSession = Depends(get_db)):
    return await _transition_video_clip(clip_id=clip_id, account_id=account_id, payload=payload, target_status="approved", action="approve_video_clip", request=request, current_user=current_user, db=db)


@annotation_router.post("/video-clips/{clip_id}/reject", response_model=ApiResponse)
async def reject_video_clip(clip_id: int, account_id: int, payload: AnnotationActionRequest, request: Request, current_user: SysUser = Depends(require_permission("douyin.annotation.approve")), db: AsyncSession = Depends(get_db)):
    return await _transition_video_clip(clip_id=clip_id, account_id=account_id, payload=payload, target_status="rejected", action="reject_video_clip", request=request, current_user=current_user, db=db)


@annotation_router.post("/video-clips/{clip_id}/restore", response_model=ApiResponse)
async def restore_video_clip(clip_id: int, account_id: int, payload: AnnotationActionRequest, request: Request, current_user: SysUser = Depends(require_permission("douyin.annotation.edit")), db: AsyncSession = Depends(get_db)):
    return await _transition_video_clip(clip_id=clip_id, account_id=account_id, payload=payload, target_status="draft", action="restore_video_clip", request=request, current_user=current_user, db=db)
