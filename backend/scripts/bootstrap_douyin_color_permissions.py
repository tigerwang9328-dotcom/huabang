"""Idempotently register Douyin analytics permissions in Huabang RBAC.

First release is intentionally broad for internal users: every currently
enabled platform role receives view, annotation, and product-maintenance
permissions. Export and account configuration remain administrator-only
through the existing ``is_admin`` bypass in ``require_permission``.
"""

import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.sys import SysPermission, SysRole, SysRolePermission
from app.services.operation_audit_service import write_operation_audit


PERMISSIONS = {
    "douyin_color:view": ("抖音颜色分析查看", "查看采集健康、视频和报告"),
    "douyin_color:annotate": ("抖音颜色分析标注", "维护视频片段和穿搭/商品标注"),
    "douyin_color:manage": ("抖音颜色分析维护", "维护商品、颜色、SKU 和业务配置"),
    "douyin_color:export": ("抖音颜色分析导出", "导出颜色分析报告"),
    "douyin_color:account_config": ("抖音颜色账号配置", "配置账号、令牌和采集开关"),
}
BROAD_FIRST_RELEASE_CODES = {
    "douyin_color:view",
    "douyin_color:annotate",
    "douyin_color:manage",
}


async def main() -> None:
    async with AsyncSessionLocal() as db:
        permission_ids: dict[str, int] = {}
        for code, (name, description) in PERMISSIONS.items():
            permission = (
                await db.execute(select(SysPermission).where(SysPermission.code == code))
            ).scalar_one_or_none()
            if permission is None:
                permission = SysPermission(code=code, name=name, module="douyin_color", description=description)
                db.add(permission)
                await db.flush()
            permission_ids[code] = permission.id

        roles = (await db.execute(select(SysRole).where(SysRole.status == 1))).scalars().all()
        created_assignments = 0
        for role in roles:
            for code in BROAD_FIRST_RELEASE_CODES:
                existing = await db.execute(
                    select(SysRolePermission.id).where(
                        SysRolePermission.role_id == role.id,
                        SysRolePermission.permission_id == permission_ids[code],
                    )
                )
                if existing.scalar_one_or_none() is None:
                    db.add(SysRolePermission(role_id=role.id, permission_id=permission_ids[code]))
                    created_assignments += 1

        await write_operation_audit(
            db,
            actor=None,
            module="douyin_color",
            action="rbac.bootstrap",
            target_type="permission_bundle",
            target_id="first_release",
            after_data={
                "permissions": sorted(PERMISSIONS),
                "broad_first_release_permissions": sorted(BROAD_FIRST_RELEASE_CODES),
                "active_role_count": len(roles),
                "created_assignments": created_assignments,
            },
        )
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
