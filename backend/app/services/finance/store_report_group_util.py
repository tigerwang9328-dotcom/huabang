"""
店铺经营日报 — 嵌套店铺组工具
- 组树(parent_group_id)；店铺直属一个节点，自动归入所有祖先组 → laminar(子集/不相交)。
- 递归子树聚合(全字段)；产出统一有序行 report_rows(成员店行 + 组合计行，含 level/row_kind)，
  页面与导出 Excel 共用同一份 → 行序、汇总完全一致。
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 组合计行需要对“成员/子组”按字段求和的全部数值列（覆盖 Excel 23 列 + dashboard 子集）
_SUM_FIELDS = [
    "sale_amount", "shipped_qty", "order_count", "actual_order_count", "actual_product_qty",
    "refund_amount", "refund_count",
    "sale_cogs", "ad_cost", "refund_net_amount", "platform_net_amount", "refund_cogs_back",
    "freight_insurance", "package_cost", "express_cost", "promotion_cost",
    "return_labor_cost", "goods_loss_cost", "compensation_amount", "total_expense", "profit",
]


def _div(a, b):
    return round(a / b, 6) if b else 0.0


async def load_group_tree(db: AsyncSession):
    """返回 (groups_by_id, children_of, members_of)
    groups_by_id: {gid: {id,name,parent_group_id}}（仅启用组）
    children_of:  {gid: [子组id...]}，顶层父为 None
    members_of:   {gid: [store_id...]}（直属成员）
    """
    grows = await db.execute(text("""
        SELECT id, name, parent_group_id
        FROM biz_store_report_groups
        WHERE is_active = true
    """))
    groups_by_id, children_of = {}, {}
    for r in grows.fetchall():
        groups_by_id[int(r.id)] = {
            "id": int(r.id), "name": r.name,
            "parent_group_id": int(r.parent_group_id) if r.parent_group_id is not None else None,
        }
    # 父若停用/不存在，视为顶层
    valid = set(groups_by_id)
    for gid, g in groups_by_id.items():
        pid = g["parent_group_id"] if g["parent_group_id"] in valid else None
        g["parent_group_id"] = pid
        children_of.setdefault(pid, []).append(gid)

    mrows = await db.execute(text("""
        SELECT m.group_id, m.store_id
        FROM biz_store_report_group_members m
        JOIN biz_store_report_groups g ON g.id = m.group_id
        WHERE g.is_active = true
    """))
    members_of = {}
    for r in mrows.fetchall():
        members_of.setdefault(int(r.group_id), []).append(int(r.store_id))
    return groups_by_id, children_of, members_of


def _aggregate(rows: list) -> dict:
    """对若干已算好的店铺行求子树合计，rate/roi 重算并除零保护。"""
    agg = {f: 0 for f in _SUM_FIELDS}
    for r in rows:
        for f in _SUM_FIELDS:
            agg[f] += float(r.get(f) or 0)
    for f in _SUM_FIELDS:
        agg[f] = round(agg[f], 2)
    sale, shipped, ad, profit, orders, actual_qty = (
        agg["sale_amount"], agg["shipped_qty"], agg["ad_cost"], agg["profit"],
        agg["order_count"], agg["actual_product_qty"],
    )
    refund_only_weight = sum(
        float(r.get("refund_only_rate") or 0) * int(r.get("shipped_qty") or 0)
        for r in rows
    )
    agg["shipped_qty"] = int(shipped)
    agg["order_count"] = int(orders)
    agg["actual_order_count"] = int(agg["actual_order_count"])
    agg["actual_product_qty"] = int(agg["actual_product_qty"])
    agg["refund_count"] = int(agg["refund_count"])
    agg["refund_rate"] = _div(agg["refund_count"], agg["shipped_qty"])
    agg["refund_only_rate"] = _div(refund_only_weight, agg["shipped_qty"])
    agg["profit_rate"] = _div(profit, sale)
    agg["profit_per_order"] = round(profit / orders, 2) if orders else 0.0
    agg["ad_cost_per_actual_product"] = round(ad / actual_qty, 2) if actual_qty else 0.0
    agg["roi"] = round(sale / ad, 4) if ad else 0.0
    if profit < 0:
        agg["biz_status"] = "亏损"
    elif agg["profit_rate"] < 0.05:
        agg["biz_status"] = "微利"
    else:
        agg["biz_status"] = "正常"
    return agg


def build_report_rows(store_rows: list, tree) -> tuple:
    """生成统一有序行。返回 (report_rows, group_subtotals)
    report_rows: 顶层(未分组店 + 顶层组块)按销售额降序；组块内 = 成员店(降序) + 子组块(递归) + 本组合计行(块末)。
    每行带 row_kind(store|group_total)、level(缩进层级)、group_id、group_name。
    无任何分组时退化为原始 store_rows(加 row_kind=store,level=0)。
    """
    groups_by_id, children_of, members_of = tree
    rows_by_store = {int(r["store_id"]): r for r in store_rows if r.get("store_id") is not None}

    # 子树店铺集合(用于聚合与排序)
    subtree_cache: dict = {}
    def subtree_store_ids(gid):
        if gid in subtree_cache:
            return subtree_cache[gid]
        ids = list(members_of.get(gid, []))
        for c in children_of.get(gid, []):
            ids.extend(subtree_store_ids(c))
        subtree_cache[gid] = ids
        return ids

    def subtree_rows(gid):
        return [rows_by_store[s] for s in subtree_store_ids(gid) if s in rows_by_store]

    def group_sale(gid):
        return sum(float(r.get("sale_amount") or 0) for r in subtree_rows(gid))

    subtotals = []

    def emit_group(gid, depth):
        g = groups_by_id[gid]
        out = []
        # 直属成员店(在场的) + 子组，混排按销售额降序
        entries = []
        for sid in members_of.get(gid, []):
            r = rows_by_store.get(sid)
            if r is not None:
                entries.append(("store", float(r.get("sale_amount") or 0), r))
        for cid in children_of.get(gid, []):
            entries.append(("group", group_sale(cid), cid))
        entries.sort(key=lambda e: e[1], reverse=True)
        for kind, _key, obj in entries:
            if kind == "store":
                out.append({**obj, "row_kind": "store", "level": depth + 1,
                            "group_id": gid, "group_name": g["name"]})
            else:
                out.extend(emit_group(obj, depth + 1))
        # 本组合计行(块末)
        agg = _aggregate(subtree_rows(gid))
        total = {
            **agg, "row_kind": "group_total", "is_group_subtotal": True,
            "level": depth, "group_id": gid, "group_name": g["name"],
            "store_id": None, "platform": "组", "has_params": True,
            "store_name": f"{g['name']} 合计（{len(subtree_store_ids(gid))}店）",
            "store_count": len(subtree_store_ids(gid)),
        }
        subtotals.append(total)
        out.append(total)
        return out

    # 顶层：未分组店 + 顶层组
    grouped_ids = set()
    for gid in groups_by_id:
        grouped_ids.update(members_of.get(gid, []))

    top_entries = []
    for r in store_rows:
        sid = r.get("store_id")
        if sid is None or int(sid) not in grouped_ids:
            top_entries.append(("store", float(r.get("sale_amount") or 0), r))
    for gid in children_of.get(None, []):
        top_entries.append(("group", group_sale(gid), gid))
    top_entries.sort(key=lambda e: e[1], reverse=True)

    report_rows = []
    for kind, _key, obj in top_entries:
        if kind == "store":
            report_rows.append({**obj, "row_kind": "store", "level": 0,
                                "group_id": None, "group_name": None})
        else:
            report_rows.extend(emit_group(obj, 0))
    return report_rows, subtotals
