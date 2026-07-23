"""
日报计算服务 - 按公式从 dm_store_daily + finance_store_daily_params 计算完整日报指标
======================================================================================
字段字母对照（与 Excel 公式拆解对齐）：
  I  = sale_amount          销售金额
  J  = final_return_rate    最终退货率（优先级：人工维护当月 > 近期历史月 > 实际数据兜底）
  M  = shipped_qty          发货件数
  N  = order_count          销售单数
  O  = sale_cogs            销售商品成本
  F  = ad_cost              广告费
  C  = compensation_amount  发货赔付、其他赔付
  K  = I * (1 - J)         退款后金额
  L  = K * platform_income_rate  实际金额（平台收入）
  P  = O * J               退货产品成本（冲回）
  Q  = M * freight_insurance_unit_cost   运费险
  R  = N * package_unit_cost             包装成本
  S  = M * express_unit_cost             快递费
  U  = N * (1-J) * promotion_unit_cost   推广成本
  V  = J * N * return_labor_unit_cost    退货人工
  W  = M * goods_loss_unit_cost          货值损耗
  E  = Q+R+S+U+V+W+F+C     费用合计（不含商品成本）
  D  = L - O + P - E       利润
  G  = D / I               利润率
  H  = D / N               每单利润

退货率取数优先级：
  1. finance_store_daily_params 当前月 estimated_return_rate > 0  → manual_current_month
  2. 最近一个有效历史月份的 estimated_return_rate                  → manual_latest_month:YYYY-MM
  3. dm_store_daily.refund_rate（实际数据兜底）                    → actual_data_fallback
"""
import logging
from datetime import date
from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _build_summary_text(sale: float, refund: float, cogs: float, net: float,
                        daily_fixed: float, platform_today: dict, avg7: float) -> str:
    """根据日报数据（发货口径）生成经营诊断摘要，与首页 API 卡片口径一致"""
    lines = []
    refund_rate = refund / sale if sale > 0 else 0
    profit_rate = net / sale if sale > 0 else 0
    if avg7 > 0:
        pct = (sale - avg7) / avg7 * 100
        if pct > 10:
            lines.append(f"📈 今日全公司发货销售额 ¥{sale:,.0f}，较近7日均值上涨 {pct:.1f}%，销售表现强劲。")
        elif pct < -10:
            lines.append(f"📉 今日全公司发货销售额 ¥{sale:,.0f}，较近7日均值下滑 {abs(pct):.1f}%，需关注销量变化。")
        else:
            lines.append(f"📊 今日全公司发货销售额 ¥{sale:,.0f}，较近7日均值持平（{pct:+.1f}%），运营稳定。")
    else:
        lines.append(f"📊 今日全公司发货销售额 ¥{sale:,.0f}。")
    if platform_today:
        top_plat, top_amt = max(platform_today.items(), key=lambda x: x[1])
        top_pct = top_amt / sale * 100 if sale > 0 else 0
        warn = "平台集中度偏高，建议加强其他渠道运营。" if top_pct > 70 else ""
        lines.append(f"🏆 销售主力：{top_plat} ¥{top_amt:,.0f}（占比 {top_pct:.0f}%）。{warn}")
    if refund_rate > 0.35:
        lines.append(f"⚠️ 预估退货率 {refund_rate*100:.1f}% 偏高，建议重点排查高退款 SKU 与发货质量。")
    elif refund_rate > 0.20:
        lines.append(f"⚡ 预估退货率 {refund_rate*100:.1f}%，处于正常偏高区间，持续关注退款趋势。")
    else:
        lines.append(f"✅ 预估退货率 {refund_rate*100:.1f}%，处于健康区间。")
    if cogs > 0:
        lines.append(f"🏢 商品成本 ¥{cogs:,.0f}。")
    if daily_fixed > 0:
        lines.append(f"🏢 日均固定费用 ¥{daily_fixed:,.0f}。")
    if net < 0:
        lines.append(f"🔴 今日纯利润 ¥{net:,.0f}（亏损），请检查退货与成本结构。")
    elif profit_rate < 0.10:
        lines.append(f"🟡 今日纯利润 ¥{net:,.0f}，利润率 {profit_rate*100:.1f}%，利润空间偏薄。")
    else:
        lines.append(f"💰 今日纯利润 ¥{net:,.0f}，利润率 {profit_rate*100:.1f}%，盈利状况良好。")
    tips = []
    if refund_rate > 0.3:
        tips.append("重点跟进退款工单")
    if platform_today and sale > 0 and max(platform_today.values()) / sale > 0.7:
        tips.append("加强多平台流量布局")
    tips = tips or ["持续关注各店铺日报异动"]
    lines.append("📋 建议：" + "，".join(tips) + "。")
    return "\n".join(lines)



