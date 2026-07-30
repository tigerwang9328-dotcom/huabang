"""Idempotently register the frozen v3.1 Douyin permissions in Huabang RBAC."""

import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.sys import SysPermission, SysRole, SysRolePermission
from app.services.operation_audit_service import write_operation_audit


PERMISSIONS = {
    "douyin.collector.write": ("抖音采集器写入", "仅供采集令牌访问配置、心跳、事件和批次接口"),
    "douyin.annotation.edit": ("抖音标注编辑", "维护草稿和提交主要衣物标注"),
    "douyin.annotation.approve": ("抖音标注审核", "审批标注和跨色重叠"),
    "douyin.report.view": ("抖音报告查看", "只读颜色报告和视频钻取"),
    "douyin.report.export": ("抖音报告导出", "导出颜色分析报告"),
    "douyin.admin": ("抖音模块管理", "管理商品、账号、令牌、语义和功能开关"),
    "douyin.audit.read": ("抖音审计查看", "查看模块操作审计"),
}

# Only platform roles with a business need get an assignment. ``is_admin``
# remains the canonical administrator bypass in the existing dependency.
ROLE_PERMISSION_CODES = {
    "operation_manager": {"douyin.annotation.edit", "douyin.report.view"},
    "product_manager": {"douyin.annotation.edit", "douyin.report.view"},
    "product_specialist": {"douyin.annotation.edit"},
    "boss": {"douyin.report.view"},
    "ceo": {"douyin.report.view", "douyin.report.export"},
    "finance_manager": {"douyin.audit.read"},
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
            for code in ROLE_PERMISSION_CODES.get(role.code, set()):
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
                "role_permission_codes": {key: sorted(value) for key, value in ROLE_PERMISSION_CODES.items()},
                "active_role_count": len(roles),
                "created_assignments": created_assignments,
            },
        )
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
