"""系统管理API（用户/角色/权限/字典）"""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from typing import Optional
from pydantic import BaseModel
from app.core.database import get_db
from app.api.v1.deps import require_permission, get_current_user
from app.core.security import get_password_hash
from app.models.sys import SysUser, SysRole, SysUserRole, SysDepartment, SysMenu, SysParam, SysPermission, SysRolePermission
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


class RegisterAuditRequest(BaseModel):
    reason: Optional[str] = None


class UserUpdateRequest(BaseModel):
    real_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    dept_id: Optional[int] = None
    store_code: Optional[str] = None
    status: Optional[int] = None
    role_ids: Optional[list[int]] = None




# ---- 注册审核 ----
def _load_register_applications(param: Optional[SysParam]) -> list[dict]:
    if not param or not param.param_value:
        return []
    try:
        value = json.loads(param.param_value)
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _safe_application(item: dict) -> dict:
    safe = dict(item)
    safe.pop("password_hash", None)
    return safe


@router.get("/register-applications", response_model=ApiResponse)
async def list_register_applications(
    status: Optional[str] = Query(None, description="pending/approved/rejected"),
    current_user: SysUser = Depends(require_permission("system:register:review")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SysParam).where(SysParam.param_key == "register_applications"))
    param = result.scalar_one_or_none()
    applications = _load_register_applications(param)
    if status:
        applications = [a for a in applications if a.get("status") == status]
    return ApiResponse.ok(data={
        "total": len(applications),
        "items": [_safe_application(a) for a in applications],
    })


@router.post("/register-applications/{application_id}/approve", response_model=ApiResponse)
async def approve_register_application(
    application_id: str,
    current_user: SysUser = Depends(require_permission("system:register:review")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SysParam).where(SysParam.param_key == "register_applications"))
    param = result.scalar_one_or_none()
    applications = _load_register_applications(param)
    app_item = next((a for a in applications if a.get("id") == application_id), None)
    if not app_item:
        return ApiResponse.fail("申请不存在", code=404)
    if app_item.get("status") != "pending":
        return ApiResponse.fail("该申请已处理，不能重复审核")

    username = (app_item.get("username") or "").strip()
    if not username:
        return ApiResponse.fail("申请缺少用户名，无法创建账号")
    exists = await db.execute(select(SysUser.id).where(SysUser.username == username, SysUser.is_deleted == False))
    if exists.scalar_one_or_none():
        return ApiResponse.fail("该用户名已存在，无法通过申请")

    role_result = await db.execute(select(SysRole).where(SysRole.code == app_item.get("apply_role"), SysRole.status == 1))
    role = role_result.scalar_one_or_none()
    if not role:
        return ApiResponse.fail("申请岗位不存在或已禁用，请先配置角色")

    user = SysUser(
        username=username,
        password_hash=app_item.get("password_hash") or get_password_hash("Hb@123456"),
        real_name=app_item.get("real_name") or username,
        phone=app_item.get("phone"),
        store_code=(app_item.get("store_code") or None),
        status=1,
        must_change_password=False,
    )
    db.add(user)
    await db.flush()
    db.add(SysUserRole(user_id=user.id, role_id=role.id))

    now = datetime.now(timezone.utc).isoformat()
    app_item["status"] = "approved"
    app_item["approved_user_id"] = int(user.id)
    app_item["reviewed_by"] = current_user.username
    app_item["reviewed_at"] = now
    param.param_value = json.dumps(applications, ensure_ascii=False)
    db.add(param)
    return ApiResponse.ok(data={"user_id": int(user.id)}, message="已通过申请并创建账号")


@router.post("/register-applications/{application_id}/reject", response_model=ApiResponse)
async def reject_register_application(
    application_id: str,
    body: RegisterAuditRequest,
    current_user: SysUser = Depends(require_permission("system:register:review")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SysParam).where(SysParam.param_key == "register_applications"))
    param = result.scalar_one_or_none()
    applications = _load_register_applications(param)
    app_item = next((a for a in applications if a.get("id") == application_id), None)
    if not app_item:
        return ApiResponse.fail("申请不存在", code=404)
    if app_item.get("status") != "pending":
        return ApiResponse.fail("该申请已处理，不能重复审核")
    app_item["status"] = "rejected"
    app_item["reject_reason"] = (body.reason or "").strip() or "管理员驳回"
    app_item["reviewed_by"] = current_user.username
    app_item["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    if not param:
        return ApiResponse.fail("申请队列不存在", code=404)
    param.param_value = json.dumps(applications, ensure_ascii=False)
    db.add(param)
    return ApiResponse.ok(message="已驳回申请")


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
    user_ids = [u.id for u in users]
    role_map = {}
    if user_ids:
        role_result = await db.execute(
            select(SysUserRole.user_id, SysRole.id, SysRole.name, SysRole.code)
            .join(SysRole, SysRole.id == SysUserRole.role_id)
            .where(SysUserRole.user_id.in_(user_ids))
        )
        for user_id, role_id, role_name, role_code in role_result.fetchall():
            role_map.setdefault(int(user_id), []).append({"id": int(role_id), "name": role_name, "code": role_code})

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
                "must_change_password": u.must_change_password,
                "roles": role_map.get(int(u.id), []),
                "role_ids": [r["id"] for r in role_map.get(int(u.id), [])],
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


# ---- 模块权限矩阵 ----
MODULE_PERMISSION_GROUPS = [
    {"code": "dashboard", "name": "经营概览"},
    {"code": "diagnosis", "name": "AI经营诊断"},
    {"code": "sales", "name": "销售中心"},
    {"code": "product", "name": "商品经营"},
    {"code": "purchase", "name": "采购协同"},
    {"code": "inventory", "name": "库存风控"},
    {"code": "finance", "name": "财务利润"},
    {"code": "hr", "name": "人力资源"},
    {"code": "knowledge", "name": "知识中枢"},
    {"code": "system", "name": "系统设置"},
]


@router.get("/permissions/module-matrix", response_model=ApiResponse)
async def module_permission_matrix(
    current_user: SysUser = Depends(require_permission("system:permission:view")),
    db: AsyncSession = Depends(get_db),
):
    role_result = await db.execute(select(SysRole).order_by(SysRole.sort_order, SysRole.id))
    roles = role_result.scalars().all()
    perm_result = await db.execute(select(SysPermission).order_by(SysPermission.module, SysPermission.code))
    permissions = perm_result.scalars().all()
    rp_result = await db.execute(select(SysRolePermission.role_id, SysPermission.code).join(SysPermission, SysPermission.id == SysRolePermission.permission_id))
    role_perm_map = {}
    for role_id, code in rp_result.fetchall():
        role_perm_map.setdefault(int(role_id), set()).add(code)

    return ApiResponse.ok(data={
        "modules": MODULE_PERMISSION_GROUPS,
        "roles": [
            {
                "id": int(r.id),
                "name": r.name,
                "code": r.code,
                "data_scope": r.data_scope,
                "status": r.status,
                "permissions": sorted(list(role_perm_map.get(int(r.id), set()))),
            }
            for r in roles
        ],
        "permissions": [
            {"id": int(p.id), "code": p.code, "name": p.name, "module": p.module, "description": p.description}
            for p in permissions
        ],
    })