def _f(v) -> float:
    if v is None:
        return 0.0
    return float(v)


def _normalize_return_rate(value) -> Optional[float]:
    """标准化退货率：小数(0.35)直接用；百分比(35)→除以100；超出范围→None"""
    if value is None:
        return None
    v = _f(value)
    if v < 0:
        return None
    if v == 0:
        return 0.0
    if v <= 1.0:
        return v
    if v <= 100.0:
        logger.warning(f"[DailyReport] return_rate value {v} > 1, treating as percent → {v/100:.4f}")
        return v / 100.0
    logger.warning(f"[DailyReport] invalid return_rate value {v} > 100, discarding")
    return None


async def _load_params(db: AsyncSession, month: str) -> dict:
    """加载指定月份的所有店铺参数，key=store_id(int)"""
    r = await db.execute(text("""
        SELECT
            store_id,
            platform_commission_rate,
            platform_income_rate,
            estimated_return_rate,
            refund_only_rate,
            freight_insurance_unit_cost,
            express_unit_cost,
            package_unit_cost,
            return_labor_unit_cost,
            goods_loss_unit_cost,
            promotion_unit_cost,
            return_rate_warning_threshold,
            warning_enabled
        FROM finance_store_daily_params
        WHERE month = :month
    """), {"month": month})
    result = {}
    for row in r.mappings():
        result[int(row["store_id"])] = dict(row)
    return result


async def _load_fallback_return_rates(
    db: AsyncSession,
    store_ids: list,
    before_month: str,
) -> dict:
    """查找每个店铺最近一个有效的 estimated_return_rate（before_month 之前的月份）"""
    if not store_ids:
        return {}
    rows = await db.execute(text("""
        SELECT DISTINCT ON (store_id)
            store_id,
            month,
            estimated_return_rate,
            return_rate_warning_threshold,
            warning_enabled
        FROM finance_store_daily_params
        WHERE store_id = ANY(:ids)
          AND month < :m
          AND estimated_return_rate > 0
        ORDER BY store_id, month DESC
    """), {"ids": list(store_ids), "m": before_month})
    return {
        int(row.store_id): {
            "estimated_return_rate":      float(row.estimated_return_rate),
            "source_month":               row.month,
            "return_rate_warning_threshold": float(row.return_rate_warning_threshold or 0.08),
            "warning_enabled":            bool(row.warning_enabled),
        }
        for row in rows.fetchall()
    }


_FALLBACK_PARAM_FIELDS = [
    "platform_income_rate",
    "refund_only_rate",
    "freight_insurance_unit_cost",
    "express_unit_cost",
    "package_unit_cost",
    "return_labor_unit_cost",
    "goods_loss_unit_cost",
    "promotion_unit_cost",
    "return_rate_warning_threshold",
]
_PLATFORM_DEFAULT_FIELDS = [
    f for f in _FALLBACK_PARAM_FIELDS if f != "refund_only_rate"
]


