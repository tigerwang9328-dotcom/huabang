"""系统管理API（用户/角色/权限/字典）"""
import json
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete, or_, and_
from typing import Optional, Any
from pydantic import BaseModel
from app.core.database import get_db
from app.api.v1.deps import require_permission, get_current_user
from app.core.security import get_password_hash
from app.core.store_whitelist import ALLOWED_STORE_CODES, ALLOWED_INVENTORY_CODES
from app.models.sys import SysUser, SysRole, SysUserRole, SysDepartment, SysMenu, SysParam, SysPermission, SysRolePermission, SysRegisterApplication, SysOperationLog, SysUserStore, SysFieldPermission
from app.schemas.common import ApiResponse
from app.services.size_wall_service import SizeWallService

router = APIRouter(prefix="/system", tags=["系统管理"])

ROLE_LABELS = {"super_admin":"超级管理员","boss":"BOSS","ceo":"总经理","product_manager":"商品经理","product_specialist":"商品专员","finance_manager":"财务经理","accountant":"会计","cashier":"出纳","warehouse_manager":"仓库主管","operation_manager":"运营经理","store_manager":"店长","guide":"导购"}
DATA_SCOPE_NAMES = {"all":"全部数据","company":"公司数据","dept":"部门数据","store":"门店数据","self":"个人数据"}
FIELD_RESOURCES = [("sales","sales.amount","销售金额"),("sales","sales.profit","销售利润"),("sales","sales.customer_phone","客户手机号"),("product","product.cost_price","商品成本价"),("product","product.gross_margin","商品毛利率"),("inventory","inventory.stock_amount","库存金额"),("finance","finance.payable","应付款"),("finance","finance.receivable","应收款"),("finance","finance.cash_balance","资金余额"),("hr","hr.salary","员工薪资"),("hr","hr.phone","员工手机号")]
SECURITY_DEFAULTS = {"password_min_length":8,"password_require_number":True,"password_require_letter":True,"password_require_special":False,"login_max_failed":5,"login_lock_minutes":30,"register_apply_rate_limit":5,"register_apply_window_minutes":10,"remember_password_enabled":False}


class SizeWallSyncRequest(BaseModel):
    analysis_date: Optional[date] = None

async def write_operation_log(db, user, module, action, target_type=None, target_id=None, before_data=None, after_data=None, request=None):
    db.add(SysOperationLog(user_id=user.id if user else None, username=user.username if user else None, module=module, action=action, target_type=target_type, target_id=str(target_id) if target_id is not None else None, before_data=before_data, after_data=after_data, ip=request.client.host if request and request.client else None, user_agent=request.headers.get("user-agent") if request else None))

async def sync_user_stores(db, user_id:int, store_code:Optional[str], store_codes:list[str]):
    codes=[]
    if store_code: codes.append(store_code)
    codes += store_codes or []
    uniq=[]
    for c in codes:
        c=(c or "").strip()
        if c and c not in uniq: uniq.append(c)
    await db.execute(delete(SysUserStore).where(SysUserStore.user_id==user_id))
    for i,c in enumerate(uniq): db.add(SysUserStore(user_id=user_id, store_code=c, is_primary=(i==0 or c==store_code)))

async def security_settings(db):
    vals=dict(SECURITY_DEFAULTS); res=await db.execute(select(SysParam).where(SysParam.param_key.like("security.%")))
    for p in res.scalars().all():
        k=p.param_key.replace("security.","",1)
        if k in vals:
            if isinstance(vals[k], bool): vals[k]=str(p.param_value).lower() in {"1","true","yes","on"}
            elif isinstance(vals[k], int):
                try: vals[k]=int(p.param_value)
                except Exception: pass
            else: vals[k]=p.param_value
    return vals



class UserCreateRequest(BaseModel):
    username: str
    password: str
    real_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    dept_id: Optional[int] = None
    store_code: Optional[str] = None
    employee_no: Optional[str] = None
    position: Optional[str] = None
    role_ids: list[int] = []
    store_codes: list[str] = []
    must_change_password: bool = False


class RegisterAuditRequest(BaseModel):
    reason: Optional[str] = None
    review_note: Optional[str] = None

