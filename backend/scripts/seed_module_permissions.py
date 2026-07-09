"""初始化华邦AI中台 10 大模块岗位权限矩阵"""
import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

MODULES = {
    "dashboard": ("经营概览", [
        ("dashboard:overview:view", "经营概览查看"),
        ("dashboard:profit:view", "利润指标查看"),
        ("dashboard:cost:view", "成本指标查看"),
    ]),
    "diagnosis": ("AI经营诊断", [
        ("diagnosis:overall:view", "总体经营诊断"),
        ("diagnosis:sales:view", "销售诊断"),
        ("diagnosis:product:view", "商品诊断"),
        ("diagnosis:inventory:view", "库存诊断"),
        ("diagnosis:finance:view", "财务诊断"),
        ("diagnosis:hr:view", "人力诊断"),
    ]),
    "sales": ("销售中心", [
        ("sales:overview:view", "销售总览"),
        ("sales:offline:view", "线下销售"),
        ("sales:online:view", "线上销售"),
        ("sales:store:view", "门店销售"),
        ("sales:guide:view", "导购销售"),
        ("sales:warning:view", "销售异常"),
    ]),
    "product": ("商品经营", [
        ("product:overview:view", "商品总览"),
        ("product:master:view", "商品主档"),
        ("product:sku:view", "SKU档案"),
        ("product:turnover:view", "动销分析"),
        ("product:replenishment:view", "爆款补货"),
        ("product:clearance:view", "滞销清仓"),
        ("product:edit", "商品编辑"),
    ]),
    "purchase": ("采购协同", [
        ("purchase:overview:view", "采购总览"),
        ("purchase:order:view", "采购订单"),
        ("purchase:supplier:view", "供应商管理"),
        ("purchase:arrival:view", "到货跟踪"),
        ("purchase:edit", "采购编辑"),
    ]),
    "inventory": ("库存风控", [
        ("inventory:overview:view", "库存总览"),
        ("inventory:balance:view", "库存余额"),
        ("inventory:warehouse:view", "仓库档案"),
        ("inventory:age:view", "库龄分析"),
        ("inventory:transfer:view", "调拨建议"),
        ("inventory:warning:view", "异常库存"),
        ("inventory:edit", "库存编辑"),
    ]),
    "finance": ("财务利润", [
        ("finance:overview:view", "财务首页"),
        ("finance:profit:view", "利润分析"),
        ("finance:expense:view", "费用分析"),
        ("finance:reimbursement:view", "报销管理"),
        ("finance:payment:view", "付款申请"),
        ("finance:cash:view", "现金安全"),
        ("finance:cost:view", "成本查看"),
        ("finance:edit", "财务编辑"),
    ]),
    "hr": ("人力资源", [
        ("hr:overview:view", "人事首页"),
        ("hr:employee:view", "员工档案"),
        ("hr:attendance:view", "考勤管理"),
        ("hr:leave:view", "请假外出"),
        ("hr:performance:view", "人效分析"),
        ("hr:salary:view", "薪资查看"),
        ("hr:edit", "人事编辑"),
    ]),
    "knowledge": ("知识中枢", [
        ("knowledge:ai:view", "AI助手"),
        ("knowledge:doc:view", "制度文档"),
        ("knowledge:qa:view", "AI问答记录"),
        ("knowledge:edit", "知识编辑"),
    ]),
    "system": ("系统设置", [
        ("system:dashboard:view", "管理后台"),
        ("system:user:view", "用户查看"),
        ("system:user:create", "用户创建"),
        ("system:user:update", "用户编辑"),
        ("system:user:delete", "用户删除"),
        ("system:role:view", "角色查看"),
        ("system:role:create", "角色创建"),
        ("system:role:update", "角色编辑"),
        ("system:role:delete", "角色删除"),
        ("system:permission:view", "权限查看"),
        ("system:permission:update", "权限配置"),
        ("system:register:review", "注册审核"),
        ("system:data-scope:update", "数据权限配置"),
        ("system:field-permission:update", "字段权限配置"),
        ("system:sync:view", "数据同步查看"),
        ("system:sync:run", "数据同步执行"),
        ("system:baison-api:view", "百胜API查看"),
        ("system:baison-api:update", "百胜API配置"),
        ("system:dingtalk:view", "钉钉查看"),
        ("system:dingtalk:update", "钉钉配置"),
        ("system:log:view", "日志查看"),
        ("system:security:update", "安全设置"),
        ("system:param:view", "系统参数查看"),
        ("system:user:reset-password", "用户重置密码"),
        ("system:user:disable", "用户停用"),
        ("system:user:enable", "用户启用"),
        ("system:operation-log:view", "操作日志查看"),
    ]),
}

ROLES = [
    ("super_admin", "超级管理员", "all", 0),
    ("boss", "BOSS", "all", 1),
    ("ceo", "总经理", "all", 2),
    ("product_manager", "商品经理", "company", 3),
    ("product_specialist", "商品专员", "dept", 4),
    ("finance_manager", "财务经理", "company", 5),
    ("accountant", "会计", "dept", 6),
    ("cashier", "出纳", "dept", 7),
    ("warehouse_manager", "仓库主管", "company", 8),
    ("operation_manager", "运营经理", "company", 9),
    ("store_manager", "店长", "store", 10),
    ("guide", "导购", "self", 11),
]