async def _load_latest_param_values(
    db: AsyncSession,
    store_ids: list,
    before_month: str,
) -> dict:
    """逐字段加载最近历史月份非零参数，用于补齐当月半截参数。"""
    if not store_ids:
        return {}
    rows = await db.execute(text("""
        SELECT
            store_id,
            month,
            platform_income_rate,
            refund_only_rate,
            freight_insurance_unit_cost,
            express_unit_cost,
            package_unit_cost,
            return_labor_unit_cost,
            goods_loss_unit_cost,
            promotion_unit_cost,
            return_rate_warning_threshold
        FROM finance_store_daily_params
        WHERE store_id = ANY(:ids)
          AND month < :m
        ORDER BY store_id, month DESC
    """), {"ids": list(store_ids), "m": before_month})

    out: dict[int, dict] = {}
    for row in rows.mappings():
        sid = int(row["store_id"])
        acc = out.setdefault(sid, {"source_months": {}})
        for field in _FALLBACK_PARAM_FIELDS:
            if field in acc:
                continue
            val = row.get(field)
            if val is not None and float(val) != 0:
                acc[field] = float(val)
                acc["source_months"][field] = row["month"]
    return out


def _apply_missing_param_fallback(params_map: dict, fallback_values: dict) -> None:
    """当月字段为 0/空时，用最近历史非零值补齐；不覆盖当月已填值。"""
    for sid, current in params_map.items():
        fb = fallback_values.get(int(sid))
        if not fb:
            continue
        sources = fb.get("source_months", {})
        used = []
        for field in _FALLBACK_PARAM_FIELDS:
            cur_val = current.get(field)
            if (cur_val is None or float(cur_val or 0) == 0) and field in fb:
                current[field] = fb[field]
                used.append(f"{field}:{sources.get(field)}")
        if used:
            current["param_fallback_source"] = ",".join(used)


async def _load_platform_default_values(db: AsyncSession, month: str) -> dict:
    """同平台已配置店铺的非零参数中位数，用作新店费用兜底。"""
    rows = await db.execute(text("""
        SELECT
            store_name,
            platform,
            platform_income_rate,
            refund_only_rate,
            freight_insurance_unit_cost,
            express_unit_cost,
            package_unit_cost,
            return_labor_unit_cost,
            goods_loss_unit_cost,
            promotion_unit_cost,
            return_rate_warning_threshold
        FROM finance_store_daily_params
        WHERE month <= :m
    """), {"m": month})
    from app.core.platform_resolver import resolve_store_platform

    buckets: dict[str, dict[str, list[float]]] = {}
    for row in rows.mappings():
        platform = resolve_store_platform(row.get("store_name"), row.get("platform")).label
        p_bucket = buckets.setdefault(platform, {field: [] for field in _PLATFORM_DEFAULT_FIELDS})
        for field in _PLATFORM_DEFAULT_FIELDS:
            val = row.get(field)
            if val is not None and float(val) != 0:
                p_bucket[field].append(float(val))

    def median(vals: list[float]) -> float | None:
        if not vals:
            return None
        vals = sorted(vals)
        mid = len(vals) // 2
        if len(vals) % 2:
            return vals[mid]
        return (vals[mid - 1] + vals[mid]) / 2

    out: dict[str, dict[str, float]] = {}
    for platform, fields in buckets.items():
        defaults = {}
        for field, vals in fields.items():
            mval = median(vals)
            if mval is not None:
                defaults[field] = mval
        if defaults:
            out[platform] = defaults
    return out


def _apply_platform_defaults(params: dict, defaults: dict | None) -> dict:
    if not defaults:
        return params
    out = dict(params)
    used = []
    for field in _PLATFORM_DEFAULT_FIELDS:
        if (out.get(field) is None or float(out.get(field) or 0) == 0) and field in defaults:
            out[field] = defaults[field]
            used.append(field)
    if used:
        out["platform_default_source"] = ",".join(used)
    return out


_DEFAULT_PARAMS = {
    "platform_commission_rate":       0.0,
    "platform_income_rate":           1.0,
    "estimated_return_rate":          0.0,
    "refund_only_rate":               0.0,
    "freight_insurance_unit_cost":    0.0,
    "express_unit_cost":              0.0,
    "package_unit_cost":              0.0,
    "return_labor_unit_cost":         0.0,
    "goods_loss_unit_cost":           0.0,
    "promotion_unit_cost":            0.0,
    "return_rate_warning_threshold":  0.08,
    "warning_enabled":                True,
}