class RegisterApproveRequest(BaseModel):
    role_ids: list[int] = []
    dept_id: Optional[int] = None
    store_code: Optional[str] = None
    store_codes: list[str] = []
    review_note: Optional[str] = None

class RoleCreateRequest(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    data_scope: str = "self"
    status: int = 1
    sort_order: int = 0

class RoleUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    data_scope: Optional[str] = None
    status: Optional[int] = None
    sort_order: Optional[int] = None
    is_hidden: Optional[bool] = None

class RolePermissionRequest(BaseModel):
    permission_ids: list[int] = []
    permission_codes: list[str] = []

class RoleDataScopeRequest(BaseModel):
    data_scope: str

class UserDataScopeRequest(BaseModel):
    dept_id: Optional[int] = None
    store_code: Optional[str] = None
    store_codes: list[str] = []

class FieldPermissionItem(BaseModel):
    role_id: int
    field_name: str
    module: Optional[str] = None
    can_view: bool = True
    mask_rule: str = "none"

class FieldPermissionSaveRequest(BaseModel):
    role_id: int
    items: list[FieldPermissionItem]

class SecuritySettingsRequest(BaseModel):
    password_min_length: int = 8
    password_require_number: bool = True
    password_require_letter: bool = True
    password_require_special: bool = False
    login_max_failed: int = 5
    login_lock_minutes: int = 30
    register_apply_rate_limit: int = 5
    register_apply_window_minutes: int = 10
    remember_password_enabled: bool = False


class UserUpdateRequest(BaseModel):
    password: Optional[str] = None
    real_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    dept_id: Optional[int] = None
    store_code: Optional[str] = None
    employee_no: Optional[str] = None
    position: Optional[str] = None
    status: Optional[int] = None
    role_ids: Optional[list[int]] = None
    store_codes: Optional[list[str]] = None
    must_change_password: Optional[bool] = None

class ResetPasswordRequest(BaseModel):
    password: Optional[str] = None




# ---- 注册审核 ----
@router.get("/register-applications", response_model=ApiResponse)
async def list_register_applications(page:int=1,page_size:int=20,status:Optional[str]=None,keyword:Optional[str]=None,apply_role:Optional[str]=None,date_from:Optional[str]=None,date_to:Optional[str]=None,current_user:SysUser=Depends(require_permission("system:register:review")),db:AsyncSession=Depends(get_db)):
    stmt=select(SysRegisterApplication)
    fs=[]
    if status: fs.append(SysRegisterApplication.status==status)
    if apply_role: fs.append(SysRegisterApplication.apply_role==apply_role)
    if keyword:
        kw=f"%{keyword}%"; fs.append(or_(SysRegisterApplication.username.ilike(kw),SysRegisterApplication.real_name.ilike(kw),SysRegisterApplication.phone.ilike(kw)))
    if fs: stmt=stmt.where(and_(*fs))
    total=(await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows=(await db.execute(stmt.order_by(SysRegisterApplication.created_at.desc()).offset((page-1)*page_size).limit(page_size))).scalars().all()
    reviewer_ids=[r.reviewed_by for r in rows if r.reviewed_by]
    rm={}
    if reviewer_ids:
        rr=await db.execute(select(SysUser.id,SysUser.real_name,SysUser.username).where(SysUser.id.in_(reviewer_ids)))
        rm={int(i):(rn or un) for i,rn,un in rr.fetchall()}
    return ApiResponse.ok(data={"total":total,"page":page,"page_size":page_size,"items":[{"id":str(r.id),"username":r.username,"real_name":r.real_name,"phone":r.phone,"apply_role":r.apply_role,"apply_role_name":ROLE_LABELS.get(r.apply_role,r.apply_role),"department":r.department,"store_code":r.store_code,"remark":r.remark,"status":r.status,"client_ip":r.client_ip,"created_at":r.created_at.isoformat() if r.created_at else None,"reviewed_by":r.reviewed_by,"reviewed_by_name":rm.get(int(r.reviewed_by)) if r.reviewed_by else None,"reviewed_at":r.reviewed_at.isoformat() if r.reviewed_at else None,"reject_reason":r.reject_reason,"approved_user_id":r.approved_user_id,"review_note":r.review_note,"assigned_role_ids":r.assigned_role_ids or [],"assigned_store_codes":r.assigned_store_codes or [],"assigned_dept_id":r.assigned_dept_id} for r in rows]})

@router.post("/register-applications/{application_id}/approve", response_model=ApiResponse)
async def approve_register_application(application_id:str, body:RegisterApproveRequest, request:Request, current_user:SysUser=Depends(require_permission("system:register:review")), db:AsyncSession=Depends(get_db)):
    app=(await db.execute(select(SysRegisterApplication).where(SysRegisterApplication.id==application_id))).scalar_one_or_none()
    if not app: return ApiResponse.fail("申请不存在", code=404)
    if app.status!="pending": return ApiResponse.fail("该申请已处理，不能重复审核")
    if (await db.execute(select(SysUser.id).where(SysUser.username==app.username, SysUser.is_deleted==False))).scalar_one_or_none(): return ApiResponse.fail("该用户名已存在，无法通过申请")
    role_ids=body.role_ids or []
    if not role_ids:
        rid=(await db.execute(select(SysRole.id).where(SysRole.code==app.apply_role, SysRole.status==1))).scalar_one_or_none()
        if not rid: return ApiResponse.fail("申请岗位不存在或已禁用，请先配置角色")
        role_ids=[int(rid)]
    user=SysUser(username=app.username,password_hash=app.password_hash,real_name=app.real_name,phone=app.phone,dept_id=body.dept_id,store_code=body.store_code or app.store_code,status=1,must_change_password=False)
    db.add(user); await db.flush()
    for rid in role_ids: db.add(SysUserRole(user_id=user.id, role_id=rid))
    await sync_user_stores(db,int(user.id),body.store_code or app.store_code,body.store_codes)
    app.status="approved"; app.approved_user_id=int(user.id); app.reviewed_by=current_user.id; app.reviewed_at=datetime.now(timezone.utc); app.review_note=body.review_note; app.assigned_role_ids=role_ids; app.assigned_store_codes=body.store_codes or ([body.store_code] if body.store_code else []); app.assigned_dept_id=body.dept_id
    await write_operation_log(db,current_user,"system","register.approve","register_application",application_id,after_data={"user_id":int(user.id),"role_ids":role_ids},request=request)
    return ApiResponse.ok(data={"user_id":int(user.id)}, message="已通过申请并创建账号")

@router.post("/register-applications/{application_id}/reject", response_model=ApiResponse)
async def reject_register_application(application_id:str, body:RegisterAuditRequest, request:Request, current_user:SysUser=Depends(require_permission("system:register:review")), db:AsyncSession=Depends(get_db)):
    app=(await db.execute(select(SysRegisterApplication).where(SysRegisterApplication.id==application_id))).scalar_one_or_none()
    if not app: return ApiResponse.fail("申请不存在", code=404)
    if app.status!="pending": return ApiResponse.fail("该申请已处理，不能重复审核")
    reason=(body.reason or "").strip()
    if not reason: return ApiResponse.fail("驳回原因不能为空")
    before={"status":app.status}; app.status="rejected"; app.reject_reason=reason; app.reviewed_by=current_user.id; app.reviewed_at=datetime.now(timezone.utc); app.review_note=body.review_note
    await write_operation_log(db,current_user,"system","register.reject","register_application",application_id,before_data=before,after_data={"reason":reason},request=request)
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
    user_store_map = {}
    if user_ids:
        store_result = await db.execute(select(SysUserStore.user_id, SysUserStore.store_code).where(SysUserStore.user_id.in_(user_ids)))
        for store_user_id, store_code in store_result.fetchall():
            user_store_map.setdefault(int(store_user_id), []).append(store_code)
    role_map = {}
    if user_ids:
        role_result = await db.execute(
            select(SysUserRole.user_id, SysRole.id, SysRole.name, SysRole.code, SysRole.data_scope)
            .join(SysRole, SysRole.id == SysUserRole.role_id)
            .where(SysUserRole.user_id.in_(user_ids))
        )
        for user_id, role_id, role_name, role_code, data_scope in role_result.fetchall():
            role_map.setdefault(int(user_id), []).append({"id": int(role_id), "name": role_name, "code": role_code, "data_scope": data_scope})

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
                "store_codes": user_store_map.get(int(u.id), []),
                "employee_no": getattr(u, "employee_no", None),
                "position": getattr(u, "position", None),
                "status": u.status,
                "is_admin": u.is_admin,
                "must_change_password": u.must_change_password,
                "roles": role_map.get(int(u.id), []),
                "role_ids": [r["id"] for r in role_map.get(int(u.id), [])],
                "last_login_at": str(u.last_login_at) if u.last_login_at else None,
                "last_login_ip": u.last_login_ip,
                "failed_login_count": getattr(u, "failed_login_count", 0),
                "locked_until": str(u.locked_until) if getattr(u, "locked_until", None) else None,
                "data_risk": any((r.get("data_scope") in {"store", "self"}) for r in role_map.get(int(u.id), [])) and not u.store_code,
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
        employee_no=body.employee_no,
        position=body.position,
        status=1,
        must_change_password=body.must_change_password,
    )
    db.add(user)
    await db.flush()

    for role_id in body.role_ids:
        db.add(SysUserRole(user_id=user.id, role_id=role_id))
    await sync_user_stores(db, int(user.id), body.store_code, body.store_codes)
    await write_operation_log(db, current_user, "system", "user.create", "user", user.id, after_data={"username": body.username, "role_ids": body.role_ids})

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

    if body.password:
        user.password_hash = get_password_hash(body.password)
        user.must_change_password = True
        user.failed_login_count = 0
        user.locked_until = None
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
    if body.employee_no is not None:
        user.employee_no = body.employee_no
    if body.position is not None:
        user.position = body.position
    if body.must_change_password is not None:
        user.must_change_password = body.must_change_password
    if body.status is not None:
        user.status = body.status

    if body.role_ids is not None:
        await db.execute(delete(SysUserRole).where(SysUserRole.user_id == user_id))
        for role_id in body.role_ids:
            db.add(SysUserRole(user_id=user_id, role_id=role_id))
    if body.store_codes is not None:
        await sync_user_stores(db, user_id, body.store_code or user.store_code, body.store_codes)
    await write_operation_log(db, current_user, "system", "user.update", "user", user_id, after_data=body.model_dump(exclude_unset=True))

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


@router.post("/users/{user_id}/enable", response_model=ApiResponse)
async def enable_user(user_id: int, request: Request, current_user: SysUser = Depends(require_permission("system:user:enable")), db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(SysUser).where(SysUser.id == user_id, SysUser.is_deleted == False))).scalar_one_or_none()
    if not user:
        return ApiResponse.fail("用户不存在", code=404)
    user.status = 1
    await write_operation_log(db, current_user, "system", "user.enable", "user", user_id, request=request)
    return ApiResponse.ok(message="用户已启用")

