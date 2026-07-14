"""Auditable task workflow API."""
import uuid
from datetime import date, datetime, timezone
from typing import Literal, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import and_, desc, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.core.data_scope import get_data_scope
from app.core.exceptions import PermissionDeniedException
from app.models.app import AppActionTask, AppTaskFeedback, AppTaskReview
from app.models.sys import SysRole, SysUser, SysUserRole, SysUserStore
from app.schemas.common import ApiResponse
from app.services.task_notification_service import TaskNotificationService
from app.services.task_workflow_service import (
    TaskTransitionError,
    can_manage_tasks,
    can_submit_feedback,
    next_task_status,
    normalize_assignee_roles,
)

router = APIRouter(prefix="/task", tags=["任务中心"])


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    description: Optional[str] = None
    data_evidence: Optional[dict] = None
    data_evidence_text: Optional[str] = None
    suggested_actions: Optional[list] = None
    review_metrics: Optional[list] = None
    feedback_requirement: Optional[str] = None
    assignee_id: Optional[int] = None
    assignee_name: Optional[str] = None
    assignee_role: Optional[str] = None
    due_date: Optional[date] = None
    priority: int = Field(default=5, ge=1, le=10)
    risk_level: str = "medium"
    related_store_code: Optional[str] = None
    related_product_code: Optional[str] = None
    related_date: Optional[date] = None
    source_type: str = "manual"
    source_id: Optional[int] = None


class TaskConfirmRequest(BaseModel):
    assignee_id: Optional[int] = None
    assignee_name: Optional[str] = None
    assignee_role: Optional[str] = None
    due_date: Optional[date] = None
    feedback_requirement: Optional[str] = None
    member_contact_script: Optional[str] = Field(default=None, min_length=8, max_length=2000)


class MemberFollowupResult(BaseModel):
    contacted: bool
    arrived: bool = False
    converted: bool = False
    conversion_amount: float = Field(default=0, ge=0, le=100_000_000)
    linked_ticket_no: Optional[str] = Field(default=None, max_length=128)
    no_conversion_reason: Optional[str] = Field(default=None, max_length=500)
    next_followup_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_progression(self):
        if self.arrived and not self.contacted:
            raise ValueError("未联系不能标记到店")
        if self.converted and not self.contacted:
            raise ValueError("未联系不能标记成交")
        if self.converted and (self.conversion_amount <= 0 or not str(self.linked_ticket_no or "").strip()):
            raise ValueError("成交必须填写成交金额和关联百胜小票")
        if self.contacted and not self.converted and not str(self.no_conversion_reason or "").strip():
            raise ValueError("未成交时必须填写原因")
        return self


class TaskFeedbackRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex, min_length=8, max_length=64)
    feedback_content: str = Field(min_length=1)
    action_taken: Optional[str] = None
    result_description: Optional[str] = None
    metrics_after: Optional[dict] = None
    member_followup: Optional[MemberFollowupResult] = None
    attachment_urls: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("attachment_urls")
    @classmethod
    def validate_attachment_urls(cls, values: list[str]) -> list[str]:
        safe_urls = []
        for raw_value in values:
            value = str(raw_value or "").strip()
            parsed = urlsplit(value)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
                raise ValueError("附件链接只允许 http 或 https 地址")
            if len(value) > 2048:
                raise ValueError("附件链接长度不能超过 2048 个字符")
            safe_urls.append(value)
        return safe_urls


class TaskReviewRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex, min_length=8, max_length=64)
    review_result: Literal["passed", "failed"]
    review_note: Optional[str] = None
    metrics_before: Optional[dict] = None
    metrics_after: Optional[dict] = None
    improvement_confirmed: Optional[bool] = None


async def _role_codes(db: AsyncSession, user: SysUser) -> set[str]:
    if user.is_admin:
        return {"super_admin"}
    rows = await db.execute(
        select(SysRole.code)
        .join(SysUserRole, SysUserRole.role_id == SysRole.id)
        .where(SysUserRole.user_id == user.id, SysRole.status == 1)
    )
    return set(rows.scalars().all())


async def _require_manager(db: AsyncSession, user: SysUser) -> set[str]:
    roles = await _role_codes(db, user)
    if not can_manage_tasks(roles):
        raise PermissionDeniedException("只有老板或主管可以执行该操作")
    return roles


