"""华邦门店/仓库白名单配置。

业务上,只有这些 store_code / warehouse_code 才进入 DWS 汇总与库存同步。
新增/移除门店或仓库请分别修改 `ALLOWED_STORE_CODES` 与 `ALLOWED_WAREHOUSE_CODES`,
并确认 dim.dim_warehouse 中对应记录的 status 同步调整。

说明:
- 7 家门店:134681、285204、285702、185805、185808、285101、285102
- 3 个仓库:GZ001 总仓、GZ002 残次仓(API 可能显示 gz002)、GYNG 内购仓
- GYNG-2、GZ003、GZ005 等不在白名单(暂不参与经营口径)
- 销售 DWS 只取门店白名单;AI 中台库存获取/展示取 7 个销售门店 + 3 个仓库。
- 维度表仍会保留全量,以便审计。
"""
from __future__ import annotations

# 销售/统计口径白名单:只统计门店,仓库不进入销售/收款口径。
ALLOWED_STORE_CODES: frozenset[str] = frozenset({
    "134681", "285204", "285702", "185805", "185808", "285101", "285102",
})

# 库存/仓库口径白名单:只统计指定仓库,其他仓库忽略。
ALLOWED_WAREHOUSE_CODES: frozenset[str] = frozenset({
    "GZ001", "GZ002", "GYNG",
})

# AI 中台库存获取/展示口径:7 个销售门店 + 3 个仓库。
ALLOWED_INVENTORY_CODES: frozenset[str] = ALLOWED_STORE_CODES | ALLOWED_WAREHOUSE_CODES

# 给 SQL 用的字面量片段(IN 用)
def allowed_store_sql_in() -> str:
    """生成 SQL 中可直接拼接的 IN 字面量,例如 ('134681','285204',...)"""
    items = ",".join(f"'{c}'" for c in sorted(ALLOWED_STORE_CODES))
    return f"({items})"

def allowed_warehouse_sql_in() -> str:
    items = ",".join(f"'{c}'" for c in sorted(ALLOWED_WAREHOUSE_CODES))
    return f"({items})"

def allowed_inventory_sql_in() -> str:
    items = ",".join(f"'{c}'" for c in sorted(ALLOWED_INVENTORY_CODES))
    return f"({items})"


# ── 品氪会员系统销售支付方式白名单 ───────────────────────────
# 品氪口径:销售额 = 积分 + 现金 + 收钱吧 + 储值卡。
# 对应百胜小票结算方式:
# - 积分:005=会员积分
# - 现金:000=现金
# - 收钱吧:666=收钱吧POS机,971=收钱吧胜券扫码
# - 储值卡:003=五月前储值,004=VIP卡消费
# 排除:礼券、线上支付、充值流水等非品氪销售页展示口径。
ACTUAL_PAY_CODES: frozenset[str] = frozenset({
    "000",  # 现金
    "666",  # 收钱吧POS机
    "971",  # 收钱吧胜券扫码(微信)
    "003",  # 五月前储值
    "004",  # VIP卡消费/储值卡
    "005",  # 会员积分
})


def actual_pay_sql_in() -> str:
    """生成 SQL 中可直接拼接的支付方式 IN 字面量。"""
    items = ",".join(f"'{c}'" for c in sorted(ACTUAL_PAY_CODES))
    return f"({items})"
