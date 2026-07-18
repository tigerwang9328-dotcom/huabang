"""老板 AI 助手定时维护任务。"""
import logging

from app.core.database import AsyncSessionLocal
from app.services.ai_assistant_service import AiAssistantService


logger = logging.getLogger(__name__)


async def cleanup_ai_assistant_conversations() -> None:
    async with AsyncSessionLocal() as db:
        count = await AiAssistantService(db).cleanup_archived()
    logger.info("老板AI助手归档会话清理完成: %s", count)
