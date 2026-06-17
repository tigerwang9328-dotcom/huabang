"""初始化数据库：创建所有表 + 初始化基础数据"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from app.core.database import engine, Base
from app.core.security import get_password_hash
from app.models import *  # 导入所有模型，触发 metadata 注册


INIT_ROLES = [
    {"name": "超级管理员", "code": "super_admin", "data_scope": "all", "sort_order": 0},
    {"name": "老板", "code": "boss", "data_scope": "all", "sort_order": 1},
    {"name": "股东", "code": "shareholder", "data_scope": "all", "sort_order": 2},
    {"name": "总经理", "code": "ceo", "data_scope": "all", "sort_order": 3},
    {"name": "财务负责人", "code": "finance_manager", "data_scope": "company", "sort_order": 4},
    {"name": "商品负责人", "code": "product_manager", "data_scope": "company", "sort_order": 5},
    {"name": "门店督导", "code": "area_supervisor", "data_scope": "dept", "sort_order": 6},
    {"name": "店长", "code": "store_manager", "data_scope": "store", "sort_order": 7},
    {"name": "导购", "code": "guide", "data_scope": "self", "sort_order": 8},
    {"name": "仓库负责人", "code": "warehouse_manager", "data_scope": "company", "sort_order": 9},
    {"name": "采购负责人", "code": "purchase_manager", "data_scope": "company", "sort_order": 10},
    {"name": "生产负责人", "code": "production_manager", "data_scope": "company", "sort_order": 11},
    {"name": "普通员工", "code": "staff", "data_scope": "self", "sort_order": 12},
]

INIT_PERMISSIONS = [
    # Dashboard
    {"code": "dashboard:view", "name": "查看驾驶舱", "module": "dashboard"},
    # 财务（敏感）
    {"code": "finance:profit:view", "name": "查看利润数据", "module": "finance"},
    {"code": "finance:expense:create", "name": "录入费用", "module": "finance"},
    {"code": "finance:cash:view", "name": "查看现金余额", "module": "finance"},
    {"code": "finance:cash:create", "name": "录入现金余额", "module": "finance"},
    # 数据同步
    {"code": "sync:view", "name": "查看同步状态", "module": "sync"},
    {"code": "sync:import", "name": "导入数据", "module": "sync"},
    # 任务
    {"code": "task:view", "name": "查看任务", "module": "task"},
    {"code": "task:create", "name": "创建任务", "module": "task"},
    {"code": "task:approve", "name": "确认派发任务", "module": "task"},
    {"code": "task:feedback", "name": "提交任务反馈", "module": "task"},
    {"code": "task:review", "name": "复查任务", "module": "task"},
    {"code": "task:close", "name": "关闭任务", "module": "task"},
    # 钉钉
    {"code": "dingtalk:view", "name": "查看推送日志", "module": "dingtalk"},
    {"code": "dingtalk:config", "name": "配置钉钉", "module": "dingtalk"},
    # 系统
    {"code": "system:user:view", "name": "查看用户", "module": "system"},
    {"code": "system:user:create", "name": "创建用户", "module": "system"},
    {"code": "system:user:update", "name": "修改用户", "module": "system"},
    {"code": "system:user:delete", "name": "删除用户", "module": "system"},
    {"code": "system:role:view", "name": "查看角色", "module": "system"},
    {"code": "system:param:view", "name": "查看系统参数", "module": "system"},
]

INIT_PARAMS = [
    {"param_key": "company_name", "param_value": "华邦服装", "description": "公司名称", "is_system": True},
    {"param_key": "discount_alert_threshold", "param_value": "0.5", "description": "折扣预警阈值（低于此折扣触发预警）", "is_system": True},
    {"param_key": "inventory_sellable_days_warning", "param_value": "7", "description": "可售天数预警阈值", "is_system": True},
    {"param_key": "cash_safety_days_warning", "param_value": "30", "description": "现金安全天数预警阈值", "is_system": True},
    {"param_key": "return_rate_warning", "param_value": "0.15", "description": "退货率预警阈值", "is_system": True},
    {"param_key": "task_overdue_remind_days", "param_value": "1", "description": "任务逾期前N天提醒", "is_system": True},
    {"param_key": "member_sleep_days", "param_value": "90", "description": "会员沉睡天数阈值", "is_system": True},
    {"param_key": "age_90_warning_ratio", "param_value": "0.3", "description": "90天以上库存占比预警阈值", "is_system": True},
]


async def init():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy import insert, select

    # 创建所有表
    async with engine.begin() as conn:
        await conn.execute(text("SET search_path TO public,sys,ods,dim,dwd,dws,dm,app,log,ai"))
        await conn.run_sync(Base.metadata.create_all)
    print("✅ 所有数据库表创建完成")

    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    async with AsyncSession() as session:
        # 初始化角色
        from app.models.sys import SysRole, SysPermission, SysUser, SysParam, SysDict
        for role_data in INIT_ROLES:
            exists = await session.execute(select(SysRole).where(SysRole.code == role_data["code"]))
            if not exists.scalar_one_or_none():
                session.add(SysRole(**role_data))
        await session.flush()
        print("✅ 角色初始化完成")

        # 初始化权限
        for perm_data in INIT_PERMISSIONS:
            exists = await session.execute(select(SysPermission).where(SysPermission.code == perm_data["code"]))
            if not exists.scalar_one_or_none():
                session.add(SysPermission(**perm_data))
        await session.flush()
        print("✅ 权限初始化完成")

        # 初始化系统参数
        for param in INIT_PARAMS:
            exists = await session.execute(select(SysParam).where(SysParam.param_key == param["param_key"]))
            if not exists.scalar_one_or_none():
                session.add(SysParam(**param))
        await session.flush()
        print("✅ 系统参数初始化完成")

        # 初始化超级管理员账号
        exists = await session.execute(select(SysUser).where(SysUser.username == "admin"))
        if not exists.scalar_one_or_none():
            admin = SysUser(
                username="admin",
                password_hash=get_password_hash("Admin@2024!"),
                real_name="超级管理员",
                is_admin=True,
                status=1,
            )
            session.add(admin)
            await session.flush()
            print(f"✅ 超级管理员账号创建: admin / Admin@2024!")
        else:
            print("ℹ️ 超级管理员账号已存在，跳过")

        await session.commit()

    print("\n✅ 数据库初始化完成！")
    print("📋 登录账号: admin / Admin@2024!")
    print("⚠️  请立即登录后修改默认密码！")


if __name__ == "__main__":
    asyncio.run(init())
