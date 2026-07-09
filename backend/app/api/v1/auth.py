from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import timedelta, datetime, timezone
from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token, decode_token
from app.core.config import settings
from app.core.exceptions import AppException
from app.api.v1.deps import get_current_user
from app.models.sys import SysUser, SysUserRole, SysRole, SysRolePermission, SysPermission, SysParam
from app.schemas.common import ApiResponse
from pydantic import BaseModel
from typing import Optional
import logging
import json
import uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["认证"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterApplyRequest(BaseModel):
    username: str
    password: str
    confirm_password: str
    real_name: str
    phone: str
    apply_role: str
    department: Optional[str] = None
    store_code: Optional[str] = None
    remark: Optional[str] = None



class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user_id: int
    username: str
    real_name: Optional[str] = None
    roles: list[str] = []
    permissions: list[str] = []
    data_scope: str = "self"
    is_admin: bool = False
    must_change_password: bool = False


@router.post("/register-apply", response_model=ApiResponse)
async def register_apply(
    request: Request,
    body: RegisterApplyRequest,
    db: AsyncSession = Depends(get_db),
):
    """注册申请：只记录申请，不直接创建账号，需管理员审核。"""
    username = body.username.strip()
    real_name = body.real_name.strip()
    phone = body.phone.strip()
    apply_role = body.apply_role.strip()
    password = body.password or ""
    confirm_password = body.confirm_password or ""
    if not username or len(username) < 3:
        return ApiResponse.fail("用户名至少3位")
    if not username.replace("_", "").replace("-", "").isalnum():
        return ApiResponse.fail("用户名仅支持字母、数字、下划线和短横线")
    if not real_name:
        return ApiResponse.fail("请填写姓名")
    if not phone or len(phone) < 6:
        return ApiResponse.fail("请填写有效手机号")
    if not apply_role:
        return ApiResponse.fail("请选择申请岗位")
    if len(password) < 8:
        return ApiResponse.fail("密码至少8位")
    if password != confirm_password:
        return ApiResponse.fail("两次输入的密码不一致")

    exists = await db.execute(select(SysUser.id).where(SysUser.username == username, SysUser.is_deleted == False))
    if exists.scalar_one_or_none():
        return ApiResponse.fail("该用户名已存在，请更换用户名")

    result = await db.execute(select(SysParam).where(SysParam.param_key == "register_applications"))
    param = result.scalar_one_or_none()
    applications = []
    if param and param.param_value:
        try:
            applications = json.loads(param.param_value)
            if not isinstance(applications, list):
                applications = []
        except Exception:
            applications = []

    for item in applications:
        if item.get("status") == "pending" and item.get("username") == username:
            return ApiResponse.fail("该用户名已有待审核申请，请勿重复提交")
        if item.get("phone") == phone and item.get("status") == "pending":
            return ApiResponse.fail("该手机号已有待审核申请，请勿重复提交")

    client_ip = request.client.host if request.client else "unknown"
    application = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password_hash": get_password_hash(password),
        "real_name": real_name,
        "phone": phone,
        "apply_role": apply_role,
        "department": (body.department or "").strip(),
        "store_code": (body.store_code or "").strip(),
        "remark": (body.remark or "").strip(),
        "status": "pending",
        "client_ip": client_ip,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    applications.insert(0, application)

    if not param:
        param = SysParam(
            param_key="register_applications",
            param_value=json.dumps(applications, ensure_ascii=False),
            description="华邦AI中台注册申请队列",
            is_system=True,
        )
        db.add(param)
    else:
        param.param_value = json.dumps(applications, ensure_ascii=False)
        db.add(param)

    logger.info(f"注册申请已提交: {username} {real_name} {phone} {apply_role} from {client_ip}")
    return ApiResponse.ok(data={"id": application["id"]}, message="注册申请已提交，请等待管理员审核")


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

    # 获取角色、数据范围与权限码
    role_result = await db.execute(
        select(SysRole.id, SysRole.code, SysRole.data_scope)
        .join(SysUserRole, SysUserRole.role_id == SysRole.id)
        .where(SysUserRole.user_id == user.id, SysRole.status == 1)
    )
    role_rows = role_result.fetchall()
    roles = [r[1] for r in role_rows]
    scope_rank = {"self": 1, "store": 2, "dept": 3, "company": 4, "all": 5}
    data_scope = "all" if user.is_admin else "self"
    for _, _, scope in role_rows:
        if scope_rank.get(scope or "self", 1) > scope_rank.get(data_scope, 1):
            data_scope = scope or "self"

    if user.is_admin:
        roles = ["super_admin"] + roles
        permissions = ["*"]
        data_scope = "all"
    else:
        perm_result = await db.execute(
            select(SysPermission.code)
            .join(SysRolePermission, SysRolePermission.permission_id == SysPermission.id)
            .join(SysRole, SysRole.id == SysRolePermission.role_id)
            .join(SysUserRole, SysUserRole.role_id == SysRole.id)
            .where(SysUserRole.user_id == user.id, SysRole.status == 1)
            .distinct()
        )
        permissions = sorted([r[0] for r in perm_result.fetchall()])

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
            permissions=permissions,
            data_scope=data_scope,
            is_admin=user.is_admin,
            must_change_password=user.must_change_password or False,
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

@router.post("/change-password", response_model=ApiResponse)
async def change_password(
    old_password: str,
    new_password: str,
    current_user: SysUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.security import verify_password, get_password_hash
    if not verify_password(old_password, current_user.password_hash):
        raise AppException(code=400, message="原密码错误")
    if len(new_password) < 8:
        raise AppException(code=400, message="新密码至少8位")
    current_user.password_hash = get_password_hash(new_password)
    current_user.must_change_password = False
    db.add(current_user)
    await db.commit()
    return ApiResponse.ok(message="密码修改成功")
