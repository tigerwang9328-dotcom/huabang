"""财务中心“历史数据存档”独立接口。"""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.api.v1.deps import get_db
from app.core.permissions import require_permission
from app.models.sys import SysUser as User
from app.services.finance import history_archive as svc

router = APIRouter(prefix="/finance/history-archive", tags=["财务-历史数据存档"])


class ArchiveUpdateBody(BaseModel):
    data_name: str | None = Field(None, max_length=200)
    category_id: int | None = None
    project_name: str | None = Field(None, max_length=128)
    company_name: str | None = Field(None, max_length=255)
    store_id: int | None = None
    data_year: int | None = None
    data_month: int | None = None
    data_start_date: date | None = None
    data_end_date: date | None = None
    data_type: str | None = None
    description: str | None = Field(None, max_length=4000)


class DeleteArchiveBody(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class CategoryCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    parent_id: int
    sort_order: int = 0


class CategoryUpdateBody(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    sort_order: int | None = None


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    ip_address = forwarded or (request.client.host if request.client else None)
    return ip_address, request.headers.get("user-agent")


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/summary")
async def archive_summary(
    db: AsyncSession = Depends(get_db),
    _ = require_permission(svc.PERM_VIEW),
):
    return await svc.get_summary(db)


@router.get("/files")
async def list_archive_files(
    keyword: str | None = Query(None),
    category_id: int | None = Query(None),
    project_name: str | None = Query(None),
    company_name: str | None = Query(None),
    store_id: int | None = Query(None),
    year: int | None = Query(None, ge=1900, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    uploader: str | None = Query(None),
    data_type: str | None = Query(None),
    status: str = Query("NORMAL"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _ = require_permission(svc.PERM_VIEW),
):
    try:
        return await svc.list_archives(
            db,
            keyword=keyword,
            category_id=category_id,
            project_name=project_name,
            company_name=company_name,
            store_id=store_id,
            year=year,
            month=month,
            uploader=uploader,
            data_type=data_type,
            status=status.upper(),
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise _http_error(exc)


@router.get("/files/{file_id}")
async def archive_detail(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    _ = require_permission(svc.PERM_VIEW),
):
    record = await svc.get_archive_detail(db, file_id)
    if not record:
        raise HTTPException(status_code=404, detail="存档文件不存在")
    return record


@router.post("/files", status_code=201)
async def upload_archive_file(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    data_name: Annotated[str, Form(...)],
    category_id: Annotated[int, Form(...)],
    data_year: Annotated[int, Form(...)],
    data_month: Annotated[int, Form(...)],
    data_type: Annotated[str, Form(...)],
    project_name: Annotated[str | None, Form()] = None,
    company_name: Annotated[str | None, Form()] = None,
    store_id: Annotated[int | None, Form()] = None,
    store_name: Annotated[str | None, Form()] = None,
    data_start_date: Annotated[date | None, Form()] = None,
    data_end_date: Annotated[date | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
    db: AsyncSession = Depends(get_db),
    current_user = require_permission(svc.PERM_UPLOAD),
):
    ip_address, user_agent = _client_meta(request)
    try:
        return await svc.save_archive(
            db,
            user=current_user,
            upload=file,
            data_name=data_name,
            category_id=category_id,
            project_name=project_name,
            company_name=company_name,
            store_id=store_id,
            store_name=store_name,
            data_year=data_year,
            data_month=data_month,
            data_start_date=data_start_date,
            data_end_date=data_end_date,
            data_type=data_type,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except (ValueError, LookupError, RuntimeError) as exc:
        raise _http_error(exc)


@router.patch("/files/{file_id}")
async def update_archive_file(
    file_id: int,
    body: ArchiveUpdateBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user = require_permission(svc.PERM_UPDATE),
):
    ip_address, user_agent = _client_meta(request)
    try:
        return await svc.update_archive(
            db,
            file_id=file_id,
            user=current_user,
            values=body.model_dump(exclude_unset=True),
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except (ValueError, LookupError) as exc:
        raise _http_error(exc)


@router.delete("/files/{file_id}")
async def delete_archive_file(
    file_id: int,
    body: DeleteArchiveBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user = require_permission(svc.PERM_DELETE),
):
    ip_address, user_agent = _client_meta(request)
    try:
        return await svc.soft_delete_archive(
            db,
            file_id=file_id,
            reason=body.reason,
            user=current_user,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except (ValueError, LookupError) as exc:
        raise _http_error(exc)


@router.post("/files/{file_id}/restore")
async def restore_archive_file(
    file_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user = require_permission(svc.PERM_DELETE),
):
    ip_address, user_agent = _client_meta(request)
    try:
        return await svc.restore_archive(
            db,
            file_id=file_id,
            user=current_user,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except (ValueError, LookupError) as exc:
        raise _http_error(exc)


@router.get("/files/{file_id}/download")
async def download_archive_file(
    file_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user = require_permission(svc.PERM_DOWNLOAD),
):
    ip_address, user_agent = _client_meta(request)
    try:
        record, prepared = await svc.prepare_download(
            db,
            file_id=file_id,
            user=current_user,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except LookupError as exc:
        raise _http_error(exc)
    except FileNotFoundError:
        raise HTTPException(status_code=410, detail="存档物理文件不存在")
    background = (
        BackgroundTask(prepared.path.unlink, missing_ok=True) if prepared.temporary else None
    )
    return FileResponse(
        path=prepared.path,
        media_type=record.mime_type,
        filename=record.original_filename,
        background=background,
    )


@router.get("/files/{file_id}/logs")
async def archive_operations(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    _ = require_permission(svc.PERM_VIEW),
):
    try:
        return {"rows": await svc.list_operations(db, file_id)}
    except LookupError as exc:
        raise _http_error(exc)


@router.get("/categories/tree")
async def categories_tree(
    db: AsyncSession = Depends(get_db),
    _ = require_permission(svc.PERM_VIEW),
):
    return {"rows": await svc.get_category_tree(db)}


@router.get("/categories/manage-tree")
async def categories_manage_tree(
    db: AsyncSession = Depends(get_db),
    _ = require_permission(svc.PERM_CATEGORY),
):
    return {"rows": await svc.get_category_tree(db, include_inactive=True)}


@router.post("/categories", status_code=201)
async def create_archive_category(
    body: CategoryCreateBody,
    db: AsyncSession = Depends(get_db),
    current_user = require_permission(svc.PERM_CATEGORY),
):
    try:
        return await svc.create_category(db, user=current_user, **body.model_dump())
    except ValueError as exc:
        raise _http_error(exc)


@router.patch("/categories/{category_id}")
async def update_archive_category(
    category_id: int,
    body: CategoryUpdateBody,
    db: AsyncSession = Depends(get_db),
    current_user = require_permission(svc.PERM_CATEGORY),
):
    try:
        return await svc.update_category(
            db,
            category_id=category_id,
            user=current_user,
            **body.model_dump(exclude_unset=True),
        )
    except (ValueError, LookupError) as exc:
        raise _http_error(exc)


@router.delete("/categories/{category_id}")
async def deactivate_archive_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = require_permission(svc.PERM_CATEGORY),
):
    try:
        return await svc.deactivate_category(
            db, category_id=category_id, user=current_user
        )
    except (ValueError, LookupError) as exc:
        raise _http_error(exc)


@router.get("/options")
async def archive_options(
    db: AsyncSession = Depends(get_db),
    _ = require_permission(svc.PERM_VIEW),
):
    return await svc.get_options(db)