@router.post("/users/{user_id}/disable", response_model=ApiResponse)
async def disable_user(user_id: int, request: Request, current_user: SysUser = Depends(require_permission("system:user:disable")), db: AsyncSession = Depends(get_db)):
    if user_id == current_user.id:
        return ApiResponse.fail("不能停用自己")
    user = (await db.execute(select(SysUser).where(SysUser.id == user_id, SysUser.is_deleted == False))).scalar_one_or_none()
    if not user:
        return ApiResponse.fail("用户不存在", code=404)
    user.status = 0
    await write_operation_log(db, current_user, "system", "user.disable", "user", user_id, request=request)
    return ApiResponse.ok(message="用户已停用")

@router.post("/users/{user_id}/reset-password", response_model=ApiResponse)
async def reset_user_password(user_id: int, body: ResetPasswordRequest, request: Request, current_user: SysUser = Depends(require_permission("system:user:reset-password")), db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(SysUser).where(SysUser.id == user_id, SysUser.is_deleted == False))).scalar_one_or_none()
    if not user:
        return ApiResponse.fail("用户不存在", code=404)
    new_password = body.password or "Hb@123456"
    user.password_hash = get_password_hash(new_password)
    user.must_change_password = True
    user.failed_login_count = 0
    user.locked_until = None
    await write_operation_log(db, current_user, "system", "user.reset_password", "user", user_id, request=request)
    return ApiResponse.ok(data={"default_password": None if body.password else "Hb@123456"}, message="密码已重置")