async def _canonical_assignee_role(db: AsyncSession, value: Optional[str]) -> Optional[str]:
    role_codes = normalize_assignee_roles(value)
    if not role_codes:
        return None
    existing = set((await db.execute(
        select(SysRole.code).where(SysRole.code.in_(sorted(role_codes)), SysRole.status == 1)
    )).scalars().all())
    unknown = role_codes - existing
    if unknown:
        raise ValueError(f"责任角色不存在或未启用: {', '.join(sorted(unknown))}")
    return " / ".join(sorted(existing))


async def _validate_assignment_scope(
    db: AsyncSession,
    user: SysUser,
    *,
    related_store_code: Optional[str],
    assignee_id: Optional[int],
) -> None:
    scope = await get_data_scope(db, user)
    store_code = (related_store_code or "").strip() or None
    if store_code:
        allowed_stores = set(scope.store_codes)
        if scope.scope == "dept":
            if user.dept_id is None:
                allowed_stores = set()
            else:
                assigned = (await db.execute(
                    select(SysUserStore.store_code)
                    .join(SysUser, SysUser.id == SysUserStore.user_id)
                    .where(
                        SysUser.dept_id == user.dept_id,
                        SysUser.status == 1,
                        SysUser.is_deleted.is_(False),
                    )
                )).scalars().all()
                direct = (await db.execute(
                    select(SysUser.store_code).where(
                        SysUser.dept_id == user.dept_id,
                        SysUser.status == 1,
                        SysUser.is_deleted.is_(False),
                        SysUser.store_code.is_not(None),
                    )
                )).scalars().all()
                candidate_stores = {str(code) for code in [*assigned, *direct] if code}
                allowed_stores = candidate_stores.intersection(scope.store_codes)
        if store_code not in allowed_stores:
            raise PermissionDeniedException("不能为数据范围外的门店创建或派发任务")

    if assignee_id is None:
        return
    assignee = await db.scalar(select(SysUser).where(
        SysUser.id == assignee_id,
        SysUser.status == 1,
        SysUser.is_deleted.is_(False),
    ))
    if assignee is None:
        raise ValueError("责任人不存在或未启用")
    if scope.scope == "dept" and assignee.dept_id != user.dept_id:
        raise PermissionDeniedException("不能向其他部门人员派发任务")
    if scope.scope in {"store", "self"}:
        assignee_stores = set((await db.execute(
            select(SysUserStore.store_code).where(SysUserStore.user_id == assignee.id)
        )).scalars().all())
        if assignee.store_code:
            assignee_stores.add(assignee.store_code)
        if not assignee_stores.intersection(scope.store_codes):
            raise PermissionDeniedException("不能向其他门店人员派发任务")


async def _resolve_role_assignment_store(
    db: AsyncSession,
    user: SysUser,
    *,
    related_store_code: Optional[str],
    assignee_role: Optional[str],
) -> Optional[str]:
    """Resolve the one store needed by store/self scoped role recipients."""
    store_code = (related_store_code or "").strip() or None
    role_codes = normalize_assignee_roles(assignee_role)
    if not role_codes:
        return store_code
    store_scoped_role = await db.scalar(
        select(func.count())
        .select_from(SysRole)
        .where(
            SysRole.code.in_(sorted(role_codes)),
            SysRole.status == 1,
            func.coalesce(SysRole.data_scope, "self").in_(("store", "self")),
        )
    )
    if not store_scoped_role or store_code:
        return store_code

    candidates = set((await db.execute(
        select(SysUserStore.store_code).where(SysUserStore.user_id == user.id)
    )).scalars().all())
    if user.store_code:
        candidates.add(user.store_code)
    candidates = {str(code).strip() for code in candidates if str(code or "").strip()}
    if len(candidates) == 1:
        return candidates.pop()
    raise ValueError("按门店分派责任角色时必须指定唯一门店")


