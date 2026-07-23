"""
销售月报 - 配置项读取
=====================
所有可调参数都走 sys_settings，避免硬编码。
"""
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_DEFAULTS = {
    "sales_monthly_report.package_unit_cost":    "0.5",
    "sales_monthly_report.goods_loss_unit_cost": "1.0",
    "sales_monthly_report.return_loss_enabled":  "true",
}


async def _get_setting(db: AsyncSession, key: str) -> str:
    r = await db.execute(text("SELECT value FROM sys_settings WHERE key=:k"), {"k": key})
    row = r.scalar_one_or_none()
    return row.strip() if row else _DEFAULTS.get(key, "")


async def get_package_unit_cost(db: AsyncSession) -> Decimal:
    v = await _get_setting(db, "sales_monthly_report.package_unit_cost")
    try:
        return Decimal(v)
    except Exception:
        return Decimal("0.5")


async def get_goods_loss_unit_cost(db: AsyncSession) -> Decimal:
    v = await _get_setting(db, "sales_monthly_report.goods_loss_unit_cost")
    try:
        return Decimal(v)
    except Exception:
        return Decimal("1.0")


async def is_return_loss_enabled(db: AsyncSession) -> bool:
    v = await _get_setting(db, "sales_monthly_report.return_loss_enabled")
    return v.lower() not in ("false", "0", "no", "off")
