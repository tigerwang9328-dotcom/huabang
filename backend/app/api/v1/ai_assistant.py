"""老板 AI 助手 API。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_current_user_roles, require_permission
from app.core.database import get_db
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.ai_assistant_service import AiAssistantService


router = APIRouter(prefix="/ai-assistant", tags=["老板AI助手"])


class PageContext(BaseModel):
    route: str | None = Field(default=None, max_length=256)
    stat_date: str | None = None
    store_code: str | None = Field(default=None, max_length=64)


class CreateConversationRequest(PageContext):
    pass


class AskAssistantRequest(PageContext):
    question: str = Field(min_length=1, max_length=1000)
    web_mode: Literal["auto"] = "auto"


def _service(db: AsyncSession) -> AiAssistantService:
    return AiAssistantService(db)


def _raise_access_error(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, RuntimeError):
        raise HTTPException(status_code=429, detail=str(exc))
    raise exc


@router.get("/brief", response_model=ApiResponse)
async def get_brief(
    route: str | None = None,
    stat_date: str | None = None,
    store_code: str | None = None,
    current_user: SysUser = Depends(require_permission("knowledge:ai:view")),
    roles: list[str] = Depends(get_current_user_roles),
    db: AsyncSession = Depends(get_db),
):
    service = _service(db)
    try:
        service.assert_allowed(current_user, roles)
    except Exception as exc:
        _raise_access_error(exc)
    return ApiResponse.ok(data=await service.brief(stat_date=stat_date, store_code=store_code))


@router.get("/conversations", response_model=ApiResponse)
async def list_conversations(
    current_user: SysUser = Depends(require_permission("knowledge:ai:view")),
    roles: list[str] = Depends(get_current_user_roles),
    db: AsyncSession = Depends(get_db),
):
    service = _service(db)
    try:
        service.assert_allowed(current_user, roles)
    except Exception as exc:
        _raise_access_error(exc)
    return ApiResponse.ok(data=await service.list_conversations(int(current_user.id)))


@router.post("/conversations", response_model=ApiResponse)
async def create_conversation(
    body: CreateConversationRequest,
    current_user: SysUser = Depends(require_permission("knowledge:ai:view")),
    roles: list[str] = Depends(get_current_user_roles),
    db: AsyncSession = Depends(get_db),
):
    service = _service(db)
    try:
        service.assert_allowed(current_user, roles)
        payload = await service.create_conversation(
            int(current_user.id),
            route=body.route,
            stat_date=body.stat_date,
            store_code=body.store_code,
        )
    except Exception as exc:
        _raise_access_error(exc)
    return ApiResponse.ok(data=payload)


@router.get("/conversations/{conversation_id}/messages", response_model=ApiResponse)
async def list_messages(
    conversation_id: int,
    current_user: SysUser = Depends(require_permission("knowledge:ai:view")),
    roles: list[str] = Depends(get_current_user_roles),
    db: AsyncSession = Depends(get_db),
):
    service = _service(db)
    try:
        service.assert_allowed(current_user, roles)
        payload = await service.list_messages(int(current_user.id), conversation_id)
    except Exception as exc:
        _raise_access_error(exc)
    return ApiResponse.ok(data=payload)


@router.post("/conversations/{conversation_id}/messages", response_model=ApiResponse)
async def ask_assistant(
    conversation_id: int,
    body: AskAssistantRequest,
    current_user: SysUser = Depends(require_permission("knowledge:ai:view")),
    roles: list[str] = Depends(get_current_user_roles),
    db: AsyncSession = Depends(get_db),
):
    service = _service(db)
    try:
        answer = await service.ask(
            user=current_user,
            roles=roles,
            conversation_id=conversation_id,
            question=body.question.strip(),
            route=body.route,
            stat_date=body.stat_date,
            store_code=body.store_code,
            web_mode=body.web_mode,
        )
    except Exception as exc:
        _raise_access_error(exc)
    return ApiResponse.ok(data=answer)


@router.delete("/conversations/{conversation_id}", response_model=ApiResponse)
async def archive_conversation(
    conversation_id: int,
    current_user: SysUser = Depends(require_permission("knowledge:ai:view")),
    roles: list[str] = Depends(get_current_user_roles),
    db: AsyncSession = Depends(get_db),
):
    service = _service(db)
    try:
        service.assert_allowed(current_user, roles)
        archived = await service.archive_conversation(int(current_user.id), conversation_id)
    except Exception as exc:
        _raise_access_error(exc)
    if not archived:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    return ApiResponse.ok(data={"archived": True})
