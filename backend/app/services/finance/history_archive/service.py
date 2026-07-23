"""历史数据资产中心业务服务。"""
from __future__ import annotations

import hashlib
import logging
import tempfile
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance.history_archive import (
    DataArchiveCategory,
    DataArchiveFile,
    DataArchiveLog,
)
from app.models.dim import DimStore as Store
from app.models.sys import SysUser as User

from . import repository as repo
from .constants import CATEGORY_STATUSES, DATA_TYPES, FILE_STATUSES, MAX_FILE_SIZE
from .storage import LOCAL_ROOT, PreparedDownload, get_storage
from .validators import (
    clean_text,
    file_extension,
    safe_filename,
    safe_path_segment,
    validate_data_type,
    validate_period,
)

logger = logging.getLogger(__name__)


def _category_path(lineage: list[DataArchiveCategory]) -> list[dict]:
    return [{"id": row.id, "name": row.name, "level": row.level} for row in lineage]


def _storage_key(
    *,
    company_name: str,
    root_category: str,
    year: int,
    month: int,
    original_filename: str,
) -> str:
    filename = safe_filename(original_filename)
    return "/".join(
        (
            safe_path_segment(company_name, "未归属主体"),
            safe_path_segment(root_category, "其他数据"),
            str(year),
            f"{month:02d}",
            f"{uuid4().hex}_{filename}",
        )
    )


async def _spool_upload(upload: UploadFile) -> tuple[Path, int, str, str]:
    LOCAL_ROOT.joinpath(".tmp").mkdir(parents=True, exist_ok=True)
    descriptor, filename = tempfile.mkstemp(prefix="archive_", dir=LOCAL_ROOT / ".tmp")
    path = Path(filename)
    md5_hash = hashlib.md5()
    sha_hash = hashlib.sha256()
    total = 0
    try:
        with open(descriptor, "wb", closefd=True) as target:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_FILE_SIZE:
                    raise ValueError(f"单个文件不能超过{MAX_FILE_SIZE // 1024 // 1024}MB")
                md5_hash.update(chunk)
                sha_hash.update(chunk)
                target.write(chunk)
        if total <= 0:
            raise ValueError("文件不能为空")
        return path, total, md5_hash.hexdigest(), sha_hash.hexdigest()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


