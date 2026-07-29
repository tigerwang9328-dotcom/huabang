"""依赖注入：JWT认证 + 权限校验"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from app.core.database import get_db
from app.core.security import decode_token
from app.models.sys import SysUser, SysUserRole, SysRole, SysRolePermission, SysPermission
from app.core.exceptions import PermissionDeniedException

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> SysUser:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token格式错误")

    result = await db.execute(
        select(SysUser).where(SysUser.id == int(user_id), SysUser.is_deleted == False)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if user.status != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")
    return user


async def get_current_user_roles(
    current_user: SysUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    """获取当前用户的角色编码列表"""
    if current_user.is_admin:
        return ["super_admin"]
    result = await db.execute(
        select(SysRole.code)
        .join(SysUserRole, SysUserRole.role_id == SysRole.id)
        .where(SysUserRole.user_id == current_user.id, SysRole.status == 1)
    )
    return [row[0] for row in result.fetchall()]


async def get_current_user_permissions(
    current_user: SysUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    """Return active platform permissions for the current principal."""
    if current_user.is_admin:
        return ["*"]
    result = await db.execute(
        select(SysPermission.code)
        .join(SysRolePermission, SysRolePermission.permission_id == SysPermission.id)
        .join(SysRole, SysRole.id == SysRolePermission.role_id)
        .join(SysUserRole, SysUserRole.role_id == SysRole.id)
        .where(SysUserRole.user_id == current_user.id, SysRole.status == 1)
        .distinct()
    )
    return [row[0] for row in result.fetchall()]


def require_permission(permission_code: str):
    """创建权限校验依赖"""
    async def check_permission(
        current_user: SysUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> SysUser:
        if current_user.is_admin:
            return current_user
        # 查询用户是否有该权限
        result = await db.execute(
            select(SysPermission.id)
            .join(SysRolePermission, SysRolePermission.permission_id == SysPermission.id)
            .join(SysRole, SysRole.id == SysRolePermission.role_id)
            .join(SysUserRole, SysUserRole.role_id == SysRole.id)
            .where(
                SysUserRole.user_id == current_user.id,
                SysPermission.code == permission_code,
                SysRole.status == 1,
            )
        )
        if not result.scalar_one_or_none():
            raise PermissionDeniedException(f"无权限: {permission_code}")
        return current_user
    return check_permission


def require_roles(*role_codes: str):
    """要求拥有指定角色之一"""
    async def check_role(
        current_user: SysUser = Depends(get_current_user),
        roles: list[str] = Depends(get_current_user_roles),
    ) -> SysUser:
        if current_user.is_admin or "super_admin" in roles:
            return current_user
        if not any(r in roles for r in role_codes):
            raise PermissionDeniedException("角色权限不足")
        return current_user
    return check_role

