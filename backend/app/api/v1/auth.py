from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from datetime import timedelta, datetime, timezone
from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token, decode_token
from app.core.config import settings
from app.core.exceptions import AppException
from app.api.v1.deps import get_current_user
from app.models.sys import SysUser, SysUserRole, SysRole, SysRolePermission, SysPermission, SysParam, SysRegisterApplication, SysOperationLog
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


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
    confirm_password: str


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




SECURITY_DEFAULTS = {"password_min_length": 8, "password_require_number": True, "password_require_letter": True, "password_require_special": False, "login_max_failed": 5, "login_lock_minutes": 30, "register_apply_rate_limit": 5, "register_apply_window_minutes": 10, "remember_password_enabled": False}

async def _security_settings(db: AsyncSession) -> dict:
    result = await db.execute(select(SysParam).where(SysParam.param_key.like("security.%")))
    values = dict(SECURITY_DEFAULTS)
    for p in result.scalars().all():
        k = p.param_key.replace("security.", "", 1)
        if k in values:
            if isinstance(values[k], bool): values[k] = str(p.param_value).lower() in {"1","true","yes","on"}
            elif isinstance(values[k], int):
                try: values[k] = int(p.param_value)
                except Exception: pass
            else: values[k] = p.param_value
    return values

async def _auth_log(db: AsyncSession, request: Request, action: str, user: Optional[SysUser] = None, username: Optional[str] = None, data=None):
    db.add(SysOperationLog(user_id=user.id if user else None, username=user.username if user else username, module="auth", action=action, target_type="user", target_id=str(user.id) if user else username, after_data=data, ip=request.client.host if request.client else None, user_agent=request.headers.get("user-agent")))

def _password_policy_error(password: str, sec: dict) -> Optional[str]:
    import re
    if len(password or "") < int(sec.get("password_min_length", 8)): return f"密码至少{sec.get('password_min_length', 8)}位"
    if sec.get("password_require_number") and not re.search(r"\d", password): return "密码必须包含数字"
    if sec.get("password_require_letter") and not re.search(r"[A-Za-z]", password): return "密码必须包含字母"
    if sec.get("password_require_special") and not re.search(r"[^A-Za-z0-9]", password): return "密码必须包含特殊字符"
    return None

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
    """注册申请：写入结构化注册申请表，需管理员审核后创建账号。"""
    username = body.username.strip()
    real_name = body.real_name.strip()
    phone = body.phone.strip()
    apply_role = body.apply_role.strip()
    password = body.password or ""
    confirm_password = body.confirm_password or ""
    sec = await _security_settings(db)
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
    policy_error = _password_policy_error(password, sec)
    if policy_error:
        return ApiResponse.fail(policy_error)
    if password != confirm_password:
        return ApiResponse.fail("两次输入的密码不一致")
    exists = await db.execute(select(SysUser.id).where(SysUser.username == username, SysUser.is_deleted == False))
    if exists.scalar_one_or_none():
        return ApiResponse.fail("该用户名已存在，请更换用户名")
    client_ip = request.client.host if request.client else "unknown"
    since = datetime.now(timezone.utc) - timedelta(minutes=int(sec.get("register_apply_window_minutes", 10)))
    ip_count = (await db.execute(select(func.count()).select_from(SysRegisterApplication).where(SysRegisterApplication.client_ip == client_ip, SysRegisterApplication.created_at >= since))).scalar() or 0
    if ip_count >= int(sec.get("register_apply_rate_limit", 5)):
        return ApiResponse.fail("注册申请过于频繁，请稍后再试")
    dup = await db.execute(select(SysRegisterApplication.id).where(SysRegisterApplication.status == "pending", ((SysRegisterApplication.username == username) | (SysRegisterApplication.phone == phone))))
    if dup.scalar_one_or_none():
        return ApiResponse.fail("该用户名或手机号已有待审核申请，请勿重复提交")
    application = SysRegisterApplication(
        id=str(uuid.uuid4()), username=username, password_hash=get_password_hash(password), real_name=real_name, phone=phone, apply_role=apply_role,
        department=(body.department or "").strip(), store_code=(body.store_code or "").strip(), remark=(body.remark or "").strip(), status="pending", client_ip=client_ip,
    )
    db.add(application)
    await _auth_log(db, request, "register.apply", username=username, data={"id": application.id, "apply_role": apply_role})
    logger.info(f"注册申请已提交: {username} {real_name} {phone} {apply_role} from {client_ip}")
    return ApiResponse.ok(data={"id": application.id}, message="注册申请已提交，请等待管理员审核")

