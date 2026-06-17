"""华邦AI中台 - FastAPI 主入口"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.core.config import settings
from app.core.logger import setup_logging
from app.core.database import check_db_connection
from app.core.redis import check_redis_connection
from app.core.exceptions import (
    AppException, app_exception_handler,
    validation_exception_handler, http_exception_handler,
    global_exception_handler,
)
from app.api.v1.router import api_router
from app.jobs.scheduler import scheduler, setup_jobs

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    setup_logging()
    logger.info("🚀 华邦AI中台启动中...")

    # 检查数据库连接
    db_ok = await check_db_connection()
    if not db_ok:
        logger.error("❌ 数据库连接失败！请检查PostgreSQL配置")
    else:
        logger.info("✅ 数据库连接正常")

    # 检查Redis连接（非致命）
    redis_ok = await check_redis_connection()
    logger.info(f"Redis {"connected" if redis_ok else "disconnected (rate-limit fallback)"}")

    # 启动定时任务
    try:
        setup_jobs()
        scheduler.start()
        logger.info("✅ 定时任务调度器已启动")
    except Exception as e:
        logger.error(f"⚠️ 定时任务启动失败: {e}")

    logger.info(f"✅ 华邦AI中台启动完成 | ENV={settings.APP_ENV} | DEBUG={settings.APP_DEBUG}")
    yield

    # 关闭
    if scheduler.running:
        scheduler.shutdown(wait=False)
    logger.info("👋 华邦AI中台已关闭")


app = FastAPI(
    title="华邦AI中台",
    description="华邦服装公司AI经营中台 - 第一阶段MVP",
    version="1.0.0",
    docs_url="/docs" if settings.APP_DEBUG or settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_DEBUG or settings.APP_ENV != "production" else None,
    lifespan=lifespan,
)

# CORS（严格限制允许域名）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)

# 统一异常处理
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# 注册路由
app.include_router(api_router)


@app.get("/health", tags=["系统"])
async def health_check():
    """健康检查"""
    db_ok = await check_db_connection()
    redis_ok = await check_redis_connection()
    return {
        "status": "ok",
        "version": "1.0.0",
        "env": settings.APP_ENV,
        "database": "connected" if db_ok else "disconnected",
        "redis": "connected" if redis_ok else "disconnected",
        "dingtalk_push_enabled": settings.DINGTALK_PUSH_ENABLED,
        "ai_provider": settings.AI_PROVIDER,
    }
