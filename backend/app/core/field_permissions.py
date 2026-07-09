"""字段级权限工具。

业务接口后续可在返回前调用：
    data = await apply_field_permissions(db, current_user, "sales", data)
"""
from __future__ import annotations
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sys import SysUser, SysUserRole, SysRole, SysFieldPermission

def _mask_value(value: Any, rule: str):
    if value is None:
        return value
    if rule == "hide":
        return None
    if rule == "summary":
        return "汇总可见"
    if rule == "mask":
        text = str(value)
        if len(text) <= 4:
            return "*" * len(text)
        return text[:3] + "****" + text[-2:]
    return value

async def get_user_field_rules(db: AsyncSession, user: SysUser, module: str) -> dict[str, str]:
    if user.is_admin:
        return {}
    result = await db.execute(
        select(SysFieldPermission.field_name, SysFieldPermission.can_view, SysFieldPermission.mask_rule)
        .join(SysUserRole, SysUserRole.role_id == SysFieldPermission.role_id)
        .join(SysRole, SysRole.id == SysUserRole.role_id)
        .where(SysUserRole.user_id == user.id, SysRole.status == 1, SysFieldPermission.module == module)
    )
    priority = {"hide": 4, "mask": 3, "summary": 2, "none": 1, None: 1}
    rules: dict[str, str] = {}
    for field_name, can_view, mask_rule in result.fetchall():
        rule = "hide" if not can_view else (mask_rule or "none")
        key = field_name.split(".", 1)[-1]
        if priority.get(rule, 1) > priority.get(rules.get(key, "none"), 1):
            rules[key] = rule
    return rules

async def apply_field_permissions(db: AsyncSession, user: SysUser, module: str, data: Any) -> Any:
    rules = await get_user_field_rules(db, user, module)
    if not rules:
        return data
    def apply_one(row: dict):
        next_row = dict(row)
        for field, rule in rules.items():
            if field in next_row:
                next_row[field] = _mask_value(next_row[field], rule)
        return next_row
    if isinstance(data, list):
        return [apply_one(x) if isinstance(x, dict) else x for x in data]
    if isinstance(data, dict):
        return apply_one(data)
    return data