@router.post("/login", response_model=ApiResponse[LoginResponse])
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    sec = await _security_settings(db)
    result = await db.execute(select(SysUser).where(SysUser.username == body.username, SysUser.is_deleted == False))
    user = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if user and user.locked_until and user.locked_until > now:
        await _auth_log(db, request, "login.failed", user=user, data={"reason": "locked"})
        remain = int((user.locked_until - now).total_seconds() // 60) + 1
        raise AppException(code=423, message=f"账号已锁定，请 {remain} 分钟后再试")
    if not user or not verify_password(body.password, user.password_hash):
        if user:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= int(sec.get("login_max_failed", 5)):
                user.locked_until = now + timedelta(minutes=int(sec.get("login_lock_minutes", 30)))
            await _auth_log(db, request, "login.failed", user=user, data={"failed_login_count": user.failed_login_count})
        else:
            await _auth_log(db, request, "login.failed", username=body.username, data={"reason": "user_not_found"})
        raise AppException(code=401, message="用户名或密码错误")
    if user.status != 1:
        await _auth_log(db, request, "login.failed", user=user, data={"reason": "disabled"})
        raise AppException(code=403, message="账号已被禁用，请联系管理员")
    role_result = await db.execute(select(SysRole.id, SysRole.code, SysRole.data_scope).join(SysUserRole, SysUserRole.role_id == SysRole.id).where(SysUserRole.user_id == user.id, SysRole.status == 1))
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
        perm_result = await db.execute(select(SysPermission.code).join(SysRolePermission, SysRolePermission.permission_id == SysPermission.id).join(SysRole, SysRole.id == SysRolePermission.role_id).join(SysUserRole, SysUserRole.role_id == SysRole.id).where(SysUserRole.user_id == user.id, SysRole.status == 1).distinct())
        permissions = sorted([r[0] for r in perm_result.fetchall()])
    token_data = {"sub": str(user.id), "username": user.username}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    client_ip = request.client.host if request.client else "unknown"
    await db.execute(update(SysUser).where(SysUser.id == user.id).values(last_login_at=now, last_login_ip=client_ip, failed_login_count=0, locked_until=None))
    await _auth_log(db, request, "login.success", user=user)
    logger.info(f"用户登录成功: {user.username} from {client_ip}")
    return ApiResponse.ok(data=LoginResponse(access_token=access_token, refresh_token=refresh_token, expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60, user_id=user.id, username=user.username, real_name=user.real_name, roles=roles, permissions=permissions, data_scope=data_scope, is_admin=user.is_admin, must_change_password=user.must_change_password or False), message="登录成功")

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
    request: Request,
    body: ChangePasswordRequest,
    current_user: SysUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_result = await db.execute(
        select(SysUser).where(SysUser.id == current_user.id, SysUser.is_deleted == False)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise AppException(code=401, message="用户不存在或已失效")

    if not verify_password(body.old_password, user.password_hash):
        await _auth_log(db, request, "password.change_failed", user=user, data={"reason": "old_password_invalid"})
        return ApiResponse.fail("原密码不正确", code=400)

    if body.new_password != body.confirm_password:
        return ApiResponse.fail("两次输入的新密码不一致", code=400)

    sec = await _security_settings(db)
    policy_error = _password_policy_error(body.new_password, sec)
    if policy_error:
        return ApiResponse.fail(policy_error, code=400)

    if verify_password(body.new_password, user.password_hash):
        return ApiResponse.fail("新密码不能和原密码相同", code=400)

    user.password_hash = get_password_hash(body.new_password)
    user.must_change_password = False
    user.failed_login_count = 0
    user.locked_until = None
    db.add(user)
    await _auth_log(db, request, "password.change_success", user=user)
    await db.commit()
    return ApiResponse.ok(message="密码修改成功，请重新登录")