# ---- 角色管理 ----
@router.get("/roles", response_model=ApiResponse)
async def list_roles(
    show_legacy: bool = False,
    keyword: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("system:role:view")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SysRole)
    if not show_legacy:
        stmt = stmt.where(or_(SysRole.is_hidden == False, SysRole.is_hidden.is_(None)))
    if keyword:
        stmt = stmt.where(or_(SysRole.name.ilike(f"%{keyword}%"), SysRole.code.ilike(f"%{keyword}%")))
    result = await db.execute(stmt.order_by(SysRole.sort_order, SysRole.id))
    roles = result.scalars().all()
    items = []
    for r in roles:
        pc = (await db.execute(select(func.count()).select_from(SysRolePermission).where(SysRolePermission.role_id == r.id))).scalar() or 0
        uc = (await db.execute(select(func.count()).select_from(SysUserRole).where(SysUserRole.role_id == r.id))).scalar() or 0
        items.append({
            "id": int(r.id), "name": r.name, "code": r.code, "description": r.description,
            "data_scope": r.data_scope, "data_scope_name": DATA_SCOPE_NAMES.get(r.data_scope, r.data_scope),
            "status": r.status, "sort_order": r.sort_order, "permission_count": pc, "user_count": uc,
            "is_builtin": bool(getattr(r, "is_builtin", False)), "is_legacy": bool(getattr(r, "is_legacy", False)), "is_hidden": bool(getattr(r, "is_hidden", False)),
        })
    return ApiResponse.ok(data=items)


