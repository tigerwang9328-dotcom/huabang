"""临时路由验证脚本:统计 mumaren_finance_center_crud 注册的路由数。"""
from app.api.v1.mumaren_finance_center_crud import router

paths = sorted({r.path for r in router.routes})
print(f"CRUD module route count: {len(paths)}")
for p in paths:
    print(f"  {p}")
