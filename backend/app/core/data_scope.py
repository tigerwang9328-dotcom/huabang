"""数据范围工具：把用户岗位映射为可查询的数据范围。"""
from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sys import SysUser, SysUserRole, SysRole
from app.core.store_whitelist import ALLOWED_STORE_CODES, ALLOWED_INVENTORY_CODES

SCOPE_RANK = {"self": 1, "store": 2, "dept": 3, "company": 4, "all": 5}

@dataclass
class DataScope:
    scope: str
    store_codes: list[str]
    inventory_codes: list[str]
    role_codes: list[str]

    @property
    def is_limited_store(self) -> bool:
        return self.scope in {"store", "self"}


def sql_in(values: list[str] | set[str] | tuple[str, ...]) -> str:
    safe = [str(v).replace("'", "''") for v in values if str(v or "").strip()]
    if not safe:
        return "('__NO_ACCESS__')"
    return "(" + ",".join(f"'{v}'" for v in sorted(set(safe))) + ")"


async def get_data_scope(db: AsyncSession, user: SysUser) -> DataScope:
    if user.is_admin:
        return DataScope("all", sorted(ALLOWED_STORE_CODES), sorted(ALLOWED_INVENTORY_CODES), ["super_admin"])

    result = await db.execute(
        select(SysRole.code, SysRole.data_scope)
        .join(SysUserRole, SysUserRole.role_id == SysRole.id)
        .where(SysUserRole.user_id == user.id, SysRole.status == 1)
    )
    rows = result.fetchall()
    role_codes = [r[0] for r in rows]
    scope = "self"
    for _, data_scope in rows:
        candidate = data_scope or "self"
        if SCOPE_RANK.get(candidate, 1) > SCOPE_RANK.get(scope, 1):
            scope = candidate

    if scope in {"store", "self"}:
        store = (user.store_code or "").strip()
        store_codes = [store] if store and store in ALLOWED_STORE_CODES else []
        inventory_codes = [store] if store and store in ALLOWED_INVENTORY_CODES else []
    else:
        store_codes = sorted(ALLOWED_STORE_CODES)
        inventory_codes = sorted(ALLOWED_INVENTORY_CODES)
    return DataScope(scope, store_codes, inventory_codes, role_codes)