@router.get("/org-options", response_model=ApiResponse)
async def get_org_options(current_user: SysUser = Depends(require_permission("system:user:view")), db: AsyncSession = Depends(get_db)):
    departments = (await db.execute(select(SysDepartment).order_by(SysDepartment.parent_id, SysDepartment.sort_order, SysDepartment.id))).scalars().all()
    return ApiResponse.ok(data={
        "departments": [{"id": int(d.id), "name": d.name, "parent_id": d.parent_id, "status": d.status} for d in departments],
        "stores": sorted(ALLOWED_STORE_CODES),
        "inventories": sorted(ALLOWED_INVENTORY_CODES),
    })


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


# ---- 角色权限增强 ----
async def role_payload(db, r):
    pc=(await db.execute(select(func.count()).select_from(SysRolePermission).where(SysRolePermission.role_id==r.id))).scalar() or 0
    uc=(await db.execute(select(func.count()).select_from(SysUserRole).where(SysUserRole.role_id==r.id))).scalar() or 0
    return {"id":int(r.id),"name":r.name,"code":r.code,"description":r.description,"data_scope":r.data_scope,"data_scope_name":DATA_SCOPE_NAMES.get(r.data_scope,r.data_scope),"status":r.status,"sort_order":r.sort_order,"permission_count":pc,"user_count":uc,"is_builtin":bool(getattr(r,"is_builtin",False)),"is_legacy":bool(getattr(r,"is_legacy",False)),"is_hidden":bool(getattr(r,"is_hidden",False))}

@router.post("/roles", response_model=ApiResponse)
async def create_role(body:RoleCreateRequest, request:Request, current_user:SysUser=Depends(require_permission("system:role:create")), db:AsyncSession=Depends(get_db)):
    if (await db.execute(select(SysRole.id).where(or_(SysRole.code==body.code, SysRole.name==body.name)))).scalar_one_or_none(): return ApiResponse.fail("角色名称或编码已存在")
    r=SysRole(name=body.name,code=body.code,description=body.description,data_scope=body.data_scope,status=body.status,sort_order=body.sort_order,is_builtin=False,is_legacy=False,is_hidden=False)
    db.add(r); await db.flush(); await write_operation_log(db,current_user,"system","role.create","role",r.id,after_data=body.model_dump(),request=request)
    return ApiResponse.ok(data={"id":int(r.id)}, message="角色创建成功")

@router.get("/roles/{role_id}", response_model=ApiResponse)
async def get_role_detail(role_id:int,current_user:SysUser=Depends(require_permission("system:role:view")),db:AsyncSession=Depends(get_db)):
    r=(await db.execute(select(SysRole).where(SysRole.id==role_id))).scalar_one_or_none()
    return ApiResponse.fail("角色不存在",404) if not r else ApiResponse.ok(data=await role_payload(db,r))

