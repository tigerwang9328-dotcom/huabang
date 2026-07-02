"""华邦门店/仓库白名单配置。

业务上,只有这些 store_code / warehouse_code 才进入 DWS 汇总与库存同步。
新增/移除门店请同步修改 `ALLOWED_STORE_CODES` 与 `ALLOWED_WAREHOUSE_CODES`,
并确认 dim.dim_warehouse 中对应记录的 status 同步调整。

说明:
- 7 家门店 + GZ001 总仓 + GZ002 残次仓(API 名"贵阳中转仓") + GYNG 内购仓
- GYNG-2、GZ003、GZ005 等不在白名单(暂不参与经营口径)
- 维度表仍会保留全量,以便审计;但 DWS/库存同步只取白名单。
"""
from __future__ import annotations

# 销售/统计口径白名单:门店 + 仓(仓的销量并入公司汇总)
ALLOWED_STORE_CODES: frozenset[str] = frozenset({
    "134681", "285204", "285702", "185805", "185808", "285101", "285102",
    "GZ001", "GZ002", "GYNG",
})

# 库存口径白名单:仅同步白名单仓库的库存
ALLOWED_WAREHOUSE_CODES: frozenset[str] = ALLOWED_STORE_CODES

# 给 SQL 用的字面量片段(IN 用)
def allowed_store_sql_in() -> str:
    """生成 SQL 中可直接拼接的 IN 字面量,例如 ('134681','285204',...)"""
    items = ",".join(f"'{c}'" for c in sorted(ALLOWED_STORE_CODES))
    return f"({items})"

def allowed_warehouse_sql_in() -> str:
    return allowed_store_sql_in()


# ── 实际收款支付方式白名单 ──────────────────────────────────────
# 业务口径:实际收款额 = 现金 + 微信 + POS + 当日充值卡(VIP卡消费)
# 排除:003=五月前储值(上月充值本月消费), 005=会员积分(非现金)
ACTUAL_PAY_CODES: frozenset[str] = frozenset({
    "000",  # 现金
    "666",  # 收钱吧POS机
    "971",  # 收钱吧胜券扫码(微信)
    "011",  # 线上支付
    "004",  # VIP卡消费(含当日充值)
})


def actual_pay_sql_in() -> str:
    """生成 SQL 中可直接拼接的支付方式 IN 字面量。"""
    items = ",".join(f"'{c}'" for c in sorted(ACTUAL_PAY_CODES))
    return f"({items})"
