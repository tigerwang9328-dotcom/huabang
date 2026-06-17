from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.api.v1.deps import get_current_user, get_current_user_roles, require_permission
from app.models.sys import SysUser
from app.services.ai_engine import AIEngine
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/ai", tags=["AI诊断"])


class AskRequest(BaseModel):
    question: str
    context_data: Optional[dict] = None


@router.post("/ask", response_model=ApiResponse)
async def ask_ai(
    body: AskRequest,
    current_user: SysUser = Depends(get_current_user),
    user_roles: list[str] = Depends(get_current_user_roles),
    db: AsyncSession = Depends(get_db),
):
    """AI自然语言问答（继承用户权限）"""
    engine = AIEngine(db)
    result = await engine.ask(
        question=body.question,
        current_user=current_user,
        user_roles=user_roles,
        context_data=body.context_data,
    )
    return ApiResponse.ok(data=result)
