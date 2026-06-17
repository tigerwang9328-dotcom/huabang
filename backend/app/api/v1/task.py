"""任务闭环API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, update
from datetime import date, timedelta, datetime, timezone
from typing import Optional
from pydantic import BaseModel
from app.core.database import get_db
from app.api.v1.deps import require_permission, get_current_user
from app.models.sys import SysUser
from app.models.app import AppActionTask, AppTaskFeedback, AppTaskReview
from app.schemas.common import ApiResponse
import logging, uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/task", tags=["任务中心"])


class TaskCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    data_evidence: Optional[dict] = None
    data_evidence_text: Optional[str] = None
    suggested_actions: Optional[list] = None
    review_metrics: Optional[list] = None
    feedback_requirement: Optional[str] = None
    assignee_id: Optional[int] = None
    assignee_name: Optional[str] = None
    assignee_role: Optional[str] = None
    due_date: Optional[str] = None
    priority: int = 5
    risk_level: str = "medium"
    related_store_code: Optional[str] = None
    related_product_code: Optional[str] = None
    source_type: str = "manual"


class TaskFeedbackRequest(BaseModel):
    feedback_content: str
    action_taken: Optional[str] = None
    result_description: Optional[str] = None
    metrics_after: Optional[dict] = None


class TaskReviewRequest(BaseModel):
    review_result: str  # passed/failed/pending
    review_note: Optional[str] = None
    metrics_before: Optional[dict] = None
    metrics_after: Optional[dict] = None
    improvement_confirmed: Optional[bool] = None


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
    stmt = (
        select(AppActionTask)
        .where(AppActionTask.is_deleted == False)
        .order_by(desc(AppActionTask.priority), desc(AppActionTask.created_at))
    )
    if status:
        stmt = stmt.where(AppActionTask.status == status)
    if store_code:
        stmt = stmt.where(AppActionTask.related_store_code == store_code)
    if priority_min:
        stmt = stmt.where(AppActionTask.priority >= priority_min)

    count_result = await db.execute(
        select(func.count()).select_from(AppActionTask)
        .where(AppActionTask.is_deleted == False)
    )
    total = count_result.scalar()

    result = await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    tasks = result.scalars().all()

    return ApiResponse.ok(data={
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": t.id,
                "task_no": t.task_no,
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "risk_level": t.risk_level,
                "assignee_name": t.assignee_name,
                "due_date": str(t.due_date) if t.due_date else None,
                "related_store_code": t.related_store_code,
                "source_type": t.source_type,
                "requires_human_confirm": t.requires_human_confirm,
                "created_at": str(t.created_at),
            }
            for t in tasks
        ],
    })


@router.post("/create", response_model=ApiResponse)
async def create_task(
    body: TaskCreateRequest,
    current_user: SysUser = Depends(require_permission("task:create")),
    db: AsyncSession = Depends(get_db),
):
    task_no = "T" + datetime.now().strftime("%Y%m%d%H%M%S") + str(uuid.uuid4())[:4].upper()
    task = AppActionTask(
        task_no=task_no,
        title=body.title,
        description=body.description,
        data_evidence=body.data_evidence,
        data_evidence_text=body.data_evidence_text,
        suggested_actions=body.suggested_actions,
        review_metrics=body.review_metrics,
        feedback_requirement=body.feedback_requirement,
        assignee_id=body.assignee_id,
        assignee_name=body.assignee_name,
        assignee_role=body.assignee_role,
        due_date=date.fromisoformat(body.due_date) if body.due_date else None,
        priority=body.priority,
        risk_level=body.risk_level,
        related_store_code=body.related_store_code,
        related_product_code=body.related_product_code,
        source_type=body.source_type,
        creator_id=current_user.id,
        status="draft",
        requires_human_confirm=True,
    )
    db.add(task)
    await db.flush()
    return ApiResponse.ok(data={"id": task.id, "task_no": task.task_no}, message="任务草稿创建成功，待人工确认派发")


@router.get("/{task_id}", response_model=ApiResponse)
async def get_task_detail(
    task_id: int,
    current_user: SysUser = Depends(require_permission("task:view")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AppActionTask).where(AppActionTask.id == task_id, AppActionTask.is_deleted == False)
    )
    task = result.scalar_one_or_none()
    if not task:
        return ApiResponse.fail("任务不存在", code=404)

    # 获取反馈和复查
    fb_result = await db.execute(
        select(AppTaskFeedback).where(AppTaskFeedback.task_id == task_id).order_by(desc(AppTaskFeedback.created_at))
    )
    feedbacks = fb_result.scalars().all()

    rv_result = await db.execute(
        select(AppTaskReview).where(AppTaskReview.task_id == task_id).order_by(desc(AppTaskReview.created_at))
    )
    reviews = rv_result.scalars().all()

    return ApiResponse.ok(data={
        "id": task.id,
        "task_no": task.task_no,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "risk_level": task.risk_level,
        "data_evidence": task.data_evidence,
        "data_evidence_text": task.data_evidence_text,
        "suggested_actions": task.suggested_actions,
        "review_metrics": task.review_metrics,
        "feedback_requirement": task.feedback_requirement,
        "assignee_id": task.assignee_id,
        "assignee_name": task.assignee_name,
        "assignee_role": task.assignee_role,
        "due_date": str(task.due_date) if task.due_date else None,
        "requires_human_confirm": task.requires_human_confirm,
        "related_store_code": task.related_store_code,
        "source_type": task.source_type,
        "dingtalk_task_url": task.dingtalk_task_url,
        "created_at": str(task.created_at),
        "updated_at": str(task.updated_at),
        "feedbacks": [{"id": f.id, "content": f.feedback_content, "action_taken": f.action_taken, "created_at": str(f.created_at)} for f in feedbacks],
        "reviews": [{"id": r.id, "result": r.review_result, "note": r.review_note, "created_at": str(r.created_at)} for r in reviews],
    })


@router.post("/{task_id}/confirm", response_model=ApiResponse)
async def confirm_task(
    task_id: int,
    current_user: SysUser = Depends(require_permission("task:approve")),
    db: AsyncSession = Depends(get_db),
):
    """人工确认派发任务（draft→pending）"""
    result = await db.execute(select(AppActionTask).where(AppActionTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        return ApiResponse.fail("任务不存在", code=404)
    if task.status != "draft":
        return ApiResponse.fail(f"任务当前状态为{task.status}，只有草稿状态可派发")
    task.status = "pending"
    task.confirmed_by = current_user.id
    task.confirmed_at = datetime.now(timezone.utc)
    return ApiResponse.ok(message="任务已派发")


@router.post("/{task_id}/feedback", response_model=ApiResponse)
async def submit_feedback(
    task_id: int,
    body: TaskFeedbackRequest,
    current_user: SysUser = Depends(require_permission("task:feedback")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AppActionTask).where(AppActionTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        return ApiResponse.fail("任务不存在", code=404)
    if task.status not in ["pending", "processing", "overdue"]:
        return ApiResponse.fail(f"任务状态为{task.status}，不可反馈")

    feedback = AppTaskFeedback(
        task_id=task_id,
        feedback_by=current_user.id,
        feedback_content=body.feedback_content,
        action_taken=body.action_taken,
        result_description=body.result_description,
        metrics_after=body.metrics_after,
    )
    db.add(feedback)
    task.status = "feedback_submitted"
    task.completed_at = datetime.now(timezone.utc)
    return ApiResponse.ok(message="反馈提交成功，等待管理层复查")


@router.post("/{task_id}/review", response_model=ApiResponse)
async def submit_review(
    task_id: int,
    body: TaskReviewRequest,
    current_user: SysUser = Depends(require_permission("task:review")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AppActionTask).where(AppActionTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        return ApiResponse.fail("任务不存在", code=404)
    if task.status != "feedback_submitted":
        return ApiResponse.fail(f"任务状态为{task.status}，不在复查阶段")

    review = AppTaskReview(
        task_id=task_id,
        reviewed_by=current_user.id,
        review_result=body.review_result,
        review_note=body.review_note,
        metrics_before=body.metrics_before,
        metrics_after=body.metrics_after,
        improvement_confirmed=body.improvement_confirmed,
    )
    db.add(review)

    if body.review_result == "passed":
        task.status = "review_passed"
    elif body.review_result == "failed":
        task.status = "review_failed"
    # pending时任务退回 processing
    else:
        task.status = "processing"

    return ApiResponse.ok(message=f"复查完成: {body.review_result}")


@router.post("/{task_id}/close", response_model=ApiResponse)
async def close_task(
    task_id: int,
    current_user: SysUser = Depends(require_permission("task:close")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AppActionTask).where(AppActionTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        return ApiResponse.fail("任务不存在", code=404)
    task.status = "closed"
    return ApiResponse.ok(message="任务已关闭")
