"""历史数据资产中心数据库查询层。"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance.history_archive import (
    DataArchiveCategory,
    DataArchiveFile,
    DataArchiveLog,
)
from app.models.dim import DimStore as Store
from app.models.sys import SysUser as User


def user_display_name(user: User) -> str:
    return user.real_name or user.username or str(user.id)


def category_to_dict(row: DataArchiveCategory) -> dict:
    return {
        "id": row.id,
        "parent_id": row.parent_id,
        "name": row.name,
        "level": row.level,
        "sort_order": row.sort_order,
        "is_fixed": bool(row.is_fixed),
        "status": row.status,
        "created_at": str(row.created_at) if row.created_at else None,
        "updated_at": str(row.updated_at) if row.updated_at else None,
    }


async def category_tree(db: AsyncSession, *, include_inactive: bool = False) -> list[dict]:
    query = select(DataArchiveCategory)
    if not include_inactive:
        query = query.where(DataArchiveCategory.status == "ACTIVE")
    result = await db.execute(
        query.order_by(
            DataArchiveCategory.level,
            DataArchiveCategory.sort_order,
            DataArchiveCategory.id,
        )
    )
    nodes = [category_to_dict(row) | {"children": []} for row in result.scalars().all()]
    by_id = {node["id"]: node for node in nodes}
    roots: list[dict] = []
    for node in nodes:
        parent = by_id.get(node["parent_id"])
        if parent:
            parent["children"].append(node)
        else:
            roots.append(node)
    return roots


async def category_lineage(
    db: AsyncSession,
    category_id: int,
    *,
    require_active: bool = True,
) -> list[DataArchiveCategory]:
    lineage: list[DataArchiveCategory] = []
    seen: set[int] = set()
    current = await db.get(DataArchiveCategory, category_id)
    while current:
        if current.id in seen:
            raise ValueError("分类树存在循环引用")
        if require_active and current.status != "ACTIVE":
            raise ValueError("所选分类已停用")
        seen.add(current.id)
        lineage.append(current)
        current = await db.get(DataArchiveCategory, current.parent_id) if current.parent_id else None
    if not lineage:
        raise LookupError("数据分类不存在")
    lineage.reverse()
    return lineage


async def descendant_category_ids(db: AsyncSession, category_id: int) -> list[int]:
    result = await db.execute(select(DataArchiveCategory.id, DataArchiveCategory.parent_id))
    children: dict[int | None, list[int]] = {}
    for item_id, parent_id in result.all():
        children.setdefault(parent_id, []).append(item_id)
    found: list[int] = []
    pending = [category_id]
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.append(current)
        pending.extend(children.get(current, []))
    return found


def file_to_dict(row: DataArchiveFile, *, uploader_name: str = "") -> dict:
    path = row.category_path or []
    return {
        "id": row.id,
        "data_name": row.data_name,
        "original_filename": row.original_filename,
        "file_size": int(row.file_size or 0),
        "file_extension": row.file_extension,
        "mime_type": row.mime_type,
        "md5": row.md5,
        "sha256": row.sha256,
        "storage_provider": row.storage_provider,
        "category_id": row.category_id,
        "category_root_id": row.category_root_id,
        "category_path": path,
        "category_path_text": " / ".join(item.get("name", "") for item in path),
        "project_name": row.project_name or "",
        "company_name": row.company_name or "",
        "store_id": row.store_id,
        "store_name": row.store_name_snapshot or "",
        "data_year": row.data_year,
        "data_month": row.data_month,
        "data_start_date": str(row.data_start_date) if row.data_start_date else None,
        "data_end_date": str(row.data_end_date) if row.data_end_date else None,
        "data_type": row.data_type,
        "description": row.description or "",
        "status": row.status,
        "uploaded_by": row.uploaded_by,
        "uploader_name": uploader_name,
        "created_at": str(row.created_at) if row.created_at else None,
        "updated_at": str(row.updated_at) if row.updated_at else None,
        "deleted_at": str(row.deleted_at) if row.deleted_at else None,
        "deleted_by": row.deleted_by,
        "delete_reason": row.delete_reason or "",
    }


async def list_files(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    category_id: int | None = None,
    project_name: str | None = None,
    company_name: str | None = None,
    store_id: int | None = None,
    year: int | None = None,
    month: int | None = None,
    uploader: str | None = None,
    data_type: str | None = None,
    status: str = "NORMAL",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    conditions = [DataArchiveFile.status == status]
    if keyword:
        pattern = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                DataArchiveFile.data_name.ilike(pattern),
                DataArchiveFile.original_filename.ilike(pattern),
                DataArchiveFile.description.ilike(pattern),
            )
        )
    if category_id:
        ids = await descendant_category_ids(db, category_id)
        conditions.append(DataArchiveFile.category_id.in_(ids))
    if project_name:
        conditions.append(DataArchiveFile.project_name == project_name)
    if company_name:
        conditions.append(DataArchiveFile.company_name == company_name)
    if store_id:
        conditions.append(DataArchiveFile.store_id == store_id)
    if year:
        conditions.append(DataArchiveFile.data_year == year)
    if month:
        conditions.append(DataArchiveFile.data_month == month)
    if data_type:
        conditions.append(DataArchiveFile.data_type == data_type)
    if uploader:
        pattern = f"%{uploader.strip()}%"
        conditions.append(or_(User.real_name.ilike(pattern), User.username.ilike(pattern)))

    base = (
        select(DataArchiveFile, User.real_name, User.username)
        .outerjoin(User, User.id == DataArchiveFile.uploaded_by)
        .where(*conditions)
    )
    count_query = (
        select(func.count(DataArchiveFile.id))
        .outerjoin(User, User.id == DataArchiveFile.uploaded_by)
        .where(*conditions)
    )
    total = int((await db.execute(count_query)).scalar() or 0)
    result = await db.execute(
        base.order_by(DataArchiveFile.created_at.desc(), DataArchiveFile.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = [
        file_to_dict(row, uploader_name=real_name or username or "")
        for row, real_name, username in result.all()
    ]
    return {"rows": rows, "total": total, "page": page, "page_size": page_size}


async def get_file_dict(db: AsyncSession, file_id: int) -> dict | None:
    result = await db.execute(
        select(DataArchiveFile, User.real_name, User.username)
        .outerjoin(User, User.id == DataArchiveFile.uploaded_by)
        .where(DataArchiveFile.id == file_id)
    )
    item = result.first()
    if not item:
        return None
    row, real_name, username = item
    return file_to_dict(row, uploader_name=real_name or username or "")


def add_log(
    db: AsyncSession,
    *,
    file_id: int,
    operation_type: str,
    user: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
    detail: dict | None = None,
) -> None:
    db.add(
        DataArchiveLog(
            file_id=file_id,
            operation_type=operation_type,
            operation_user_id=user.id,
            operation_user_name=user_display_name(user),
            ip_address=(ip_address or "")[:64] or None,
            user_agent=(user_agent or "")[:512] or None,
            change_detail=detail or {},
        )
    )


async def list_logs(db: AsyncSession, file_id: int) -> list[dict]:
    result = await db.execute(
        select(DataArchiveLog)
        .where(DataArchiveLog.file_id == file_id)
        .order_by(DataArchiveLog.operation_time.desc(), DataArchiveLog.id.desc())
    )
    return [
        {
            "id": row.id,
            "operation_type": row.operation_type,
            "operation_user_id": row.operation_user_id,
            "operation_user_name": row.operation_user_name or "",
            "operation_time": str(row.operation_time) if row.operation_time else None,
            "ip_address": row.ip_address or "",
            "user_agent": row.user_agent or "",
            "change_detail": row.change_detail or {},
        }
        for row in result.scalars().all()
    ]


async def option_values(db: AsyncSession) -> dict:
    async def distinct_values(column):
        result = await db.execute(
            select(column)
            .where(column.is_not(None), column != "")
            .distinct()
            .order_by(column)
        )
        return list(result.scalars().all())

    stores = await db.execute(
        select(Store.id, Store.store_name)
        .where(Store.status == 'active')
        .order_by(Store.store_name)
    )
    uploaders = await db.execute(
        select(User.id, User.real_name, User.username)
        .join(DataArchiveFile, DataArchiveFile.uploaded_by == User.id)
        .distinct()
        .order_by(User.real_name, User.username)
    )
    return {
        "projects": await distinct_values(DataArchiveFile.project_name),
        "companies": await distinct_values(DataArchiveFile.company_name),
        "stores": [{"id": item_id, "name": name} for item_id, name in stores.all()],
        "uploaders": [
            {"id": item_id, "name": real_name or username or str(item_id)}
            for item_id, real_name, username in uploaders.all()
        ],
    }