ALL = [code for _, perms in MODULES.values() for code, _ in perms]
VIEW_ALL = [c for c in ALL if c.endswith(':view')]
M = {
    "super_admin": ALL,
    "boss": [c for c in VIEW_ALL if not c.startswith('system:')] + ["system:dashboard:view", "system:log:view", "system:operation-log:view", "system:permission:view", "system:user:view", "system:role:view"],
    "ceo": [c for c in VIEW_ALL if not c.startswith('system:')] + ["system:dashboard:view", "system:log:view", "system:operation-log:view", "system:permission:view", "system:user:view", "system:role:view"],
    "product_manager": [
        "dashboard:overview:view", "diagnosis:product:view", "diagnosis:inventory:view",
        "sales:overview:view", "sales:store:view", "product:overview:view", "product:master:view", "product:sku:view",
        "product:turnover:view", "product:replenishment:view", "product:clearance:view", "product:edit",
        "purchase:overview:view", "purchase:order:view", "purchase:arrival:view",
        "inventory:overview:view", "inventory:balance:view", "inventory:warning:view", "knowledge:ai:view", "knowledge:doc:view",
    ],
    "product_specialist": [
        "diagnosis:product:view", "product:overview:view", "product:master:view", "product:sku:view",
        "product:turnover:view", "inventory:overview:view", "inventory:balance:view", "purchase:arrival:view", "knowledge:doc:view",
    ],
    "finance_manager": [
        "dashboard:overview:view", "dashboard:profit:view", "dashboard:cost:view", "diagnosis:finance:view",
        "sales:overview:view", "sales:offline:view", "sales:store:view", "product:sku:view", "purchase:order:view",
        "inventory:overview:view", "inventory:balance:view", "finance:overview:view", "finance:profit:view", "finance:expense:view",
        "finance:reimbursement:view", "finance:payment:view", "finance:cash:view", "finance:cost:view", "finance:edit",
        "knowledge:ai:view", "system:dashboard:view",
    ],
    "accountant": [
        "diagnosis:finance:view", "finance:overview:view", "finance:profit:view", "finance:expense:view",
        "finance:reimbursement:view", "finance:cost:view", "knowledge:doc:view",
    ],
    "cashier": [
        "finance:overview:view", "finance:payment:view", "finance:cash:view", "knowledge:doc:view",
    ],
    "warehouse_manager": [
        "diagnosis:inventory:view", "product:master:view", "product:sku:view", "purchase:arrival:view",
        "inventory:overview:view", "inventory:balance:view", "inventory:warehouse:view", "inventory:age:view",
        "inventory:transfer:view", "inventory:warning:view", "inventory:edit", "knowledge:doc:view",
    ],
    "operation_manager": [
        "dashboard:overview:view", "diagnosis:overall:view", "diagnosis:sales:view", "diagnosis:inventory:view",
        "sales:overview:view", "sales:offline:view", "sales:online:view", "sales:store:view", "sales:guide:view", "sales:warning:view",
        "product:overview:view", "inventory:overview:view", "inventory:balance:view", "inventory:warning:view", "knowledge:ai:view",
    ],
    "store_manager": [
        "dashboard:overview:view", "diagnosis:sales:view", "sales:overview:view", "sales:offline:view", "sales:store:view", "sales:guide:view",
        "product:overview:view", "inventory:overview:view", "inventory:balance:view", "hr:performance:view", "knowledge:ai:view", "knowledge:doc:view",
    ],
    "guide": [
        "sales:guide:view", "knowledge:ai:view", "knowledge:doc:view",
    ],
}

async def main():
    async with AsyncSessionLocal() as db:
        # permissions
        for module, (module_name, perms) in MODULES.items():
            for code, name in perms:
                await db.execute(text("""
                    INSERT INTO sys.sys_permission(code, name, module, description)
                    VALUES (:code, :name, :module, :desc)
                    ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, module=EXCLUDED.module, description=EXCLUDED.description
                """), {"code": code, "name": name, "module": module, "desc": module_name})
        # roles
        for code, name, scope, sort in ROLES:
            await db.execute(text("""
                INSERT INTO sys.sys_role(name, code, description, data_scope, status, sort_order, is_builtin, is_legacy, is_hidden)
                VALUES (:name, :code, :desc, :scope, 1, :sort, true, false, false)
                ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, description=EXCLUDED.description, data_scope=EXCLUDED.data_scope, status=1, sort_order=EXCLUDED.sort_order, is_builtin=true, is_legacy=false, is_hidden=false
            """), {"name": name, "code": code, "desc": "华邦AI中台岗位角色", "scope": scope, "sort": sort})
        # role permissions
        for role_code, perms in M.items():
            await db.execute(text("""
                INSERT INTO sys.sys_role_permission(role_id, permission_id)
                SELECT r.id, p.id
                FROM sys.sys_role r, sys.sys_permission p
                WHERE r.code=:role_code AND p.code = ANY(:perms)
                ON CONFLICT (role_id, permission_id) DO NOTHING
            """), {"role_code": role_code, "perms": perms})
        
        # mark legacy roles without deleting them
        await db.execute(text("""
            UPDATE sys.sys_role
            SET is_legacy=true, is_hidden=true
            WHERE code <> ALL(:core_codes)
        """), {"core_codes": [r[0] for r in ROLES]})
        await db.commit()
        rc = (await db.execute(text("SELECT count(*) FROM sys.sys_role"))).scalar()
        pc = (await db.execute(text("SELECT count(*) FROM sys.sys_permission"))).scalar()
        rpc = (await db.execute(text("SELECT count(*) FROM sys.sys_role_permission"))).scalar()
        print({"roles": rc, "permissions": pc, "role_permissions": rpc})

if __name__ == '__main__':
    asyncio.run(main())
