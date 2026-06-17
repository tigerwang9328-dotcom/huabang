from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import timedelta, datetime, timezone
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.core.config import settings
from app.core.exceptions import AppException
from app.models.sys import SysUser, SysUserRole, SysRole
from app.schemas.common import ApiResponse
from pydantic import BaseModel
from typing import Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["认证"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user_id: int
    username: str
    real_name: Optional[str] = None
    roles: list[str] = []
    is_admin: bool = False


@router.post("/login", response_model=ApiResponse[LoginResponse])
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SysUser).where(
            SysUser.username == body.username,
            SysUser.is_deleted == False,
        )
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise AppException(code=401, message="用户名或密码错误")

    if user.status != 1:
        raise AppException(code=403, message="账号已被禁用，请联系管理员")

    # 获取角色
    role_result = await db.execute(
        select(SysRole.code)
        .join(SysUserRole, SysUserRole.role_id == SysRole.id)
        .where(SysUserRole.user_id == user.id)
    )
    roles = [r[0] for r in role_result.fetchall()]
    if user.is_admin:
        roles = ["super_admin"] + roles

    # 生成 token
    token_data = {"sub": str(user.id), "username": user.username}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    # 更新登录时间
    client_ip = request.client.host if request.client else "unknown"
    await db.execute(
        update(SysUser)
        .where(SysUser.id == user.id)
        .values(
            last_login_at=datetime.now(timezone.utc),
            last_login_ip=client_ip,
        )
    )

    logger.info(f"用户登录成功: {user.username} from {client_ip}")

    return ApiResponse.ok(
        data=LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=user.id,
            username=user.username,
            real_name=user.real_name,
            roles=roles,
            is_admin=user.is_admin,
        ),
        message="登录成功",
    )


@router.post("/refresh", response_model=ApiResponse)
async def refresh_token(
    refresh_token_str: str,
    db: AsyncSession = Depends(get_db),
):
    payload = decode_token(refresh_token_str)
    if not payload or payload.get("type") != "refresh":
        raise AppException(code=401, message="refresh_token无效或已过期")

    user_id = payload.get("sub")
    result = await db.execute(
        select(SysUser).where(SysUser.id == int(user_id), SysUser.is_deleted == False)
    )
    user = result.scalar_one_or_none()
    if not user or user.status != 1:
        raise AppException(code=401, message="用户不存在或已禁用")

    new_access_token = create_access_token({"sub": str(user.id), "username": user.username})
    return ApiResponse.ok(data={"access_token": new_access_token, "token_type": "Bearer"})


@router.post("/logout", response_model=ApiResponse)
async def logout():
    # JWT无状态，客户端清除token即可；如需黑名单可扩展Redis
    return ApiResponse.ok(message="已退出登录")
