"""牧马人财务中心 CRUD 路由测试的共享 mock 工具。

所有用例只通过 mock Db 验证路由层行为(状态机、同账簿校验、审计日志写入),
不触碰真实数据库。每个测试文件通过 ``from mumaren_crud_helpers import ...`` 复用。
"""
import os

os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("DB_PASSWORD", "test-only-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")

from app.models.mumaren_finance_center import FinanceCenterMumarenAuditLog


class _FakeUser:
    """路由依赖需要的最小用户对象。"""

    def __init__(self, user_id: int = 5, is_admin: bool = False):
        self.id = user_id
        self.is_admin = is_admin


class _MockScalars:
    def __init__(self, items):
        self._items = list(items)

    def __iter__(self):
        return iter(self._items)

    def all(self):
        return list(self._items)


class _MockResult:
    """模拟 SQLAlchemy 执行结果,支持 scalars/scalar_one/one/all。"""

    def __init__(self, *, scalar=None, scalars=None, one=None, all_rows=None):
        self._scalar = scalar
        self._scalars = list(scalars or [])
        self._one = one
        self._all = list(all_rows or [])

    def scalars(self):
        return _MockScalars(self._scalars)

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def one(self):
        return self._one

    def all(self):
        return self._all

    def first(self):
        return self._all[0] if self._all else None


class _MockDb:
    """记录 add/delete/flush/execute/get 调用,用于断言审计日志与状态机。"""

    def __init__(self, *, get_map=None, execute_results=None):
        self.added = []
        self.deleted = []
        self._get_map = get_map or {}
        self._execute_results = list(execute_results or [])
        self._exec_index = 0
        self._next_id = 1000

    async def execute(self, stmt):
        if self._exec_index < len(self._execute_results):
            result = self._execute_results[self._exec_index]
            self._exec_index += 1
            if callable(result):
                return result(stmt)
            return result
        return _MockResult(scalars=[])

    async def get(self, model, pk):
        mapping = self._get_map.get(model)
        if mapping is None:
            return None
        if isinstance(mapping, dict):
            return mapping.get(pk)
        return mapping

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                self._next_id += 1
                obj.id = self._next_id

    async def delete(self, obj):
        self.deleted.append(obj)

    def audit_logs(self, action: str | None = None) -> list:
        logs = [item for item in self.added if isinstance(item, FinanceCenterMumarenAuditLog)]
        if action:
            logs = [log for log in logs if log.action == action]
        return logs