def _compute_store_row(dm: dict, params: dict) -> dict:
    p = {**_DEFAULT_PARAMS, **params}

    I = _f(dm.get("sale_amount"))
    M = int(dm.get("shipped_qty") or 0)
    N = int(dm.get("order_count") or 0)
    actual_order_count = int(dm.get("actual_order_count") or 0)
    actual_product_qty = int(dm.get("actual_product_qty") or 0)
    O = _f(dm.get("sale_cogs"))
    F = _f(dm.get("ad_cost"))
    C = _f(dm.get("compensation_amount"))
    refund_amount = _f(dm.get("refund_amount"))

    # ── 退货率优先级解析 ──────────────────────────────────────────────────
    # actual_J：dm_store_daily 实际数据（refund_amount / sale_amount）
    actual_J = _f(dm.get("refund_rate"))
    # estimated_J：人工维护参数（当月或最近历史月，已在 get_daily_report 预处理）
    estimated_J = _normalize_return_rate(p.get("estimated_return_rate")) or 0.0
    # 最终退货率：人工维护优先，仅当参数为 0 时才退回实际数据
    J = estimated_J if estimated_J > 0 else actual_J

    return_rate_source = p.get("return_rate_source", "actual_data_fallback")

    if estimated_J > 0 and estimated_J != actual_J:
        logger.debug(
            f"[DailyReport] return_rate override: store={dm.get('store_name')} "
            f"platform={dm.get('platform')} source={return_rate_source} "
            f"value={J:.4f} actual_dm={actual_J:.4f}"
        )
    elif estimated_J == 0 and actual_J == 0:
        logger.debug(
            f"[DailyReport] return_rate missing: store={dm.get('store_name')} "
            f"platform={dm.get('platform')} source=actual_data_fallback value=0"
        )

    income_rate = _f(p["platform_income_rate"]) or 1.0

    K     = I * (1 - J)
    L     = K * income_rate
    P_val = O * J
    Q     = M * _f(p["freight_insurance_unit_cost"])
    R     = N * _f(p["package_unit_cost"])
    S     = M * _f(p["express_unit_cost"])
    U     = N * (1 - J) * _f(p["promotion_unit_cost"])
    V     = J * N * _f(p["return_labor_unit_cost"])
    W     = M * _f(p["goods_loss_unit_cost"])
    E     = Q + R + S + U + V + W + F + C
    D     = L - O + P_val - E
    G     = D / I if I > 0 else 0.0
    H     = D / N if N > 0 else 0.0
    roi   = I / F if F > 0 else 0.0
    ad_cost_per_actual_product = F / actual_product_qty if actual_product_qty > 0 else 0.0

    threshold  = _normalize_return_rate(p.get("return_rate_warning_threshold")) or 0.08
    warning_on = bool(p.get("warning_enabled", True))

    # 状态判断全部使用 J（最终退货率，含人工维护覆盖）
    if J > threshold and warning_on:
        biz_status = "高预估退货率"
    elif D < 0:
        biz_status = "亏损"
    elif G < 0.05:
        biz_status = "微利"
    else:
        biz_status = "正常"

    return {
        "store_id":             dm.get("store_id"),
        "store_name":           dm.get("store_name", ""),
        "platform":             dm.get("platform", ""),
        "biz_date":             str(dm.get("biz_date", "")),
        "sale_amount":          round(I, 2),
        "shipped_qty":          M,
        "order_count":          N,
        "actual_order_count":   actual_order_count,
        "actual_product_qty":   actual_product_qty,
        "refund_amount":        round(refund_amount, 2),
        "refund_count":         round(M * J),           # 估算退货件数 = 发货件数 × 最终退货率
        "refund_rate":          round(J, 6),            # 最终退货率（含人工维护覆盖）
        "refund_rate_actual":   round(actual_J, 6),     # dm 实际退货率（辅助调试）
        "return_rate_source":   return_rate_source,
        "sale_cogs":            round(O, 2),
        "ad_cost":              round(F, 2),
        "compensation_amount":  round(C, 2),
        "refund_only_rate":     _normalize_return_rate(p.get("refund_only_rate")) or 0.0,
        "ad_cost_source":       dm.get("ad_cost_source", "dm_data"),
        "refund_net_amount":    round(K, 2),
        "platform_net_amount":  round(L, 2),
        "refund_cogs_back":     round(P_val, 2),
        "freight_insurance":    round(Q, 2),
        "package_cost":         round(R, 2),
        "express_cost":         round(S, 2),
        "promotion_cost":       round(U, 2),
        "return_labor_cost":    round(V, 2),
        "goods_loss_cost":      round(W, 2),
        "total_expense":        round(E, 2),
        "profit":               round(D, 2),
        "profit_rate":          round(G, 6),
        "profit_per_order":     round(H, 2),
        "ad_cost_per_actual_product": round(ad_cost_per_actual_product, 2),
        "roi":                  round(roi, 4),
        "biz_status":           biz_status,
        "platform_income_rate": round(income_rate, 4),
        "has_params":           len(params) > 0,
    }



