"""百盛/金蝶数据同步API（Excel导入为主）"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional
from app.core.database import get_db
from app.api.v1.deps import require_permission
from app.models.sys import SysUser
from app.models.log import LogDataSync
from app.schemas.common import ApiResponse, PageQuery
from app.services.baison_import import BaisonImportService
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sync", tags=["数据同步"])

ALLOWED_TYPES = {"sales_order", "sales_detail", "return_order", "return_detail",
                 "inventory", "member", "employee", "store", "product", "sku"}


@router.post("/baison/import-excel", response_model=ApiResponse)
async def import_baison_excel(
    background_tasks: BackgroundTasks,
    data_type: str = Form(..., description="sales_order/inventory/member/store/product/sku等"),
    file: UploadFile = File(...),
    current_user: SysUser = Depends(require_permission("sync:import")),
    db: AsyncSession = Depends(get_db),
):
    """百盛数据Excel导入"""
    if data_type not in ALLOWED_TYPES:
        allowed = ", ".join(ALLOWED_TYPES)
        return ApiResponse.fail(f"不支持的数据类型: {data_type}，支持: {allowed}")

    # 文件类型校验
    filename = file.filename or ""
    if not any(filename.lower().endswith(ext) for ext in [".xlsx", ".xls", ".csv"]):
        return ApiResponse.fail("仅支持 .xlsx .xls .csv 格式")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        return ApiResponse.fail("文件大小不能超过50MB")

    service = BaisonImportService(db)
    result = await service.import_excel(
        data_type=data_type,
        file_content=content,
        filename=filename,
        operator_id=current_user.id,
    )

    return ApiResponse.ok(
        data=result,
        message=f"导入完成: 成功{result.get(success_rows, 0)}行，"
                f"重复{result.get(duplicate_rows, 0)}行，"
                f"失败{result.get(error_rows, 0)}行",
    )


@router.get("/status", response_model=ApiResponse)
async def get_sync_status(
    current_user: SysUser = Depends(require_permission("sync:view")),
    db: AsyncSession = Depends(get_db),
):
    """各数据类型同步状态"""
    result = await db.execute(
        select(LogDataSync)
        .order_by(desc(LogDataSync.start_at))
        .limit(50)
    )
    logs = result.scalars().all()

    # 按 data_type 取最新一条
    latest = {}
    for log in logs:
        key = f"{log.source_system}_{log.data_type}"
        if key not in latest:
            latest[key] = {
                "source_system": log.source_system,
                "data_type": log.data_type,
                "status": log.status,
                "last_sync_at": str(log.start_at) if log.start_at else None,
                "total_rows": log.total_rows,
                "success_rows": log.success_rows,
                "error_rows": log.error_rows,
            }

    return ApiResponse.ok(data=list(latest.values()))


@router.get("/logs", response_model=ApiResponse)
async def get_sync_logs(
    page: int = 1,
    page_size: int = 20,
    source_system: Optional[str] = None,
    data_type: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("sync:view")),
    db: AsyncSession = Depends(get_db),
):
    """同步日志列表"""
    stmt = select(LogDataSync).order_by(desc(LogDataSync.start_at))
    if source_system:
        stmt = stmt.where(LogDataSync.source_system == source_system)
    if data_type:
        stmt = stmt.where(LogDataSync.data_type == data_type)

    total = await db.execute(select(LogDataSync).with_only_columns(
        *[LogDataSync.id.label("count")]
    ))
    logs_result = await db.execute(
        stmt.offset((page - 1) * page_size).limit(page_size)
    )
    logs = logs_result.scalars().all()

    return ApiResponse.ok(data={
        "items": [
            {
                "id": l.id,
                "batch_no": l.batch_no,
                "source_system": l.source_system,
                "data_type": l.data_type,
                "file_name": l.file_name,
                "total_rows": l.total_rows,
                "success_rows": l.success_rows,
                "duplicate_rows": l.duplicate_rows,
                "error_rows": l.error_rows,
                "status": l.status,
                "start_at": str(l.start_at) if l.start_at else None,
                "end_at": str(l.end_at) if l.end_at else None,
                "duration_seconds": l.duration_seconds,
            }
            for l in logs
        ],
        "page": page,
        "page_size": page_size,
    })