async def save_archive(
    db: AsyncSession,
    *,
    user: User,
    upload: UploadFile,
    data_name: str,
    category_id: int,
    project_name: str | None,
    company_name: str | None,
    store_id: int | None,
    store_name: str | None,
    data_year: int,
    data_month: int,
    data_start_date: date | None,
    data_end_date: date | None,
    data_type: str,
    description: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> dict:
    clean_name = clean_text(data_name, maximum=200, required=True)
    clean_company = clean_text(company_name, maximum=255)
    clean_project = clean_text(project_name, maximum=128)
    clean_description = clean_text(description, maximum=4000)
    validate_period(data_year, data_month, data_start_date, data_end_date)
    normalized_type = validate_data_type(data_type)
    original_name = safe_filename(upload.filename or "")
    extension, mime_type = file_extension(original_name)

    lineage = await repo.category_lineage(db, category_id)
    if len(lineage) > 3:
        raise ValueError("当前版本最多支持三级分类")
    root = lineage[0]

    store_snapshot = clean_text(store_name, maximum=128)
    if store_id:
        store = await db.get(Store, store_id)
        if not store:
            raise ValueError("所属店铺不存在")
        store_snapshot = store.store_name

    temp_path, size, md5_value, sha_value = await _spool_upload(upload)
    storage = get_storage()
    key = _storage_key(
        company_name=clean_company,
        root_category=root.name,
        year=data_year,
        month=data_month,
        original_filename=original_name,
    )
    saved = False
    try:
        await storage.save(temp_path, key)
        saved = True
        record = DataArchiveFile(
            data_name=clean_name,
            original_filename=original_name,
            storage_provider=storage.provider,
            storage_key=key,
            file_size=size,
            file_extension=extension,
            mime_type=mime_type,
            md5=md5_value,
            sha256=sha_value,
            category_id=category_id,
            category_root_id=root.id,
            category_path=_category_path(lineage),
            project_name=clean_project or None,
            company_name=clean_company or None,
            store_id=store_id,
            store_name_snapshot=store_snapshot or None,
            data_year=data_year,
            data_month=data_month,
            data_start_date=data_start_date,
            data_end_date=data_end_date,
            data_type=normalized_type,
            description=clean_description or None,
            status="NORMAL",
            uploaded_by=user.id,
        )
        db.add(record)
        await db.flush()
        repo.add_log(
            db,
            file_id=record.id,
            operation_type="UPLOAD",
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            detail={
                "file_name": original_name,
                "file_size": size,
                "md5": md5_value,
                "category_path": record.category_path,
            },
        )
        await db.commit()
        await db.refresh(record)
        return repo.file_to_dict(record, uploader_name=repo.user_display_name(user))
    except Exception:
        await db.rollback()
        if saved:
            await storage.discard_uncommitted(key)
        raise
    finally:
        temp_path.unlink(missing_ok=True)


async def list_archives(db: AsyncSession, **filters) -> dict:
    status = filters.get("status", "NORMAL")
    if status not in FILE_STATUSES:
        raise ValueError("不支持的文件状态")
    data_type = filters.get("data_type")
    if data_type and data_type not in DATA_TYPES:
        raise ValueError("不支持的数据类型")
    month = filters.get("month")
    if month and not 1 <= month <= 12:
        raise ValueError("月份必须在1至12之间")
    return await repo.list_files(db, **filters)


async def get_archive(db: AsyncSession, file_id: int) -> DataArchiveFile | None:
    return await db.get(DataArchiveFile, file_id)


async def get_archive_detail(db: AsyncSession, file_id: int) -> dict | None:
    return await repo.get_file_dict(db, file_id)


async def update_archive(
    db: AsyncSession,
    *,
    file_id: int,
    user: User,
    values: dict,
    ip_address: str | None,
    user_agent: str | None,
) -> dict:
    record = await db.get(DataArchiveFile, file_id)
    if not record:
        raise LookupError("存档文件不存在")
    if record.status != "NORMAL":
        raise ValueError("已删除文件不能修改")

    changed: dict[str, dict] = {}

    def set_value(field: str, value) -> None:
        old = getattr(record, field)
        if old != value:
            changed[field] = {"before": old, "after": value}
            setattr(record, field, value)

    if "data_name" in values:
        set_value("data_name", clean_text(values["data_name"], maximum=200, required=True))
    if "project_name" in values:
        set_value("project_name", clean_text(values["project_name"], maximum=128) or None)
    if "company_name" in values:
        set_value("company_name", clean_text(values["company_name"], maximum=255) or None)
    if "description" in values:
        set_value("description", clean_text(values["description"], maximum=4000) or None)
    if "data_type" in values:
        set_value("data_type", validate_data_type(values["data_type"]))
    if "data_year" in values or "data_month" in values or "data_start_date" in values or "data_end_date" in values:
        year = values.get("data_year", record.data_year)
        month = values.get("data_month", record.data_month)
        start = values.get("data_start_date", record.data_start_date)
        end = values.get("data_end_date", record.data_end_date)
        validate_period(year, month, start, end)
        set_value("data_year", year)
        set_value("data_month", month)
        set_value("data_start_date", start)
        set_value("data_end_date", end)
    if "store_id" in values:
        store_id = values["store_id"]
        store_name = None
        if store_id:
            store = await db.get(Store, store_id)
            if not store:
                raise ValueError("所属店铺不存在")
            store_name = store.store_name
        set_value("store_id", store_id)
        set_value("store_name_snapshot", store_name)
    if "category_id" in values:
        lineage = await repo.category_lineage(db, values["category_id"])
        if len(lineage) > 3:
            raise ValueError("当前版本最多支持三级分类")
        set_value("category_id", values["category_id"])
        set_value("category_root_id", lineage[0].id)
        set_value("category_path", _category_path(lineage))

    if changed:
        record.updated_at = datetime.now()
        repo.add_log(
            db,
            file_id=record.id,
            operation_type="UPDATE",
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            detail={"changes": changed},
        )
        await db.commit()
    return (await repo.get_file_dict(db, file_id)) or {}


async def soft_delete_archive(
    db: AsyncSession,
    *,
    file_id: int,
    reason: str,
    user: User,
    ip_address: str | None,
    user_agent: str | None,
) -> dict:
    record = await db.get(DataArchiveFile, file_id)
    if not record:
        raise LookupError("存档文件不存在")
    if record.status != "NORMAL":
        raise ValueError("文件已经在回收站")
    clean_reason = clean_text(reason, maximum=1000, required=True)
    record.status = "DELETED"
    record.deleted_at = datetime.now()
    record.deleted_by = user.id
    record.delete_reason = clean_reason
    record.updated_at = datetime.now()
    repo.add_log(
        db,
        file_id=record.id,
        operation_type="DELETE",
        user=user,
        ip_address=ip_address,
        user_agent=user_agent,
        detail={"reason": clean_reason, "physical_file_deleted": False},
    )
    await db.commit()
    return (await repo.get_file_dict(db, file_id)) or {}


async def restore_archive(
    db: AsyncSession,
    *,
    file_id: int,
    user: User,
    ip_address: str | None,
    user_agent: str | None,
) -> dict:
    record = await db.get(DataArchiveFile, file_id)
    if not record:
        raise LookupError("存档文件不存在")
    if record.status != "DELETED":
        raise ValueError("文件不在回收站")
    previous_reason = record.delete_reason
    record.status = "NORMAL"
    record.deleted_at = None
    record.deleted_by = None
    record.delete_reason = None
    record.updated_at = datetime.now()
    repo.add_log(
        db,
        file_id=record.id,
        operation_type="RESTORE",
        user=user,
        ip_address=ip_address,
        user_agent=user_agent,
        detail={"previous_delete_reason": previous_reason or ""},
    )
    await db.commit()
    return (await repo.get_file_dict(db, file_id)) or {}


async def prepare_download(
    db: AsyncSession,
    *,
    file_id: int,
    user: User,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[DataArchiveFile, PreparedDownload]:
    record = await db.get(DataArchiveFile, file_id)
    if not record:
        raise LookupError("存档文件不存在")
    storage = get_storage(record.storage_provider)
    prepared = await storage.prepare_download(record.storage_key)
    repo.add_log(
        db,
        file_id=record.id,
        operation_type="DOWNLOAD",
        user=user,
        ip_address=ip_address,
        user_agent=user_agent,
        detail={"file_name": record.original_filename, "status": record.status},
    )
    await db.commit()
    return record, prepared


async def list_operations(db: AsyncSession, file_id: int) -> list[dict]:
    if not await db.get(DataArchiveFile, file_id):
        raise LookupError("存档文件不存在")
    return await repo.list_logs(db, file_id)


async def get_category_tree(db: AsyncSession, *, include_inactive: bool = False) -> list[dict]:
    return await repo.category_tree(db, include_inactive=include_inactive)


async def create_category(
    db: AsyncSession,
    *,
    name: str,
    parent_id: int,
    sort_order: int,
    user: User,
) -> dict:
    clean_name = clean_text(name, maximum=128, required=True)
    parent = await db.get(DataArchiveCategory, parent_id)
    if not parent or parent.status != "ACTIVE":
        raise ValueError("上级分类不存在或已停用")
    if parent.level >= 3:
        raise ValueError("当前版本最多支持三级分类")
    duplicate = await db.execute(
        select(DataArchiveCategory.id).where(
            DataArchiveCategory.parent_id == parent_id,
            DataArchiveCategory.name == clean_name,
        )
    )
    if duplicate.scalar_one_or_none():
        raise ValueError("同级分类名称已存在")
    record = DataArchiveCategory(
        parent_id=parent_id,
        name=clean_name,
        level=parent.level + 1,
        sort_order=sort_order,
        is_fixed=False,
        status="ACTIVE",
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return repo.category_to_dict(record)


async def update_category(
    db: AsyncSession,
    *,
    category_id: int,
    name: str | None,
    sort_order: int | None,
    user: User,
) -> dict:
    record = await db.get(DataArchiveCategory, category_id)
    if not record:
        raise LookupError("分类不存在")
    if record.is_fixed and name is not None and clean_text(name, maximum=128) != record.name:
        raise ValueError("固定一级分类不能改名")
    if name is not None:
        clean_name = clean_text(name, maximum=128, required=True)
        duplicate = await db.execute(
            select(DataArchiveCategory.id).where(
                DataArchiveCategory.parent_id == record.parent_id,
                DataArchiveCategory.name == clean_name,
                DataArchiveCategory.id != record.id,
            )
        )
        if duplicate.scalar_one_or_none():
            raise ValueError("同级分类名称已存在")
        record.name = clean_name
    if sort_order is not None:
        record.sort_order = sort_order
    record.updated_by = user.id
    record.updated_at = datetime.now()
    await db.commit()
    await db.refresh(record)
    return repo.category_to_dict(record)


async def deactivate_category(db: AsyncSession, *, category_id: int, user: User) -> dict:
    record = await db.get(DataArchiveCategory, category_id)
    if not record:
        raise LookupError("分类不存在")
    if record.is_fixed:
        raise ValueError("固定一级分类不能停用")
    child_count = int(
        (
            await db.execute(
                select(func.count(DataArchiveCategory.id)).where(
                    DataArchiveCategory.parent_id == category_id,
                    DataArchiveCategory.status == "ACTIVE",
                )
            )
        ).scalar()
        or 0
    )
    file_count = int(
        (
            await db.execute(
                select(func.count(DataArchiveFile.id)).where(
                    DataArchiveFile.category_id == category_id
                )
            )
        ).scalar()
        or 0
    )
    if child_count or file_count:
        raise ValueError("分类存在子分类或已归档文件，不能停用")
    record.status = "INACTIVE"
    record.updated_by = user.id
    record.updated_at = datetime.now()
    await db.commit()
    return repo.category_to_dict(record)


async def get_options(db: AsyncSession) -> dict:
    return await repo.option_values(db)


async def get_summary(db: AsyncSession) -> dict:
    totals = (
        await db.execute(
            select(
                func.count(DataArchiveFile.id),
                func.coalesce(func.sum(DataArchiveFile.file_size), 0),
                func.count(func.distinct(DataArchiveFile.data_year)),
            ).where(DataArchiveFile.status == "NORMAL")
        )
    ).one()
    years = await db.execute(
        select(DataArchiveFile.data_year)
        .where(DataArchiveFile.status == "NORMAL")
        .distinct()
        .order_by(DataArchiveFile.data_year)
    )
    category_count = int(
        (
            await db.execute(
                select(func.count(DataArchiveCategory.id)).where(
                    DataArchiveCategory.status == "ACTIVE"
                )
            )
        ).scalar()
        or 0
    )
    distribution = await db.execute(
        select(
            DataArchiveCategory.id,
            DataArchiveCategory.name,
            func.count(DataArchiveFile.id),
        )
        .outerjoin(
            DataArchiveFile,
            (DataArchiveFile.category_root_id == DataArchiveCategory.id)
            & (DataArchiveFile.status == "NORMAL"),
        )
        .where(DataArchiveCategory.level == 1, DataArchiveCategory.status == "ACTIVE")
        .group_by(DataArchiveCategory.id, DataArchiveCategory.name, DataArchiveCategory.sort_order)
        .order_by(DataArchiveCategory.sort_order, DataArchiveCategory.id)
    )
    recent_uploads = await repo.list_files(db, status="NORMAL", page=1, page_size=5)
    recent_download_result = await db.execute(
        select(DataArchiveLog, DataArchiveFile)
        .join(DataArchiveFile, DataArchiveFile.id == DataArchiveLog.file_id)
        .where(DataArchiveLog.operation_type == "DOWNLOAD")
        .order_by(DataArchiveLog.operation_time.desc(), DataArchiveLog.id.desc())
        .limit(5)
    )
    return {
        "total_files": int(totals[0] or 0),
        "total_size": int(totals[1] or 0),
        "covered_year_count": int(totals[2] or 0),
        "covered_years": list(years.scalars().all()),
        "category_count": category_count,
        "category_distribution": [
            {"category_id": item_id, "name": name, "file_count": int(count)}
            for item_id, name, count in distribution.all()
        ],
        "recent_uploads": recent_uploads["rows"],
        "recent_downloads": [
            {
                "file_id": file_row.id,
                "data_name": file_row.data_name,
                "original_filename": file_row.original_filename,
                "user_name": log_row.operation_user_name or "",
                "operation_time": str(log_row.operation_time),
            }
            for log_row, file_row in recent_download_result.all()
        ],
    }


async def purge_expired_archives(now: datetime | None = None) -> int:
    """兼容旧调度入口。新规则禁止物理删除，因此固定不执行清理。"""
    logger.info("历史数据资产中心采用永久软删除，跳过物理文件清理")
    return 0