async def _load_daily_ad_costs(db: AsyncSession, biz_date: date) -> dict:
    """加载人工维护的每日广告费和赔付，key=store_id(int)"""
    rows = await db.execute(text("""
        SELECT store_id, ad_cost, compensation_amount
        FROM finance_store_daily_ad_costs
        WHERE biz_date = :dt
    """), {"dt": biz_date})
    return {
        int(r.store_id): {
            "ad_cost": float(r.ad_cost or 0),
            "compensation_amount": float(r.compensation_amount or 0),
        }
        for r in rows.fetchall()
    }


async def get_daily_report(
    db: AsyncSession,
    biz_date: date,
    store_id: Optional[int] = None,
) -> dict:
    month = biz_date.strftime("%Y-%m")

    # ── Step 1: 加载当月参数 ──────────────────────────────────────────────
    params_map = await _load_params(db, month)

    # ── Step 2: 为当月 estimated_return_rate=0 的店铺查最近历史月份 ────────
    need_fallback_ids = [
        sid for sid, p in params_map.items()
        if (_normalize_return_rate(p.get("estimated_return_rate")) or 0.0) == 0.0
    ]
    fallback_map = await _load_fallback_return_rates(db, need_fallback_ids, month)

    for sid in need_fallback_ids:
        if sid in fallback_map:
            fb = fallback_map[sid]
            params_map[sid]["estimated_return_rate"] = fb["estimated_return_rate"]
            src = f"manual_latest_month:{fb['source_month']}"
            params_map[sid]["return_rate_source"] = src
            logger.debug(
                f"[DailyReport] return_rate fallback: store_id={sid} "
                f"source={src} value={fb['estimated_return_rate']:.4f}"
            )
        else:
            params_map[sid]["return_rate_source"] = "actual_data_fallback"

    # 当月有 estimated_return_rate > 0 的店铺标记来源
    for sid, p in params_map.items():
        if "return_rate_source" not in p:
            p["return_rate_source"] = "manual_current_month"

    # ── Step 3: 查询 dm_store_daily ─────────────────────────────────────
    where_extra = "AND d.store_id = :sid" if store_id else ""
    params_sql: dict = {"dt": biz_date}
    if store_id:
        params_sql["sid"] = store_id

    rows = await db.execute(text(f"""
        SELECT
            d.store_id,
            s.store_name,
            COALESCE(bp.name, '') AS platform,
            d.biz_date,
            d.sale_amount,
            COALESCE(d.shipped_qty, d.paid_qty, 0) AS shipped_qty,
            d.order_count,
            COALESCE(d.actual_order_count, 0) AS actual_order_count,
            COALESCE(d.actual_product_qty, 0) AS actual_product_qty,
            d.refund_amount,
            d.refund_count,
            d.refund_rate,
            d.sale_cogs,
            d.refund_cogs,
            d.ad_cost
        FROM dm_store_daily d
        JOIN biz_stores s ON s.id = d.store_id
        LEFT JOIN biz_platforms bp ON bp.id = s.platform_id
        WHERE d.biz_date = :dt {where_extra}
        ORDER BY d.sale_amount DESC
    """), params_sql)

    # ── Step 4: 收集 dm 数据，找出 params_map 中没有记录的店铺 ────────────
    dm_list = [dict(row) for row in rows.mappings()]
    dm_store_ids = {int(dm["store_id"]) for dm in dm_list}
    new_store_ids = dm_store_ids - set(params_map.keys())

    if new_store_ids:
        # 没有当月记录的店铺，也尝试历史月份兜底
        extra_fallback = await _load_fallback_return_rates(db, list(new_store_ids), month)
        for sid in new_store_ids:
            if sid in extra_fallback:
                fb = extra_fallback[sid]
                src = f"manual_latest_month:{fb['source_month']}"
                params_map[sid] = {
                    **_DEFAULT_PARAMS,
                    "estimated_return_rate":         fb["estimated_return_rate"],
                    "return_rate_source":            src,
                    "return_rate_warning_threshold": fb.get("return_rate_warning_threshold", 0.08),
                    "warning_enabled":               fb.get("warning_enabled", True),
                }
            else:
                params_map[sid] = {
                    **_DEFAULT_PARAMS,
                    "return_rate_source": "actual_data_fallback",
                }

    # ── Step 4.1: 当月参数行可能只导入了退货率，费用字段为 0 时按最近历史月补齐 ──
    latest_param_values = await _load_latest_param_values(db, list(dm_store_ids), month)
    _apply_missing_param_fallback(params_map, latest_param_values)

    # ── Step 4.5: 加载每日广告费和赔付（广告费优先级高于 dm_store_daily.ad_cost） ─
    daily_ad_costs = await _load_daily_ad_costs(db, biz_date)
    platform_defaults = await _load_platform_default_values(db, month)

    # ── Step 5: 计算每行日报 ─────────────────────────────────────────────
    from app.core.platform_resolver import resolve_store_platform
    store_rows = []
    for dm in dm_list:
        plat = resolve_store_platform(dm["store_name"], dm["platform"]).label
        dm["platform"] = plat
        # 人工维护广告费覆盖 dm_store_daily.ad_cost
        sid_key = int(dm["store_id"])
        dm["compensation_amount"] = 0.0
        if sid_key in daily_ad_costs:
            dm["ad_cost"]        = daily_ad_costs[sid_key]["ad_cost"]
            dm["compensation_amount"] = daily_ad_costs[sid_key]["compensation_amount"]
            dm["ad_cost_source"] = "manual_daily"
        else:
            dm["ad_cost_source"] = "dm_data" if _f(dm.get("ad_cost")) > 0 else "none"
        p = params_map.get(
            int(dm["store_id"]),
            {**_DEFAULT_PARAMS, "return_rate_source": "actual_data_fallback"},
        )
        p = _apply_platform_defaults(p, platform_defaults.get(plat))
        store_rows.append(_compute_store_row(dm, p))

    # ── Step 6: 汇总行 ────────────────────────────────────────────────────
    if store_rows:
        def _sum(key):
            return round(sum(r[key] for r in store_rows), 2)

        total_sale         = _sum("sale_amount")
        total_profit       = _sum("profit")
        total_shipped      = sum(r["shipped_qty"]  for r in store_rows)
        total_actual_orders = sum(r["actual_order_count"] for r in store_rows)
        total_actual_qty    = sum(r["actual_product_qty"] for r in store_rows)
        total_refund_count = sum(r["refund_count"] for r in store_rows)
        total_ad           = _sum("ad_cost")
        total_compensation = _sum("compensation_amount")
        total_refund_only_weight = sum(
            float(r.get("refund_only_rate") or 0) * int(r.get("shipped_qty") or 0)
            for r in store_rows
        )
        total_sale_cogs    = _sum("sale_cogs")
        summary = {
            "sale_amount":   total_sale,
            "shipped_qty":   total_shipped,
            "order_count":   sum(r["order_count"] for r in store_rows),
            "actual_order_count": total_actual_orders,
            "actual_product_qty": total_actual_qty,
            "refund_amount": _sum("refund_amount"),
            "refund_count":  total_refund_count,
            "refund_rate":   round(
                total_refund_count / total_shipped if total_shipped > 0 else 0, 6
            ),
            "ad_cost":       total_ad,
            "compensation_amount": total_compensation,
            "refund_only_rate": round(
                total_refund_only_weight / total_shipped if total_shipped > 0 else 0, 6
            ),
            "total_expense": _sum("total_expense"),
            "profit":        total_profit,
            "profit_rate":   round(total_profit / total_sale if total_sale > 0 else 0, 6),
            "ad_cost_per_actual_product": round(total_ad / total_actual_qty if total_actual_qty > 0 else 0, 2),
            "roi":           round(total_sale / total_ad if total_ad > 0 else 0, 4),
            "sale_cogs":     total_sale_cogs,
            "refund_net_amount":    _sum("refund_net_amount"),
            "platform_net_amount":  _sum("platform_net_amount"),
            "refund_cogs_back":     _sum("refund_cogs_back"),
            "freight_insurance":    _sum("freight_insurance"),
            "package_cost":         _sum("package_cost"),
            "express_cost":         _sum("express_cost"),
            "promotion_cost":       _sum("promotion_cost"),
            "return_labor_cost":    _sum("return_labor_cost"),
            "goods_loss_cost":      _sum("goods_loss_cost"),
            "store_count":   len(store_rows),
        }
    else:
        summary = {}

    # ── ai_summary: 基于日报数据生成诊断摘要，与首页 API 卡片口径一致 ────────
    _platform_today: dict[str, float] = {}
    for _r in store_rows:
        _p = _r["platform"]
        _platform_today[_p] = _platform_today.get(_p, 0.0) + float(_r["sale_amount"])
    try:
        from datetime import timedelta as _td
        _avg7_r = await db.execute(text(
            "SELECT COALESCE(AVG(total_sale_amount), 0) AS avg_sale "
            "FROM dm_company_daily "
            "WHERE biz_date BETWEEN :s AND :e"
        ), {"s": biz_date - _td(days=7), "e": biz_date - _td(days=1)})
        _avg7 = float(_avg7_r.fetchone().avg_sale)
    except Exception:
        _avg7 = 0.0
    try:
        _fixed_r = await db.execute(text(
            "SELECT value FROM sys_settings WHERE key = 'monthly_fixed_cost'"
        ))
        _fixed = _fixed_r.fetchone()
        _daily_fixed = round(float(_fixed.value) / 30, 2) if _fixed else 0.0
    except Exception:
        _daily_fixed = 0.0
    _s = summary or {}
    ai_summary = _build_summary_text(
        sale=float(_s.get("sale_amount", 0)),
        refund=float(_s.get("refund_amount", 0)),
        cogs=float(_s.get("sale_cogs", 0)),
        net=float(_s.get("profit", 0)),
        daily_fixed=_daily_fixed,
        platform_today=_platform_today,
        avg7=_avg7,
    )

    # ── 嵌套店铺组：生成统一有序行(成员店行+组合计行)，页面与导出 Excel 共用 ──
    from app.services.finance.store_report_group_util import load_group_tree, build_report_rows
    if store_id is None:
        tree = await load_group_tree(db)
        report_rows, group_subtotals = build_report_rows(store_rows, tree)
    else:
        report_rows = [{**r, "row_kind": "store", "level": 0, "group_id": None, "group_name": None}
                       for r in store_rows]
        group_subtotals = []

    return {
        "biz_date":    str(biz_date),
        "stores":      store_rows,        # 扁平原始行(向后兼容: 推送/旧消费方)
        "report_rows": report_rows,       # 有序展示行(含组合计行+层级) -> 页面与 Excel 用
        "summary":     summary,
        "groups":      group_subtotals,
        "ai_summary":  ai_summary,
    }
