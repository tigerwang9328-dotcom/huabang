"""API总路由注册"""
from fastapi import APIRouter
from app.api.v1 import auth, dashboard, sync, task, finance, ai, dingtalk, system, etl, rules, report, acceptance, baison, dingtalk_finance, hr, store, product, inventory

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
api_router.include_router(rules.router)
api_router.include_router(report.router)
api_router.include_router(acceptance.router)
api_router.include_router(baison.router)
api_router.include_router(store.router)
api_router.include_router(product.router)
api_router.include_router(inventory.router)
api_router.include_router(dingtalk_finance.router)
api_router.include_router(hr.router)