def _task_item(task: AppActionTask) -> dict:
    return {
        "id": task.id,
        "task_no": task.task_no,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "risk_level": task.risk_level,
        "assignee_id": task.assignee_id,
        "assignee_name": task.assignee_name,
        "assignee_role": task.assignee_role,
        "due_date": str(task.due_date) if task.due_date else None,
        "related_store_code": task.related_store_code,
        "source_type": task.source_type,
        "source_id": task.source_id,
        "requires_human_confirm": task.requires_human_confirm,
        "notification_status": task.notification_status,
        "notification_event_key": task.notification_event_key,
        "notification_kind": task.notification_kind,
        "notification_attempt_count": task.notification_attempt_count,
        "notification_manual_retry_count": task.notification_manual_retry_count,
        "created_at": str(task.created_at),
    }


def _role_assignment_condition(role_codes: set[str]):
    role_matches = []
    for role_code in sorted(role_codes):
        role_matches.extend((
            AppActionTask.assignee_role == role_code,
            AppActionTask.assignee_role.like(f"{role_code} / %"),
            AppActionTask.assignee_role.like(f"% / {role_code}"),
            AppActionTask.assignee_role.like(f"% / {role_code} / %"),
        ))
    if not role_matches:
        return AppActionTask.id == -1
    return and_(AppActionTask.assignee_id.is_(None), or_(*role_matches))


async def _scoped_task_statement(db: AsyncSession, user: SysUser):
    stmt = select(AppActionTask).where(AppActionTask.is_deleted.is_(False))
    scope = await get_data_scope(db, user)
    role_codes = set(scope.role_codes)
    creator_store_code = (
        select(SysUser.store_code)
        .where(SysUser.id == AppActionTask.creator_id)
        .correlate(AppActionTask)
        .scalar_subquery()
    )
    effective_store_code = func.coalesce(AppActionTask.related_store_code, creator_store_code)
    role_assignment = and_(
        _role_assignment_condition(role_codes),
        effective_store_code.in_(scope.store_codes or ["__NO_ACCESS__"]),
    )
    if scope.scope == "self":
        stmt = stmt.where(or_(AppActionTask.assignee_id == user.id, role_assignment))
    elif scope.scope == "store":
        stmt = stmt.where(or_(
            AppActionTask.assignee_id == user.id,
            effective_store_code.in_(scope.store_codes or ["__NO_ACCESS__"]),
        ))
    elif scope.scope == "dept":
        if user.dept_id is None:
            stmt = stmt.where(AppActionTask.assignee_id == user.id)
        else:
            creator_ids = select(SysUser.id).where(SysUser.dept_id == user.dept_id)
            stmt = stmt.where(or_(
                AppActionTask.assignee_id == user.id,
                AppActionTask.creator_id.in_(creator_ids),
            ))
    return stmt


async def _locked_scoped_task(
    db: AsyncSession,
    user: SysUser,
    task_id: int,
) -> AppActionTask | None:
    stmt = await _scoped_task_statement(db, user)
    return await db.scalar(stmt.where(AppActionTask.id == task_id).with_for_update())


def _task_capabilities(task: AppActionTask, user: SysUser, roles: set[str]) -> dict:
    manager = can_manage_tasks(roles)
    can_feedback = (
        task.status in {"pending", "processing", "overdue"}
        and can_submit_feedback(task.assignee_id, task.assignee_role, user.id, roles)
    )
    return {
        "can_confirm": manager and task.status == "draft",
        "can_feedback": can_feedback,
        "can_review": manager and task.status == "feedback_submitted",
        "can_close": manager and task.status == "review_passed",
    }


async def _retry_task_notification(
    db: AsyncSession,
    task: AppActionTask,
    current_user: SysUser,
) -> dict:
    task_id = int(task.id)
    await db.commit()
    return await TaskNotificationService().retry(task_id, actor_id=int(current_user.id))


async def _scoped_source_task(
    db: AsyncSession,
    current_user: SysUser,
    *,
    source_type: str,
    source_id: int,
) -> Optional[AppActionTask]:
    stmt = await _scoped_task_statement(db, current_user)
    return await db.scalar(stmt.where(
        AppActionTask.source_type == source_type,
        AppActionTask.source_id == source_id,
    ))