@router.put("/roles/{role_id}", response_model=ApiResponse)
async def update_role(role_id:int,body:RoleUpdateRequest,request:Request,current_user:SysUser=Depends(require_permission("system:role:update")),db:AsyncSession=Depends(get_db)):
    r=(await db.execute(select(SysRole).where(SysRole.id==role_id))).scalar_one_or_none()
    if not r: return ApiResponse.fail("角色不存在",404)
    before=await role_payload(db,r)
    for k,v in body.model_dump(exclude_unset=True).items(): setattr(r,k,v)
    await write_operation_log(db,current_user,"system","role.update","role",role_id,before_data=before,after_data=body.model_dump(exclude_unset=True),request=request)
    return ApiResponse.ok(message="角色已更新")

@router.delete("/roles/{role_id}", response_model=ApiResponse)
async def delete_role(role_id:int,request:Request,current_user:SysUser=Depends(require_permission("system:role:delete")),db:AsyncSession=Depends(get_db)):
    r=(await db.execute(select(SysRole).where(SysRole.id==role_id))).scalar_one_or_none()
    if not r: return ApiResponse.fail("角色不存在",404)
    r.status=0; r.is_hidden=True
    await write_operation_log(db,current_user,"system","role.disable","role",role_id,before_data={"code":r.code},request=request)
    return ApiResponse.ok(message="角色已停用并隐藏")

@router.get("/roles/{role_id}/permissions", response_model=ApiResponse)
async def get_role_permissions(role_id:int,current_user:SysUser=Depends(require_permission("system:permission:view")),db:AsyncSession=Depends(get_db)):
    perms=(await db.execute(select(SysPermission).order_by(SysPermission.module,SysPermission.code))).scalars().all()
    checked=(await db.execute(select(SysRolePermission.permission_id).where(SysRolePermission.role_id==role_id))).scalars().all()
    groups=[]
    for m in MODULE_PERMISSION_GROUPS:
        groups.append({"module":m["code"],"module_name":m["name"],"permissions":[{"id":int(p.id),"code":p.code,"name":p.name,"description":p.description} for p in perms if p.module==m["code"]]})
    return ApiResponse.ok(data={"role_id":role_id,"checked_permission_ids":[int(x) for x in checked],"groups":groups})

@router.put("/roles/{role_id}/permissions", response_model=ApiResponse)
async def update_role_permissions(role_id:int, body:RolePermissionRequest, request:Request, current_user:SysUser=Depends(require_permission("system:permission:update")), db:AsyncSession=Depends(get_db)):
    ids=set(body.permission_ids or [])
    if body.permission_codes:
        ids.update(int(x) for x in (await db.execute(select(SysPermission.id).where(SysPermission.code.in_(body.permission_codes)))).scalars().all())
    before=[int(x) for x in (await db.execute(select(SysRolePermission.permission_id).where(SysRolePermission.role_id==role_id))).scalars().all()]
    await db.execute(delete(SysRolePermission).where(SysRolePermission.role_id==role_id))
    for pid in ids: db.add(SysRolePermission(role_id=role_id, permission_id=pid))
    await write_operation_log(db,current_user,"system","role.update_permissions","role",role_id,before_data={"permission_ids":before},after_data={"permission_ids":sorted(ids)},request=request)
    return ApiResponse.ok(message="权限已保存")

@router.put("/roles/{role_id}/data-scope", response_model=ApiResponse)
async def update_role_data_scope(role_id:int,body:RoleDataScopeRequest,request:Request,current_user:SysUser=Depends(require_permission("system:data-scope:update")),db:AsyncSession=Depends(get_db)):
    r=(await db.execute(select(SysRole).where(SysRole.id==role_id))).scalar_one_or_none()
    if not r: return ApiResponse.fail("角色不存在",404)
    before={"data_scope":r.data_scope}; r.data_scope=body.data_scope
    await write_operation_log(db,current_user,"system","data_scope.update","role",role_id,before_data=before,after_data={"data_scope":body.data_scope},request=request)
    return ApiResponse.ok(message="角色数据范围已保存")

