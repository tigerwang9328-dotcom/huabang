"""Seed the two Huabang platform permissions required by Finance V2.

Run against a recovery copy first.  The script never assigns users, changes
role state, or changes any role other than adding missing links for
``finance_manager``.
"""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.finance_v2.platform_permission_seed import (
    seed_finance_v2_platform_permissions,
)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        result = await seed_finance_v2_platform_permissions(db)
        verification = await db.execute(
            text(
                """
                SELECT role.status, count(permission.id)
                FROM sys.sys_role AS role
                LEFT JOIN sys.sys_role_permission AS role_permission ON role_permission.role_id = role.id
                LEFT JOIN sys.sys_permission AS permission
                  ON permission.id = role_permission.permission_id
                 AND permission.code = ANY(:permission_codes)
                WHERE role.code = :role_code
                GROUP BY role.status
                """
            ),
            {"role_code": result.role_code, "permission_codes": list(result.permission_codes)},
        )
        row = verification.one_or_none()
        if row is None or row[0] != 1 or row[1] != len(result.permission_codes):
            await db.rollback()
            raise RuntimeError("finance_manager platform permission seed verification failed")
        await db.commit()
    print(
        json.dumps(
            {"role_code": result.role_code, "permission_codes": result.permission_codes, "status": "ready"},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
