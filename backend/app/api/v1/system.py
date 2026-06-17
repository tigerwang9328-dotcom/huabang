"""系统管理API（用户/角色/权限/字典）"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from typing import Optional
from pydantic import BaseModel
from app.core.database import get_db
from app.api.v1.deps import require_permission, get_current_user
from app.core.security import get_password_hash
from app.models.sys import SysUser, SysRole, SysUserRole, SysDepartment, SysMenu, SysParam
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/system", tags=["系统管理"])


class UserCreateRequest(BaseModel):
    username: str
    password: str
    real_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    dept_id: Optional[int] = None
    store_code: Optional[str] = None
    role_ids: list[int] = []


class UserUpdateRequest(BaseModel):
    real_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    dept_id: Optional[int] = None
    store_code: Optional[str] = None
    status: Optional[int] = None
    role_ids: Optional[list[int]] = None


# ---- 用户管理 ----
@router.get("/users", response_model=ApiResponse)
async def list_users(
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    dept_id: Optional[int] = None,
    status: Optional[int] = None,
    current_user: SysUser = Depends(require_permission("system:user:view")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SysUser).where(SysUser.is_deleted == False).order_by(SysUser.id)
    if keyword:
        stmt = stmt.where(
            (SysUser.username.ilike(f"%{keyword}%")) |
            (SysUser.real_name.ilike(f"%{keyword}%"))
        )
    if dept_id:
        stmt = stmt.where(SysUser.dept_id == dept_id)
    if status is not None:
        stmt = stmt.where(SysUser.status == status)

    count_result = await db.execute(select(func.count()).select_from(SysUser).where(SysUser.is_deleted == False))
    total = count_result.scalar()
    result = await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    users = result.scalars().all()

    return ApiResponse.ok(data={
        "total": total,
        "items": [
            {
                "id": u.id,
                "username": u.username,
                "real_name": u.real_name,
                "phone": u.phone,
                "email": u.email,
                "dept_id": u.dept_id,
                "store_code": u.store_code,
                "status": u.status,
                "is_admin": u.is_admin,
                "last_login_at": str(u.last_login_at) if u.last_login_at else None,
                "created_at": str(u.created_at),
            }
            for u in users
        ],
    })


@router.post("/users", response_model=ApiResponse)
async def create_user(
    body: UserCreateRequest,
    current_user: SysUser = Depends(require_permission("system:user:create")),
    db: AsyncSession = Depends(get_db),
):
    exists = await db.execute(select(SysUser.id).where(SysUser.username == body.username))
    if exists.scalar_one_or_none():
        return ApiResponse.fail(f"用户名 {body.username} 已存在")

    user = SysUser(
        username=body.username,
        password_hash=get_password_hash(body.password),
        real_name=body.real_name,
        phone=body.phone,
        email=body.email,
        dept_id=body.dept_id,
        store_code=body.store_code,
        status=1,
    )
    db.add(user)
    await db.flush()

    for role_id in body.role_ids:
        db.add(SysUserRole(user_id=user.id, role_id=role_id))

    return ApiResponse.ok(data={"id": user.id}, message="用户创建成功")


@router.put("/users/{user_id}", response_model=ApiResponse)
async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    current_user: SysUser = Depends(require_permission("system:user:update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SysUser).where(SysUser.id == user_id, SysUser.is_deleted == False))
    user = result.scalar_one_or_none()
    if not user:
        return ApiResponse.fail("用户不存在", code=404)

    if body.real_name is not None:
        user.real_name = body.real_name
    if body.phone is not None:
        user.phone = body.phone
    if body.email is not None:
        user.email = body.email
    if body.dept_id is not None:
        user.dept_id = body.dept_id
    if body.store_code is not None:
        user.store_code = body.store_code
    if body.status is not None:
        user.status = body.status

    if body.role_ids is not None:
        await db.execute(delete(SysUserRole).where(SysUserRole.user_id == user_id))
        for role_id in body.role_ids:
            db.add(SysUserRole(user_id=user_id, role_id=role_id))

    return ApiResponse.ok(message="用户信息更新成功")


@router.delete("/users/{user_id}", response_model=ApiResponse)
async def delete_user(
    user_id: int,
    current_user: SysUser = Depends(require_permission("system:user:delete")),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        return ApiResponse.fail("不能删除自己")
    result = await db.execute(select(SysUser).where(SysUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return ApiResponse.fail("用户不存在", code=404)
    user.is_deleted = True
    return ApiResponse.ok(message="用户已删除")


# ---- 角色管理 ----
@router.get("/roles", response_model=ApiResponse)
async def list_roles(
    current_user: SysUser = Depends(require_permission("system:role:view")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SysRole).order_by(SysRole.sort_order))
    roles = result.scalars().all()
    return ApiResponse.ok(data=[
        {"id": r.id, "name": r.name, "code": r.code, "description": r.description,
         "data_scope": r.data_scope, "status": r.status}
        for r in roles
    ])


# ---- 系统参数 ----
@router.get("/params", response_model=ApiResponse)
async def list_params(
    current_user: SysUser = Depends(require_permission("system:param:view")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SysParam).order_by(SysParam.param_key))
    params = result.scalars().all()
    return ApiResponse.ok(data=[
        {"id": p.id, "param_key": p.param_key, "param_value": p.param_value,
         "description": p.description, "is_system": p.is_system}
        for p in params
    ])
