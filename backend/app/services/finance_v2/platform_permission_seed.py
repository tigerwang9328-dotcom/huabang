"""Idempotent, narrowly scoped platform permission seed for Finance V2."""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import text

from app.services.finance_v2.platform_permissions import (
    FINANCE_MANAGER_ROLE,
    FINANCE_V2_READ_PERMISSION,
    FINANCE_V2_WRITE_PERMISSION,
)


class SqlExecutor(Protocol):
    async def execute(self, statement, parameters): ...


FINANCE_V2_PLATFORM_ROLE = {
    "code": FINANCE_MANAGER_ROLE,
    "name": "财务经理",
    "description": "华邦财务中心 V2 操作角色",
    "data_scope": "company",
    "sort_order": 5,
}

FINANCE_V2_PLATFORM_PERMISSION_ROWS = (
    {
        "code": FINANCE_V2_READ_PERMISSION,
        "name": "财务中心 V2 查看",
        "module": "finance",
        "description": "查看财务中心 V2 的账簿、历史账、报表和监控",
    },
    {
        "code": FINANCE_V2_WRITE_PERMISSION,
        "name": "财务中心 V2 操作",
        "module": "finance",
        "description": "提交财务中心 V2 写命令；仍受功能开关限制",
    },
)


@dataclass(frozen=True)
class FinanceV2PlatformPermissionSeedResult:
    role_code: str
    permission_codes: tuple[str, ...]


async def seed_finance_v2_platform_permissions(db: SqlExecutor) -> FinanceV2PlatformPermissionSeedResult:
    """Add only the V2 finance role/permission records and their two links."""
    await db.execute(
        text(
            """
            INSERT INTO sys.sys_role
                (name, code, description, data_scope, status, sort_order, is_builtin, is_legacy, is_hidden)
            VALUES
                (:name, :code, :description, :data_scope, 1, :sort_order, true, false, false)
            ON CONFLICT (code) DO NOTHING
            """
        ),
        FINANCE_V2_PLATFORM_ROLE,
    )
    for permission in FINANCE_V2_PLATFORM_PERMISSION_ROWS:
        await db.execute(
            text(
                """
                INSERT INTO sys.sys_permission (code, name, module, description)
                VALUES (:code, :name, :module, :description)
                ON CONFLICT (code) DO NOTHING
                """
            ),
            permission,
        )
    permission_codes = tuple(row["code"] for row in FINANCE_V2_PLATFORM_PERMISSION_ROWS)
    await db.execute(
        text(
            """
            INSERT INTO sys.sys_role_permission (role_id, permission_id)
            SELECT role.id, permission.id
            FROM sys.sys_role AS role
            CROSS JOIN sys.sys_permission AS permission
            WHERE role.code = :role_code
              AND permission.code = ANY(:permission_codes)
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"role_code": FINANCE_MANAGER_ROLE, "permission_codes": list(permission_codes)},
    )
    return FinanceV2PlatformPermissionSeedResult(
        role_code=FINANCE_MANAGER_ROLE,
        permission_codes=permission_codes,
    )