@router.get("/list", response_model=ApiResponse)
async def get_task_list(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    store_code: Optional[str] = None,
    priority_min: Optional[int] = None,
    current_user: SysUser = Depends(require_permission("task:view")),
    db: AsyncSession = Depends(get_db),
):
    stmt = await _scoped_task_statement(db, current_user)
    if status:
        stmt = stmt.where(AppActionTask.status == status)
    if store_code:
        stmt = stmt.where(AppActionTask.related_store_code == store_code)
    if priority_min is not None:
        stmt = stmt.where(AppActionTask.priority >= priority_min)
    total = int((await db.scalar(select(func.count()).select_from(stmt.subquery()))) or 0)
    tasks = (await db.execute(
        stmt.order_by(desc(AppActionTask.priority), desc(AppActionTask.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()
    roles = await _role_codes(db, current_user)
    return ApiResponse.ok(data={
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [{**_task_item(task), **_task_capabilities(task, current_user, roles)} for task in tasks],
    })


@router.get("/assignees", response_model=ApiResponse)
async def list_task_assignees(
    store_code: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("task:approve")),
    db: AsyncSession = Depends(get_db),
):
    await _require_manager(db, current_user)
    scope = await get_data_scope(db, current_user)
    requested_store = str(store_code or "").strip().upper()
    allowed_codes = {str(code).upper() for code in scope.store_codes}
    if requested_store and requested_store not in allowed_codes:
        raise PermissionDeniedException("不能查看数据范围外门店的责任人")
    target_codes = [requested_store] if requested_store else sorted(allowed_codes)
    if not target_codes:
        return ApiResponse.ok(data={"items": []})
    rows = (await db.execute(text("""
        SELECT u.id,u.real_name,u.employee_no,u.position,
               ARRAY_REMOVE(ARRAY_AGG(DISTINCT COALESCE(us.store_code,u.store_code)),NULL) store_codes
        FROM sys.sys_user u
        LEFT JOIN sys.sys_user_store us ON us.user_id=u.id
        WHERE u.status=1 AND u.is_deleted=false
          AND NULLIF(BTRIM(COALESCE(u.employee_no,'')),'') IS NOT NULL
          AND (UPPER(COALESCE(u.store_code,''))=ANY(:store_codes) OR UPPER(COALESCE(us.store_code,''))=ANY(:store_codes))
        GROUP BY u.id,u.real_name,u.employee_no,u.position
        ORDER BY COALESCE(u.real_name,u.employee_no)
    """), {"store_codes": target_codes})).mappings().all()
    return ApiResponse.ok(data={"items": [dict(row) for row in rows]})


@router.post("/create", response_model=ApiResponse)
async def create_task(
    body: TaskCreateRequest,
    current_user: SysUser = Depends(require_permission("task:create")),
    db: AsyncSession = Depends(get_db),
):
    try:
        assignee_role = await _canonical_assignee_role(db, body.assignee_role)
        await _validate_assignment_scope(
            db,
            current_user,
            related_store_code=body.related_store_code,
            assignee_id=body.assignee_id,
        )
    except ValueError as exc:
        return ApiResponse.fail(str(exc))
    if body.source_id is not None:
        existing = await _scoped_source_task(
            db,
            current_user,
            source_type=body.source_type,
            source_id=body.source_id,
        )
        if existing:
            return ApiResponse.ok(data={"id": existing.id, "task_no": existing.task_no}, message="该异常已有任务草稿")
    task = AppActionTask(
        task_no="T" + datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4].upper(),
        title=body.title.strip(),
        description=body.description,
        data_evidence=body.data_evidence,
        data_evidence_text=body.data_evidence_text,
        suggested_actions=body.suggested_actions,
        review_metrics=body.review_metrics,
        feedback_requirement=body.feedback_requirement,
        assignee_id=body.assignee_id,
        assignee_name=body.assignee_name,
        assignee_role=assignee_role,
        due_date=body.due_date,
        priority=body.priority,
        risk_level=body.risk_level,
        related_store_code=body.related_store_code,
        related_product_code=body.related_product_code,
        related_date=body.related_date,
        source_type=body.source_type,
        source_id=body.source_id,
        creator_id=current_user.id,
        status="draft",
        requires_human_confirm=True,
    )
    try:
        async with db.begin_nested():
            db.add(task)
            await db.flush()
    except IntegrityError:
        if body.source_id is None:
            raise
        existing = await _scoped_source_task(
            db,
            current_user,
            source_type=body.source_type,
            source_id=body.source_id,
        )
        if existing:
            return ApiResponse.ok(
                data={"id": existing.id, "task_no": existing.task_no},
                message="该异常已有任务草稿",
            )
        return ApiResponse.fail("该来源已有任务", code=409)
    return ApiResponse.ok(data={"id": task.id, "task_no": task.task_no}, message="任务草稿创建成功，待人工确认派发")


@router.get("/{task_id}", response_model=ApiResponse)
async def get_task_detail(
    task_id: int,
    current_user: SysUser = Depends(require_permission("task:view")),
    db: AsyncSession = Depends(get_db),
):
    stmt = await _scoped_task_statement(db, current_user)
    task = await db.scalar(stmt.where(AppActionTask.id == task_id))
    if not task:
        return ApiResponse.fail("任务不存在", code=404)
    feedbacks = (await db.execute(
        select(AppTaskFeedback).where(AppTaskFeedback.task_id == task_id).order_by(AppTaskFeedback.created_at)
    )).scalars().all()
    reviews = (await db.execute(
        select(AppTaskReview).where(AppTaskReview.task_id == task_id).order_by(AppTaskReview.created_at)
    )).scalars().all()
    roles = await _role_codes(db, current_user)
    data = {**_task_item(task), **_task_capabilities(task, current_user, roles)}
    data.update({
        "description": task.description,
        "data_evidence": task.data_evidence,
        "data_evidence_text": task.data_evidence_text,
        "suggested_actions": task.suggested_actions,
        "review_metrics": task.review_metrics,
        "feedback_requirement": task.feedback_requirement,
        "related_product_code": task.related_product_code,
        "related_date": str(task.related_date) if task.related_date else None,
        "confirmed_by": task.confirmed_by,
        "confirmed_at": str(task.confirmed_at) if task.confirmed_at else None,
        "closed_by": task.closed_by,
        "closed_at": str(task.closed_at) if task.closed_at else None,
        "overdue_at": str(task.overdue_at) if task.overdue_at else None,
        "notification_error": task.notification_error,
        "notification_updated_at": str(task.notification_updated_at) if task.notification_updated_at else None,
        "updated_at": str(task.updated_at),
        "feedbacks": [{
            "id": item.id,
            "request_id": item.request_id,
            "feedback_by": item.feedback_by,
            "content": item.feedback_content,
            "action_taken": item.action_taken,
            "result_description": item.result_description,
            "metrics_after": item.metrics_after,
            "attachment_urls": item.attachment_urls or [],
            "created_at": str(item.created_at),
        } for item in feedbacks],
        "reviews": [{
            "id": item.id,
            "request_id": item.request_id,
            "reviewed_by": item.reviewed_by,
            "result": item.review_result,
            "note": item.review_note,
            "metrics_before": item.metrics_before,
            "metrics_after": item.metrics_after,
            "improvement_confirmed": item.improvement_confirmed,
            "created_at": str(item.created_at),
        } for item in reviews],
    })
    return ApiResponse.ok(data=data)


@router.post("/{task_id}/confirm", response_model=ApiResponse)
async def confirm_task(
    task_id: int,
    body: TaskConfirmRequest = TaskConfirmRequest(),
    current_user: SysUser = Depends(require_permission("task:approve")),
    db: AsyncSession = Depends(get_db),
):
    await _require_manager(db, current_user)
    task = await _locked_scoped_task(db, current_user, task_id)
    if not task:
        return ApiResponse.fail("任务不存在", code=404)
    if task.status != "draft":
        if task.confirmed_at is not None:
            if task.notification_status != "success":
                notification = await _retry_task_notification(db, task, current_user)
                return ApiResponse.ok(
                    data={**_task_item(task), "notification": notification},
                    message="任务已派发，已重试责任人通知",
                )
            return ApiResponse.ok(data=_task_item(task), message="任务已派发，无需重复确认")
        return ApiResponse.fail(f"任务当前状态为{task.status}，不可派发")

    for name in ("assignee_id", "assignee_name", "feedback_requirement"):
        value = getattr(body, name)
        if value is not None:
            setattr(task, name, value)
    role_value = body.assignee_role if body.assignee_role is not None else task.assignee_role
    try:
        task.assignee_role = await _canonical_assignee_role(db, role_value)
    except ValueError as exc:
        return ApiResponse.fail(str(exc))
    if task.assignee_id is None:
        try:
            task.related_store_code = await _resolve_role_assignment_store(
                db,
                current_user,
                related_store_code=task.related_store_code,
                assignee_role=task.assignee_role,
            )
        except ValueError as exc:
            return ApiResponse.fail(str(exc))
    if body.due_date:
        task.due_date = body.due_date
    if not (task.assignee_id or task.assignee_role):
        return ApiResponse.fail("确认派发前必须指定责任人或责任角色")
    try:
        await _validate_assignment_scope(
            db,
            current_user,
            related_store_code=task.related_store_code,
            assignee_id=task.assignee_id,
        )
    except ValueError as exc:
        return ApiResponse.fail(str(exc))
    if not task.due_date:
        return ApiResponse.fail("确认派发前必须设置截止日期")
    if not task.feedback_requirement:
        return ApiResponse.fail("确认派发前必须填写处理和反馈要求")
    if not (task.data_evidence or task.data_evidence_text):
        return ApiResponse.fail("确认派发前必须保留数据证据")

    if task.source_type == "member_action":
        if task.assignee_id is None:
            return ApiResponse.fail("VIP会员行动必须指定到具体责任人")
        if not str(body.member_contact_script or "").strip():
            return ApiResponse.fail("联系会员前必须由主管确认联系话术")
        assignee = await db.scalar(select(SysUser).where(
            SysUser.id == task.assignee_id,
            SysUser.status == 1,
            SysUser.is_deleted.is_(False),
        ))
        if not assignee or not str(assignee.employee_no or "").strip():
            return ApiResponse.fail("VIP会员行动责任人必须维护员工编号")
        assignee_store_codes = {str(code).upper() for code in (await db.execute(
            select(SysUserStore.store_code).where(SysUserStore.user_id == assignee.id)
        )).scalars().all()}
        if assignee.store_code:
            assignee_store_codes.add(str(assignee.store_code).upper())
        if str(task.related_store_code or "").upper() not in assignee_store_codes:
            return ApiResponse.fail("VIP会员行动责任人必须属于会员归属门店")
        task.assignee_name = str(assignee.real_name or assignee.employee_no)
        evidence = dict(task.data_evidence or {})
        member_action = dict(evidence.get("member_action") or {})
        member_action.update({
            "confirmed_script": str(body.member_contact_script).strip(),
            "responsibility_status": "confirmed",
            "responsible_user_id": int(assignee.id),
            "responsible_employee_no": str(assignee.employee_no),
            "confirmed_by": int(current_user.id),
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        })
        evidence["member_action"] = member_action
        task.data_evidence = evidence
        await db.execute(text("""
            UPDATE dm.dm_member_segment_snapshot
            SET responsibility_status='confirmed',responsible_employee_no=:employee_no
            WHERE id=:snapshot_id
        """), {
            "snapshot_id": task.source_id,
            "employee_no": str(assignee.employee_no),
        })

    task.status = next_task_status(task.status, "confirm")
    task.confirmed_by = current_user.id
    task.confirmed_at = datetime.now(timezone.utc)
    task.requires_human_confirm = False
    task.workflow_version = int(task.workflow_version or 0) + 1
    notifier = TaskNotificationService()
    await notifier.enqueue_assignment(db, task)
    await db.commit()
    notification = await notifier.notify_assignment(task_id)
    return ApiResponse.ok(data={**_task_item(task), "notification": notification}, message="任务已派发")


@router.post("/{task_id}/retry-notification", response_model=ApiResponse)
async def retry_task_notification(
    task_id: int,
    current_user: SysUser = Depends(require_permission("task:approve")),
    db: AsyncSession = Depends(get_db),
):
    await _require_manager(db, current_user)
    task = await _locked_scoped_task(db, current_user, task_id)
    if not task:
        return ApiResponse.fail("任务不存在", code=404)
    if task.status == "draft" or task.confirmed_at is None:
        return ApiResponse.fail("任务尚未确认派发")
    notification = await _retry_task_notification(db, task, current_user)
    return ApiResponse.ok(
        data={**_task_item(task), "notification": notification},
        message="责任人通知已重试",
    )


@router.post("/{task_id}/feedback", response_model=ApiResponse)
async def submit_feedback(
    task_id: int,
    body: TaskFeedbackRequest,
    current_user: SysUser = Depends(require_permission("task:feedback")),
    db: AsyncSession = Depends(get_db),
):
    task = await _locked_scoped_task(db, current_user, task_id)
    if not task:
        return ApiResponse.fail("任务不存在", code=404)
    roles = await _role_codes(db, current_user)
    if not can_submit_feedback(task.assignee_id, task.assignee_role, current_user.id, roles):
        raise PermissionDeniedException("只有该任务的负责人可以反馈")
    existing = await db.scalar(select(AppTaskFeedback).where(
        AppTaskFeedback.task_id == task_id,
        AppTaskFeedback.request_id == body.request_id,
    ))
    if existing:
        return ApiResponse.ok(data={"feedback_id": existing.id}, message="反馈已提交，无需重复提交")
    try:
        new_status = next_task_status(task.status, "feedback")
    except TaskTransitionError as exc:
        return ApiResponse.fail(str(exc))
    metrics_after = dict(body.metrics_after or {})
    if task.source_type == "member_action":
        if body.member_followup is None:
            return ApiResponse.fail("VIP会员行动反馈必须记录联系、到店和成交结果")
        metrics_after["member_followup"] = body.member_followup.model_dump(mode="json")
    feedback = AppTaskFeedback(
        task_id=task_id,
        request_id=body.request_id,
        feedback_by=current_user.id,
        feedback_content=body.feedback_content,
        attachment_urls=body.attachment_urls,
        action_taken=body.action_taken,
        result_description=body.result_description,
        metrics_after=metrics_after or None,
    )
    db.add(feedback)
    task.status = new_status
    task.workflow_version = int(task.workflow_version or 0) + 1
    await db.flush()
    return ApiResponse.ok(data={"feedback_id": feedback.id}, message="反馈提交成功，等待复查")


@router.post("/{task_id}/review", response_model=ApiResponse)
async def submit_review(
    task_id: int,
    body: TaskReviewRequest,
    current_user: SysUser = Depends(require_permission("task:review")),
    db: AsyncSession = Depends(get_db),
):
    await _require_manager(db, current_user)
    task = await _locked_scoped_task(db, current_user, task_id)
    if not task:
        return ApiResponse.fail("任务不存在", code=404)
    existing = await db.scalar(select(AppTaskReview).where(
        AppTaskReview.task_id == task_id,
        AppTaskReview.request_id == body.request_id,
    ))
    if existing:
        return ApiResponse.ok(data={"review_id": existing.id}, message="复查结果已记录，无需重复提交")
    try:
        new_status = next_task_status(task.status, "review", review_result=body.review_result)
    except TaskTransitionError as exc:
        return ApiResponse.fail(str(exc))
    review = AppTaskReview(
        task_id=task_id,
        request_id=body.request_id,
        reviewed_by=current_user.id,
        review_result=body.review_result,
        review_note=body.review_note,
        metrics_before=body.metrics_before,
        metrics_after=body.metrics_after,
        improvement_confirmed=body.improvement_confirmed,
    )
    db.add(review)
    task.status = new_status
    task.workflow_version = int(task.workflow_version or 0) + 1
    await db.flush()
    message = "复查通过，等待关闭" if body.review_result == "passed" else "已退回责任人继续整改"
    return ApiResponse.ok(data={"review_id": review.id, "status": new_status}, message=message)


@router.post("/{task_id}/close", response_model=ApiResponse)
async def close_task(
    task_id: int,
    current_user: SysUser = Depends(require_permission("task:close")),
    db: AsyncSession = Depends(get_db),
):
    await _require_manager(db, current_user)
    task = await _locked_scoped_task(db, current_user, task_id)
    if not task:
        return ApiResponse.fail("任务不存在", code=404)
    if task.status == "closed":
        return ApiResponse.ok(data=_task_item(task), message="任务已关闭，无需重复操作")
    try:
        task.status = next_task_status(task.status, "close")
    except TaskTransitionError as exc:
        return ApiResponse.fail(str(exc))
    now = datetime.now(timezone.utc)
    task.closed_by = current_user.id
    task.closed_at = now
    task.completed_at = now
    task.workflow_version = int(task.workflow_version or 0) + 1
    return ApiResponse.ok(data=_task_item(task), message="任务已关闭")
