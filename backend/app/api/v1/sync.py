"""百盛/金蝶数据同步API（Excel导入为主）"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, text
from typing import Optional
from datetime import datetime, timezone
from app.core.database import get_db
from app.api.v1.deps import require_permission
from app.models.sys import SysUser
from app.models.log import LogDataSync
from app.schemas.common import ApiResponse, PageQuery
from app.services.baison_import import BaisonImportService, FIELD_MAPPING
import logging
import pandas as pd
import io

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sync", tags=["数据同步"])

ALLOWED_TYPES = {"sales_order", "sales_detail", "return_order", "return_detail",
                 "inventory", "member", "employee", "store", "product", "sku"}

ODS_TABLE_MAP = {
    "sales_order": "ods.ods_baison_sales_order",
    "sales_detail": "ods.ods_baison_sales_detail",
    "return_order": "ods.ods_baison_return_order",
    "return_detail": "ods.ods_baison_return_detail",
    "inventory": "ods.ods_baison_inventory",
    "member": "ods.ods_baison_member",
    "employee": "ods.ods_baison_employee",
    "store": "ods.ods_baison_store",
    "product": "ods.ods_baison_product",
    "sku": "ods.ods_baison_sku",
}


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
        message=f"导入完成: 成功{result.get('success_rows', 0)}行，"
                f"重复{result.get('duplicate_rows', 0)}行，"
                f"失败{result.get('error_rows', 0)}行",
    )


@router.post("/preview", response_model=ApiResponse)
async def preview_excel(
    data_type: str = Form(...),
    file: UploadFile = File(...),
    current_user: SysUser = Depends(require_permission("sync:import")),
):
    """预览Excel字段，返回列名、示例数据、字段映射建议（不写入数据库）"""
    if data_type not in ALLOWED_TYPES:
        return ApiResponse.fail(f"不支持的数据类型: {data_type}")

    filename = file.filename or ""
    if not any(filename.lower().endswith(ext) for ext in [".xlsx", ".xls", ".csv"]):
        return ApiResponse.fail("仅支持 .xlsx .xls .csv 格式")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        return ApiResponse.fail("预览文件不超过10MB")

    try:
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content), nrows=10)
        else:
            df = pd.read_excel(io.BytesIO(content), nrows=10)

        excel_cols = list(df.columns)
        mapping_config = FIELD_MAPPING.get(data_type, {})

        # 映射分析
        matched = {}
        unmatched_excel = []
        for col in excel_cols:
            sys_field = mapping_config.get(str(col).strip())
            if sys_field:
                matched[str(col)] = sys_field
            else:
                unmatched_excel.append(str(col))

        mapped_sys_fields = set(matched.values())
        required_fields = set(mapping_config.values())
        missing_sys_fields = list(required_fields - mapped_sys_fields)

        # 示例数据（前3行）
        sample_rows = []
        for _, row in df.head(3).iterrows():
            sample_rows.append({str(k): (str(v) if pd.notna(v) else None) for k, v in row.items()})

        return ApiResponse.ok(data={
            "data_type": data_type,
            "filename": filename,
            "total_cols": len(excel_cols),
            "excel_columns": excel_cols,
            "field_mapping": matched,
            "unmatched_excel_cols": unmatched_excel,
            "missing_system_fields": missing_sys_fields,
            "mapping_coverage": round(len(matched) / max(len(mapping_config), 1) * 100, 1),
            "sample_rows": sample_rows,
            "tip": "mapping_coverage<80%时建议检查Excel列名是否与系统一致",
        })
    except Exception as e:
        return ApiResponse.fail(f"预览失败: {str(e)[:200]}")


@router.post("/rollback/{batch_no}", response_model=ApiResponse)
async def rollback_batch(
    batch_no: str,
    current_user: SysUser = Depends(require_permission("sync:import")),
    db: AsyncSession = Depends(get_db),
):
    """回滚指定批次导入的数据（从ODS表删除该batch_no的记录，并更新日志状态）"""
    # 查找批次日志
    log_r = await db.execute(
        select(LogDataSync).where(LogDataSync.batch_no == batch_no)
    )
    sync_log = log_r.scalar_one_or_none()
    if not sync_log:
        return ApiResponse.fail(f"批次号 {batch_no} 不存在")

    if sync_log.status == "rolled_back":
        return ApiResponse.fail(f"批次 {batch_no} 已回滚，不可重复操作")

    data_type = sync_log.data_type
    table_name = ODS_TABLE_MAP.get(data_type)
    if not table_name:
        return ApiResponse.fail(f"数据类型 {data_type} 不支持回滚")

    try:
        result = await db.execute(
            text(f"DELETE FROM {table_name} WHERE batch_no = :bn"),
            {"bn": batch_no}
        )
        deleted_rows = result.rowcount

        sync_log.status = "rolled_back"
        sync_log.error_detail = f"[ROLLBACK] 由 {current_user.username} 于 {datetime.now().isoformat()} 回滚，删除 {deleted_rows} 行"
        await db.commit()

        logger.info(f"批次 {batch_no} 回滚成功，删除 {deleted_rows} 行，操作人: {current_user.username}")
        return ApiResponse.ok(
            data={"batch_no": batch_no, "deleted_rows": deleted_rows, "data_type": data_type},
            message=f"回滚成功，已删除 {deleted_rows} 行数据"
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"回滚失败 {batch_no}: {e}")
        return ApiResponse.fail(f"回滚失败: {str(e)[:200]}")


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
