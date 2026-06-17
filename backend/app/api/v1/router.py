"""API总路由注册"""
from fastapi import APIRouter
from app.api.v1 import auth, dashboard, sync, task, finance, ai, dingtalk, system, etl

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(sync.router)
api_router.include_router(task.router)
api_router.include_router(finance.router)
api_router.include_router(ai.router)
api_router.include_router(dingtalk.router)
api_router.include_router(system.router)
api_router.include_router(etl.router)