@router.get("/security-settings", response_model=ApiResponse)
async def get_security_settings(current_user:SysUser=Depends(require_permission("system:security:update")),db:AsyncSession=Depends(get_db)):
    return ApiResponse.ok(data=await security_settings(db))

@router.put("/security-settings", response_model=ApiResponse)
async def update_security_settings(body:SecuritySettingsRequest,request:Request,current_user:SysUser=Depends(require_permission("system:security:update")),db:AsyncSession=Depends(get_db)):
    before=await security_settings(db)
    for k,v in body.model_dump().items():
        key=f"security.{k}"; res=await db.execute(select(SysParam).where(SysParam.param_key==key)); p=res.scalar_one_or_none(); val=str(v).lower() if isinstance(v,bool) else str(v)
        if p: p.param_value=val
        else: db.add(SysParam(param_key=key,param_value=val,description="系统安全设置",is_system=True))
    await write_operation_log(db,current_user,"system","security.update","security_settings","security",before_data=before,after_data=body.model_dump(),request=request)
    return ApiResponse.ok(message="安全设置已保存")

@router.get("/operation-logs", response_model=ApiResponse)
async def get_operation_logs(page:int=1,page_size:int=20,module:Optional[str]=None,action:Optional[str]=None,username:Optional[str]=None,keyword:Optional[str]=None,current_user:SysUser=Depends(require_permission("system:operation-log:view")),db:AsyncSession=Depends(get_db)):
    stmt=select(SysOperationLog); fs=[]
    if module: fs.append(SysOperationLog.module==module)
    if action: fs.append(SysOperationLog.action==action)
    if username: fs.append(SysOperationLog.username.ilike(f"%{username}%"))
    if keyword: fs.append(or_(SysOperationLog.action.ilike(f"%{keyword}%"), SysOperationLog.target_id.ilike(f"%{keyword}%")))
    if fs: stmt=stmt.where(and_(*fs))
    total=(await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows=(await db.execute(stmt.order_by(SysOperationLog.created_at.desc()).offset((page-1)*page_size).limit(page_size))).scalars().all()
    return ApiResponse.ok(data={"total":total,"page":page,"page_size":page_size,"items":[{"id":int(r.id),"username":r.username,"module":r.module,"action":r.action,"target_type":r.target_type,"target_id":r.target_id,"ip":r.ip,"user_agent":r.user_agent,"created_at":r.created_at.isoformat() if r.created_at else None,"before_data":r.before_data,"after_data":r.after_data} for r in rows]})

@router.get("/field-permissions", response_model=ApiResponse)
async def get_field_permissions(role_id:Optional[int]=None,current_user:SysUser=Depends(require_permission("system:field-permission:update")),db:AsyncSession=Depends(get_db)):
    stmt=select(SysFieldPermission)
    if role_id: stmt=stmt.where(SysFieldPermission.role_id==role_id)
    rows=(await db.execute(stmt)).scalars().all()
    return ApiResponse.ok(data={"resources":[{"module":m,"field_name":f,"field_label":n} for m,f,n in FIELD_RESOURCES],"items":[{"id":int(r.id),"role_id":int(r.role_id),"module":r.module,"field_name":r.field_name,"can_view":r.can_view,"mask_rule":r.mask_rule or "none"} for r in rows]})

@router.put("/field-permissions", response_model=ApiResponse)
async def update_field_permissions(body:FieldPermissionSaveRequest,request:Request,current_user:SysUser=Depends(require_permission("system:field-permission:update")),db:AsyncSession=Depends(get_db)):
    await db.execute(delete(SysFieldPermission).where(SysFieldPermission.role_id==body.role_id))
    for item in body.items: db.add(SysFieldPermission(role_id=body.role_id,module=item.module or item.field_name.split('.')[0],field_name=item.field_name,can_view=item.can_view,mask_rule=item.mask_rule))
    await write_operation_log(db,current_user,"system","field_permission.update","role",body.role_id,after_data=body.model_dump(),request=request)
    return ApiResponse.ok(message="字段权限已保存")

@router.get("/data-scopes", response_model=ApiResponse)
async def get_data_scopes(current_user:SysUser=Depends(require_permission("system:data-scope:update")),db:AsyncSession=Depends(get_db)):
    roles=(await db.execute(select(SysRole).order_by(SysRole.sort_order,SysRole.id))).scalars().all(); users=(await db.execute(select(SysUser).where(SysUser.is_deleted==False).order_by(SysUser.id))).scalars().all()
    return ApiResponse.ok(data={"roles":[await role_payload(db,r) for r in roles],"users":[{"id":int(u.id),"username":u.username,"real_name":u.real_name,"dept_id":u.dept_id,"store_code":u.store_code,"risk":"未绑定门店" if not u.store_code else "正常"} for u in users],"risk_users":[{"id":int(u.id),"username":u.username,"risk":"未绑定门店"} for u in users if not u.store_code],"store_whitelist": sorted(ALLOWED_STORE_CODES), "inventory_whitelist": sorted(ALLOWED_INVENTORY_CODES)})

@router.put("/users/{user_id}/data-scope", response_model=ApiResponse)
async def update_user_data_scope(user_id:int,body:UserDataScopeRequest,request:Request,current_user:SysUser=Depends(require_permission("system:data-scope:update")),db:AsyncSession=Depends(get_db)):
    u=(await db.execute(select(SysUser).where(SysUser.id==user_id,SysUser.is_deleted==False))).scalar_one_or_none()
    if not u: return ApiResponse.fail("用户不存在",404)
    u.dept_id=body.dept_id; u.store_code=body.store_code; await sync_user_stores(db,user_id,body.store_code,body.store_codes)
    await write_operation_log(db,current_user,"system","data_scope.update","user",user_id,after_data=body.model_dump(),request=request)
    return ApiResponse.ok(message="用户数据权限已保存")

@router.get("/users/{user_id}/data-scope-preview", response_model=ApiResponse)
async def user_data_scope_preview(user_id:int,current_user:SysUser=Depends(require_permission("system:data-scope:update")),db:AsyncSession=Depends(get_db)):
    from app.core.data_scope import get_data_scope
    u=(await db.execute(select(SysUser).where(SysUser.id==user_id,SysUser.is_deleted==False))).scalar_one_or_none()
    if not u: return ApiResponse.fail("用户不存在",404)
    ds=await get_data_scope(db,u); return ApiResponse.ok(data={"user_id":user_id,"roles":ds.role_codes,"data_scope":ds.scope,"store_codes":ds.store_codes,"inventory_codes":ds.inventory_codes,"warnings":[] if ds.store_codes else ["未绑定有效门店"]})

@router.get("/dashboard-stats", response_model=ApiResponse)
async def system_dashboard_stats(current_user:SysUser=Depends(require_permission("system:dashboard:view")),db:AsyncSession=Depends(get_db)):
    user_total=(await db.execute(select(func.count()).select_from(SysUser).where(SysUser.is_deleted==False))).scalar() or 0; enabled=(await db.execute(select(func.count()).select_from(SysUser).where(SysUser.is_deleted==False,SysUser.status==1))).scalar() or 0
    role_count=(await db.execute(select(func.count()).select_from(SysRole))).scalar() or 0; perm_count=(await db.execute(select(func.count()).select_from(SysPermission))).scalar() or 0; pending=(await db.execute(select(func.count()).select_from(SysRegisterApplication).where(SysRegisterApplication.status=="pending"))).scalar() or 0
    return ApiResponse.ok(data={"cards":{"user_total":user_total,"user_enabled":enabled,"user_disabled":max(user_total-enabled,0),"role_count":role_count,"permission_count":perm_count,"pending_register":pending,"today_login":0,"today_permission_changes":0,"data_risk_users":0,"security_risks":0},"todos":[{"label":"待审核注册申请","count":pending}]})


@router.post("/sync/size-wall", response_model=ApiResponse)
async def rebuild_size_wall_snapshot(
    body: SizeWallSyncRequest,
    current_user: SysUser = Depends(require_permission("sync:import")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await SizeWallService().build_snapshot(db, body.analysis_date)
        await db.commit()
        return ApiResponse.ok(data=result, message="断码尺码墙快照生成完成")
    except ValueError as exc:
        await db.rollback()
        return ApiResponse.fail(str(exc))
