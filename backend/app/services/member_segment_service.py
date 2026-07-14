"""Persisted VIP segmentation, risk rules and wake-up candidates."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.store_whitelist import ALLOWED_INVENTORY_CODES


DEFAULT_MEMBER_SEGMENT_RULES: dict[str, Any] = {
    "rule_version": "2026.07.1",
    "high_value_amount": 10000.0,
    "high_balance_amount": 5000.0,
    "high_repurchase_count": 10,
    "high_avg_order_value": 800.0,
    "high_gross_margin": 0.65,
    "gross_margin_min_coverage": 0.95,
    "sleeping_days": 90,
    "churn_risk_days": 180,
    "frequency_period_days": 90,
    "frequency_decline_ratio": 0.5,
    "frequency_baseline_min_orders": 3,
    "excessive_discount_rate": 0.6,
    "discount_min_orders": 3,
    "return_rate_threshold": 0.2,
    "return_min_orders": 2,
    "return_sales_min_orders": 3,
    "recharge_no_second_consume_days": 30,
    "recharge_risk_lookback_days": 180,
}

RULE_BOUNDS: dict[str, tuple[float, float]] = {
    "high_value_amount": (0.01, 100_000_000),
    "high_balance_amount": (0.01, 100_000_000),
    "high_repurchase_count": (1, 100_000),
    "high_avg_order_value": (0.01, 1_000_000),
    "high_gross_margin": (0.0001, 1),
    "gross_margin_min_coverage": (0.0001, 1),
    "sleeping_days": (1, 3650),
    "churn_risk_days": (1, 3650),
    "frequency_period_days": (1, 365),
    "frequency_decline_ratio": (0.0001, 1),
    "frequency_baseline_min_orders": (1, 100_000),
    "excessive_discount_rate": (0.0001, 1),
    "discount_min_orders": (1, 100_000),
    "return_rate_threshold": (0.0001, 10),
    "return_min_orders": (1, 100_000),
    "return_sales_min_orders": (1, 100_000),
    "recharge_no_second_consume_days": (1, 3650),
    "recharge_risk_lookback_days": (1, 3650),
}

LABEL_NAMES = {
    "HIGH_VALUE": "高价值",
    "HIGH_BALANCE": "高余额",
    "HIGH_REPURCHASE": "高复购",
    "HIGH_AOV": "高客单",
    "HIGH_MARGIN": "高毛利",
    "DORMANT": "沉睡",
    "CHURN_RISK": "流失风险",
    "WAKEUP_CANDIDATE": "可唤醒",
}

RISK_META = {
    "HIGH_BALANCE_DORMANT": ("大额余额长期未消费", "critical"),
    "HIGH_VALUE_INACTIVE": ("高价值VIP长期未到店", "risk"),
    "FREQUENCY_DECLINE": ("消费频率下降", "warning"),
    "RECHARGE_NO_SECOND_CONSUME": ("充值后未二次消费", "risk"),
    "EXCESSIVE_DISCOUNT": ("折扣过高", "warning"),
    "NEGATIVE_BALANCE": ("会员余额异常", "critical"),
    "RETURN_ANOMALY": ("退货异常", "risk"),
}


def _num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def merge_member_segment_rules(overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Merge recognized configuration keys with guarded defaults."""
    merged = dict(DEFAULT_MEMBER_SEGMENT_RULES)
    if not isinstance(overrides, dict):
        return merged
    for key, value in overrides.items():
        if key not in merged or value is None:
            continue
        if key == "rule_version":
            merged[key] = str(value)[:32]
            continue
        if isinstance(value, bool):
            continue
        try:
            parsed = float(value) if isinstance(merged[key], float) else int(value)
        except (TypeError, ValueError):
            continue
        minimum, maximum = RULE_BOUNDS[key]
        if minimum <= parsed <= maximum:
            merged[key] = parsed
    if merged["churn_risk_days"] < merged["sleeping_days"]:
        merged["churn_risk_days"] = merged["sleeping_days"]
    if merged["recharge_risk_lookback_days"] < merged["recharge_no_second_consume_days"]:
        merged["recharge_risk_lookback_days"] = merged["recharge_no_second_consume_days"]
    return merged


def resolve_member_segment_rebuild_date(
    requested: date | None,
    *,
    now: datetime | None = None,
) -> date:
    """Snapshots can only be rebuilt from current master data for Beijing today."""
    instant = now or datetime.now(timezone.utc)
    business_date = instant.astimezone(ZoneInfo("Asia/Shanghai")).date()
    if requested is not None and requested != business_date:
        raise ValueError("会员分层仅支持重算北京时间当天；历史日期只读取已保存快照")
    return business_date


def normalize_member_segment_store_codes(
    store_codes: Iterable[str] | None,
) -> list[str]:
    source_codes = ALLOWED_INVENTORY_CODES if store_codes is None else store_codes
    return sorted({
        str(code).upper()
        for code in source_codes
        if str(code).strip()
    })


def snapshot_key(calc_date: date, member_no: str) -> str:
    return f"{calc_date.isoformat()}:{member_no}"


def _entry(
    code: str,
    calc_date: date,
    rule_version: str,
    evidence: dict[str, Any],
    *,
    risk: bool = False,
) -> dict[str, Any]:
    if risk:
        name, severity = RISK_META[code]
        return {
            "code": code,
            "name": name,
            "severity": severity,
            "calc_date": calc_date.isoformat(),
            "rule_version": rule_version,
            "evidence": evidence,
        }
    return {
        "code": code,
        "name": LABEL_NAMES[code],
        "calc_date": calc_date.isoformat(),
        "rule_version": rule_version,
        "evidence": evidence,
    }


def _rfm_score(recency_days: int, frequency: int, monetary: float) -> float:
    recency = 5 if recency_days <= 30 else 4 if recency_days <= 60 else 3 if recency_days <= 90 else 2 if recency_days <= 180 else 1
    freq = 5 if frequency >= 20 else 4 if frequency >= 10 else 3 if frequency >= 5 else 2 if frequency >= 2 else 1
    money = 5 if monetary >= 20000 else 4 if monetary >= 10000 else 3 if monetary >= 5000 else 2 if monetary >= 1000 else 1
    return round((recency + freq + money) / 3, 2)


def build_member_segment_result(
    metrics: dict[str, Any],
    calc_date: date,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply deterministic, evidence-bearing member rules to one member."""
    cfg = merge_member_segment_rules(rules)
    version = str(cfg["rule_version"])
    balance = _num(metrics.get("current_balance"))
    total_amount = _num(metrics.get("total_amount"))
    total_count = _int(metrics.get("total_count"))
    recency_days = max(_int(metrics.get("recency_days"), 9999), 0)
    avg_order_value = _num(metrics.get("avg_order_value"))
    labels: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    quality: dict[str, dict[str, Any]] = {}

    def label(code: str, evidence: dict[str, Any]) -> None:
        labels.append(_entry(code, calc_date, version, evidence))

    def risk(code: str, evidence: dict[str, Any]) -> None:
        risks.append(_entry(code, calc_date, version, evidence, risk=True))

    if total_amount >= cfg["high_value_amount"]:
        label("HIGH_VALUE", {"total_amount": round(total_amount, 2), "threshold": cfg["high_value_amount"]})
    if balance >= cfg["high_balance_amount"]:
        label("HIGH_BALANCE", {"current_balance": round(balance, 2), "threshold": cfg["high_balance_amount"], "source": "baison.CZ_DQJE"})
    if total_count >= cfg["high_repurchase_count"]:
        label("HIGH_REPURCHASE", {"total_count": total_count, "threshold": cfg["high_repurchase_count"]})
    if avg_order_value >= cfg["high_avg_order_value"]:
        label("HIGH_AOV", {"avg_order_value": round(avg_order_value, 2), "threshold": cfg["high_avg_order_value"]})

    gross_margin = metrics.get("gross_margin")
    cost_coverage = _num(metrics.get("cost_coverage"))
    if gross_margin is None or cost_coverage < cfg["gross_margin_min_coverage"]:
        quality["gross_margin"] = {
            "status": "pending_data",
            "coverage": round(cost_coverage, 4),
            "required_coverage": cfg["gross_margin_min_coverage"],
            "reason": "会员商品成本覆盖不足，不参与高毛利标签",
        }
    else:
        quality["gross_margin"] = {"status": "ready", "coverage": round(cost_coverage, 4)}
        if _num(gross_margin) >= cfg["high_gross_margin"]:
            label("HIGH_MARGIN", {"gross_margin": round(_num(gross_margin), 4), "cost_coverage": round(cost_coverage, 4), "threshold": cfg["high_gross_margin"]})

    if recency_days >= cfg["sleeping_days"]:
        label("DORMANT", {"recency_days": recency_days, "threshold": cfg["sleeping_days"]})
    if recency_days >= cfg["churn_risk_days"]:
        label("CHURN_RISK", {"recency_days": recency_days, "threshold": cfg["churn_risk_days"]})

    if balance >= cfg["high_balance_amount"] and recency_days >= cfg["sleeping_days"]:
        risk("HIGH_BALANCE_DORMANT", {"current_balance": round(balance, 2), "recency_days": recency_days})
    if total_amount >= cfg["high_value_amount"] and recency_days >= cfg["sleeping_days"]:
        risk("HIGH_VALUE_INACTIVE", {"total_amount": round(total_amount, 2), "recency_days": recency_days})

    required_history = int(cfg["frequency_period_days"]) * 2
    ticket_history_days = _int(metrics.get("ticket_history_days"))
    previous_orders = _int(metrics.get("previous_period_orders"))
    current_orders = _int(metrics.get("current_period_orders"))
    if ticket_history_days < required_history:
        quality["frequency_trend"] = {
            "status": "pending_data",
            "history_days": ticket_history_days,
            "required_days": required_history,
            "reason": "POS历史不足两个完整对比周期",
        }
    else:
        quality["frequency_trend"] = {"status": "ready", "history_days": ticket_history_days}
        if previous_orders >= cfg["frequency_baseline_min_orders"] and current_orders / previous_orders <= cfg["frequency_decline_ratio"]:
            risk("FREQUENCY_DECLINE", {"current_orders": current_orders, "previous_orders": previous_orders, "ratio": round(current_orders / previous_orders, 4), "threshold": cfg["frequency_decline_ratio"]})

    days_since_recharge = metrics.get("days_since_recharge")
    if (
        days_since_recharge is not None
        and cfg["recharge_no_second_consume_days"] <= _int(days_since_recharge) <= cfg["recharge_risk_lookback_days"]
        and _int(metrics.get("post_recharge_order_count")) < 2
    ):
        risk("RECHARGE_NO_SECOND_CONSUME", {"latest_recharge_date": metrics.get("latest_recharge_date"), "days_since_recharge": _int(days_since_recharge), "post_recharge_order_count": _int(metrics.get("post_recharge_order_count"))})

    discount_rate = metrics.get("avg_discount_rate")
    discount_orders = _int(metrics.get("discount_order_count"))
    if discount_rate is not None and discount_orders >= cfg["discount_min_orders"] and 0 < _num(discount_rate) <= cfg["excessive_discount_rate"]:
        risk("EXCESSIVE_DISCOUNT", {"avg_discount_rate": round(_num(discount_rate), 4), "order_count": discount_orders, "threshold": cfg["excessive_discount_rate"]})

    if balance < 0:
        risk("NEGATIVE_BALANCE", {"current_balance": round(balance, 2), "source": "baison.CZ_DQJE"})

    return_rate = metrics.get("return_rate")
    return_orders = _int(metrics.get("return_orders"))
    sales_orders = _int(metrics.get("sales_order_count"))
    if sales_orders >= cfg["return_sales_min_orders"] and (
        return_orders >= cfg["return_min_orders"]
        or (return_rate is not None and _num(return_rate) >= cfg["return_rate_threshold"])
    ):
        risk("RETURN_ANOMALY", {"return_rate": round(_num(return_rate), 4), "return_orders": return_orders, "sales_order_count": sales_orders})

    wakeup_codes = {"HIGH_BALANCE_DORMANT", "HIGH_VALUE_INACTIVE", "FREQUENCY_DECLINE", "RECHARGE_NO_SECOND_CONSUME"}
    is_wakeup = bool(wakeup_codes & {item["code"] for item in risks})
    if is_wakeup:
        label("WAKEUP_CANDIDATE", {"risk_codes": sorted(wakeup_codes & {item["code"] for item in risks})})

    risk_codes = {item["code"] for item in risks}
    priority = 1 if risk_codes & {"NEGATIVE_BALANCE", "HIGH_BALANCE_DORMANT"} else 2 if is_wakeup else 3
    result_metrics = dict(metrics)
    result_metrics["rfm_score"] = _rfm_score(recency_days, total_count, total_amount)
    return {
        "snapshot_key": snapshot_key(calc_date, str(metrics.get("member_no") or "")),
        "calc_date": calc_date.isoformat(),
        "member_no": str(metrics.get("member_no") or ""),
        "store_code": str(metrics.get("store_code") or "").upper(),
        "labels": labels,
        "risks": risks,
        "metrics": result_metrics,
        "data_quality": quality,
        "is_wakeup_candidate": is_wakeup,
        "wakeup_priority": priority,
        "wakeup_reasons": [item for item in risks if item["code"] in wakeup_codes],
        "preferences": list(metrics.get("preferences") or []),
        "suggested_products": list(metrics.get("suggested_products") or []),
        "responsibility_status": "unconfirmed",
        "responsible_employee_no": None,
        "candidate_guide_ids": sorted(set(metrics.get("candidate_guide_ids") or [])),
        "rule_version": version,
    }


async def load_member_segment_rules(db: AsyncSession) -> dict[str, Any]:
    raw = (await db.execute(text("SELECT param_value FROM sys.sys_param WHERE param_key='member_segment_rules'"))).scalar()
    if not raw:
        return dict(DEFAULT_MEMBER_SEGMENT_RULES)
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return dict(DEFAULT_MEMBER_SEGMENT_RULES)
    return merge_member_segment_rules(parsed)


async def _member_metrics(db: AsyncSession, calc_date: date, store_codes: list[str]) -> list[dict[str, Any]]:
    """Load only evidence that has a reliable local source."""
    period_days = int((await load_member_segment_rules(db))["frequency_period_days"])
    rows = (await db.execute(text("""
        WITH ticket_base AS (
            SELECT t.biz_date, t.ticket_no, UPPER(t.store_code) store_code,
                   NULLIF(BTRIM(COALESCE(NULLIF(t.vip_code::text,''), NULLIF(t.customer_code::text,''), '')), '') member_no,
                   COALESCE(t.sales_amount,0) sales_amount,
                   COALESCE(t.standard_amount,0) standard_amount,
                   COALESCE(t.discount_rate,0) discount_rate,
                   t.raw_data, t.synced_at
            FROM dwd.dwd_pos_ticket t
            WHERE t.biz_date <= :calc_date
              AND UPPER(t.store_code)=ANY(:store_codes)
              AND COALESCE(t.is_void,false)=false
              AND COALESCE(t.is_pending,false)=false
        ), ticket_stats AS (
            SELECT member_no,
                   MIN(biz_date) first_ticket_date,
                   MAX(synced_at) source_updated_at,
                   COUNT(*) FILTER (WHERE sales_amount>0 AND biz_date>CAST(:calc_date AS date)-CAST(:period_days AS integer)) sales_order_count,
                   COUNT(*) FILTER (WHERE sales_amount>0 AND biz_date>CAST(:calc_date AS date)-CAST(:period_days AS integer)) current_period_orders,
                   COUNT(*) FILTER (WHERE sales_amount>0 AND biz_date>CAST(:calc_date AS date)-(CAST(:period_days AS integer)*2) AND biz_date<=CAST(:calc_date AS date)-CAST(:period_days AS integer)) previous_period_orders,
                   AVG(discount_rate) FILTER (WHERE sales_amount>0 AND standard_amount>0 AND biz_date>CAST(:calc_date AS date)-CAST(:period_days AS integer)) avg_discount_rate,
                   COUNT(*) FILTER (WHERE sales_amount>0 AND standard_amount>0 AND biz_date>CAST(:calc_date AS date)-CAST(:period_days AS integer)) discount_order_count,
                   COUNT(*) FILTER (WHERE sales_amount<0 AND biz_date>CAST(:calc_date AS date)-CAST(:period_days AS integer)) return_orders,
                   COALESCE(SUM(ABS(sales_amount)) FILTER (WHERE sales_amount<0 AND biz_date>CAST(:calc_date AS date)-CAST(:period_days AS integer)),0) return_amount,
                   COALESCE(SUM(sales_amount) FILTER (WHERE sales_amount>0 AND biz_date>CAST(:calc_date AS date)-CAST(:period_days AS integer)),0) period_sales
            FROM ticket_base WHERE member_no IS NOT NULL GROUP BY member_no
        ), recharge AS (
            SELECT member_no, MAX(biz_date) latest_recharge_date, MAX(synced_at) source_updated_at
            FROM dwd.dwd_baison_member_deposit_log
            WHERE biz_date<=:calc_date AND UPPER(store_code)=ANY(:store_codes)
              AND (business_type='recharge' OR change_type='0')
            GROUP BY member_no
        ), post_recharge AS (
            SELECT r.member_no,
                   COUNT(l.id) FILTER (WHERE l.business_type='consume' OR l.change_type='2') post_recharge_order_count
            FROM recharge r
            LEFT JOIN dwd.dwd_baison_member_deposit_log l
              ON l.member_no=r.member_no
             AND l.biz_date BETWEEN r.latest_recharge_date AND :calc_date
             AND UPPER(l.store_code)=ANY(:store_codes)
            GROUP BY r.member_no
        )
        SELECT m.member_no,
               UPPER(m.register_store) store_code,
               COALESCE(m.current_balance,0) current_balance,
               COALESCE(m.total_amount,0) total_amount,
               COALESCE(m.total_count,0) total_count,
               m.last_consume_date,
               GREATEST(CAST(:calc_date AS date)-COALESCE(m.last_consume_date,m.register_date,CAST(:calc_date AS date)-9999),0) recency_days,
               CASE WHEN COALESCE(m.total_count,0)>0 THEN COALESCE(m.total_amount,0)/m.total_count ELSE 0 END avg_order_value,
               COALESCE(ts.current_period_orders,0) current_period_orders,
               COALESCE(ts.previous_period_orders,0) previous_period_orders,
               CASE WHEN ts.first_ticket_date IS NULL THEN 0 ELSE CAST(:calc_date AS date)-ts.first_ticket_date+1 END ticket_history_days,
               ts.avg_discount_rate, COALESCE(ts.discount_order_count,0) discount_order_count,
               CASE WHEN COALESCE(ts.period_sales,0)>0 THEN COALESCE(ts.return_amount,0)/ts.period_sales ELSE NULL END return_rate,
               COALESCE(ts.return_orders,0) return_orders,
               COALESCE(ts.sales_order_count,0) sales_order_count,
               r.latest_recharge_date,
               CASE WHEN r.latest_recharge_date IS NULL THEN NULL ELSE CAST(:calc_date AS date)-r.latest_recharge_date END days_since_recharge,
               COALESCE(pr.post_recharge_order_count,0) post_recharge_order_count,
               NULL::numeric gross_margin, 0::numeric cost_coverage,
               GREATEST(COALESCE(m.updated_at,'epoch'),COALESCE(ts.source_updated_at,'epoch'),COALESCE(r.source_updated_at,'epoch')) source_updated_at
        FROM dim.dim_member m
        LEFT JOIN ticket_stats ts ON ts.member_no=m.member_no
        LEFT JOIN recharge r ON r.member_no=m.member_no
        LEFT JOIN post_recharge pr ON pr.member_no=m.member_no
        WHERE UPPER(m.register_store)=ANY(:store_codes)
          AND COALESCE(m.status,'active')='active'
        ORDER BY m.member_no
    """), {"calc_date": calc_date, "store_codes": store_codes, "period_days": period_days})).mappings().all()
    return [dict(row) for row in rows]


async def _member_preferences(db: AsyncSession, calc_date: date, store_codes: list[str]) -> dict[str, dict[str, Any]]:
    rows = (await db.execute(text("""
        WITH lines AS (
            SELECT NULLIF(BTRIM(COALESCE(NULLIF(t.vip_code::text,''),NULLIF(t.customer_code::text,''),'')),'') member_no,
                   UPPER(t.store_code) store_code,
                   NULLIF(d.item->>'spdm','') product_code,
                   NULLIF(d.item->>'spmc','') product_name,
                   CASE
                     WHEN COALESCE(d.item->>'je','') ~ '^-?[0-9]+([.][0-9]+)?$'
                     THEN (d.item->>'je')::numeric
                     ELSE 0::numeric
                   END sales_amount,
                   NULLIF(BTRIM(t.raw_data->>'dgy_list_dm'),'') guide_ids
            FROM dwd.dwd_pos_ticket t
            CROSS JOIN LATERAL jsonb_array_elements(COALESCE(t.raw_data->'orderDetailGets','[]'::jsonb)) d(item)
            WHERE t.biz_date BETWEEN CAST(:calc_date AS date)-180 AND CAST(:calc_date AS date)
              AND UPPER(t.store_code)=ANY(:store_codes)
              AND COALESCE(t.is_void,false)=false AND COALESCE(t.is_pending,false)=false
        ), ranked AS (
            SELECT member_no, product_code, MAX(product_name) product_name, SUM(sales_amount) sales_amount,
                   ROW_NUMBER() OVER (PARTITION BY member_no ORDER BY SUM(sales_amount) DESC,product_code) rn
            FROM lines WHERE member_no IS NOT NULL AND product_code IS NOT NULL AND sales_amount>0
            GROUP BY member_no,product_code
        ), products AS (
            SELECT member_no, jsonb_agg(jsonb_build_object('product_code',product_code,'product_name',product_name,'sales_amount',sales_amount) ORDER BY rn) products
            FROM ranked WHERE rn<=3 GROUP BY member_no
        ), guides AS (
            SELECT member_no, array_agg(DISTINCT guide_id ORDER BY guide_id) guide_ids
            FROM lines CROSS JOIN LATERAL unnest(string_to_array(lines.guide_ids,',')) AS u(guide_id)
            WHERE member_no IS NOT NULL AND BTRIM(guide_id)<>'' GROUP BY member_no
        )
        SELECT COALESCE(p.member_no,g.member_no) member_no,COALESCE(p.products,'[]'::jsonb) products,COALESCE(g.guide_ids,ARRAY[]::text[]) guide_ids
        FROM products p FULL JOIN guides g ON g.member_no=p.member_no
    """), {"calc_date": calc_date, "store_codes": store_codes})).mappings().all()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        products = list(row["products"] or [])
        result[str(row["member_no"])] = {
            "preferences": [{"name": item.get("product_name"), "product_code": item.get("product_code")} for item in products[:3]],
            "suggested_products": products[:3],
            "candidate_guide_ids": [str(value).strip() for value in (row["guide_ids"] or []) if str(value).strip()],
        }
    return result


async def rebuild_member_segments(
    db: AsyncSession,
    calc_date: date | None = None,
    store_codes: Iterable[str] | None = None,
) -> dict[str, Any]:
    target_date = resolve_member_segment_rebuild_date(calc_date)
    codes = normalize_member_segment_store_codes(store_codes)
    locked = (await db.execute(text("SELECT pg_try_advisory_xact_lock(hashtext('member_segment_rebuild'), :lock_date)"), {"lock_date": int(target_date.strftime("%Y%m%d"))})).scalar()
    if not locked:
        return {"ok": True, "skipped": True, "reason": "locked", "calc_date": target_date.isoformat()}
    rules = await load_member_segment_rules(db)
    metrics_rows = await _member_metrics(db, target_date, codes)
    prefs = await _member_preferences(db, target_date, codes)
    now = datetime.now(timezone.utc)
    payloads: list[dict[str, Any]] = []
    for metrics in metrics_rows:
        metrics.update(prefs.get(str(metrics["member_no"]), {}))
        result = build_member_segment_result(metrics, target_date, rules)
        payloads.append({
            "calc_date": target_date,
            "member_no": result["member_no"],
            "store_code": result["store_code"],
            "labels": json.dumps(result["labels"], ensure_ascii=False, default=str),
            "risks": json.dumps(result["risks"], ensure_ascii=False, default=str),
            "metrics": json.dumps(result["metrics"], ensure_ascii=False, default=str),
            "data_quality": json.dumps(result["data_quality"], ensure_ascii=False, default=str),
            "is_wakeup_candidate": result["is_wakeup_candidate"],
            "wakeup_priority": result["wakeup_priority"],
            "wakeup_reasons": json.dumps(result["wakeup_reasons"], ensure_ascii=False, default=str),
            "preferences": json.dumps(result["preferences"], ensure_ascii=False, default=str),
            "suggested_products": json.dumps(result["suggested_products"], ensure_ascii=False, default=str),
            "responsibility_status": result["responsibility_status"],
            "responsible_employee_no": None,
            "candidate_guide_ids": json.dumps(result["candidate_guide_ids"], ensure_ascii=False),
            "rule_version": result["rule_version"],
            "source_updated_at": metrics.get("source_updated_at"),
            "generated_at": now,
        })
    upsert = text("""
        INSERT INTO dm.dm_member_segment_snapshot (
            calc_date,member_no,store_code,labels,risks,metrics,data_quality,
            is_wakeup_candidate,wakeup_priority,wakeup_reasons,preferences,suggested_products,
            responsibility_status,responsible_employee_no,candidate_guide_ids,rule_version,
            source_updated_at,generated_at
        ) VALUES (
            :calc_date,:member_no,:store_code,CAST(:labels AS jsonb),CAST(:risks AS jsonb),
            CAST(:metrics AS jsonb),CAST(:data_quality AS jsonb),:is_wakeup_candidate,
            :wakeup_priority,CAST(:wakeup_reasons AS jsonb),CAST(:preferences AS jsonb),
            CAST(:suggested_products AS jsonb),:responsibility_status,:responsible_employee_no,
            CAST(:candidate_guide_ids AS jsonb),:rule_version,:source_updated_at,:generated_at
        ) ON CONFLICT (calc_date,member_no) DO UPDATE SET
            store_code=EXCLUDED.store_code,labels=EXCLUDED.labels,risks=EXCLUDED.risks,
            metrics=EXCLUDED.metrics,data_quality=EXCLUDED.data_quality,
            is_wakeup_candidate=EXCLUDED.is_wakeup_candidate,wakeup_priority=EXCLUDED.wakeup_priority,
            wakeup_reasons=EXCLUDED.wakeup_reasons,preferences=EXCLUDED.preferences,
            suggested_products=EXCLUDED.suggested_products,
            responsibility_status=dm.dm_member_segment_snapshot.responsibility_status,
            responsible_employee_no=dm.dm_member_segment_snapshot.responsible_employee_no,
            candidate_guide_ids=EXCLUDED.candidate_guide_ids,rule_version=EXCLUDED.rule_version,
            source_updated_at=EXCLUDED.source_updated_at,generated_at=EXCLUDED.generated_at
    """)
    for offset in range(0, len(payloads), 500):
        await db.execute(upsert, payloads[offset:offset + 500])
    if payloads:
        await db.execute(text("""
            DELETE FROM dm.dm_member_segment_snapshot
            WHERE calc_date=:calc_date AND store_code=ANY(:store_codes)
              AND member_no<>ALL(:member_nos)
        """), {"calc_date": target_date, "store_codes": codes, "member_nos": [row["member_no"] for row in payloads]})
    else:
        await db.execute(text("DELETE FROM dm.dm_member_segment_snapshot WHERE calc_date=:calc_date AND store_code=ANY(:store_codes)"), {"calc_date": target_date, "store_codes": codes})
    await db.flush()
    return {
        "ok": True,
        "calc_date": target_date.isoformat(),
        "member_count": len(payloads),
        "labelled_count": sum(bool(json.loads(row["labels"])) for row in payloads),
        "risk_count": sum(bool(json.loads(row["risks"])) for row in payloads),
        "wakeup_count": sum(bool(row["is_wakeup_candidate"]) for row in payloads),
        "rule_version": rules["rule_version"],
    }


async def latest_member_segment_date(
    db: AsyncSession,
    store_codes: Iterable[str],
) -> date | None:
    codes = sorted({str(code).upper() for code in store_codes})
    return (await db.execute(text("""
        SELECT MAX(calc_date) FROM dm.dm_member_segment_snapshot
        WHERE store_code=ANY(:store_codes)
    """), {"store_codes": codes})).scalar()


async def get_member_segment_overview(
    db: AsyncSession,
    store_codes: Iterable[str],
    calc_date: date | None = None,
) -> dict[str, Any]:
    codes = sorted({str(code).upper() for code in store_codes})
    target_date = calc_date or await latest_member_segment_date(db, codes)
    if not target_date:
        return {"calc_date": None, "summary": {}, "labels": {}, "risks": {}, "status": "pending_data"}
    row = (await db.execute(text("""
        SELECT COUNT(*) total_members,
               COUNT(*) FILTER (WHERE jsonb_array_length(labels)>0) labelled_members,
               COUNT(*) FILTER (WHERE jsonb_array_length(risks)>0) risk_members,
               COUNT(*) FILTER (WHERE is_wakeup_candidate) wakeup_members,
               COUNT(*) FILTER (WHERE labels @> '[{"code":"HIGH_VALUE"}]') high_value,
               COUNT(*) FILTER (WHERE labels @> '[{"code":"HIGH_BALANCE"}]') high_balance,
               COUNT(*) FILTER (WHERE labels @> '[{"code":"HIGH_REPURCHASE"}]') high_repurchase,
               COUNT(*) FILTER (WHERE labels @> '[{"code":"HIGH_AOV"}]') high_aov,
               COUNT(*) FILTER (WHERE labels @> '[{"code":"HIGH_MARGIN"}]') high_margin,
               COUNT(*) FILTER (WHERE labels @> '[{"code":"DORMANT"}]') dormant,
               COUNT(*) FILTER (WHERE labels @> '[{"code":"CHURN_RISK"}]') churn_risk,
               COUNT(*) FILTER (WHERE risks @> '[{"code":"NEGATIVE_BALANCE"}]') negative_balance,
               COUNT(*) FILTER (WHERE risks @> '[{"code":"HIGH_BALANCE_DORMANT"}]') high_balance_dormant,
               COUNT(*) FILTER (WHERE risks @> '[{"code":"HIGH_VALUE_INACTIVE"}]') high_value_inactive,
               COUNT(*) FILTER (WHERE risks @> '[{"code":"FREQUENCY_DECLINE"}]') frequency_decline,
               COUNT(*) FILTER (WHERE risks @> '[{"code":"RECHARGE_NO_SECOND_CONSUME"}]') recharge_no_second_consume,
               COUNT(*) FILTER (WHERE risks @> '[{"code":"EXCESSIVE_DISCOUNT"}]') excessive_discount,
               COUNT(*) FILTER (WHERE risks @> '[{"code":"RETURN_ANOMALY"}]') return_anomaly,
               COUNT(*) FILTER (WHERE data_quality->'frequency_trend'->>'status'='pending_data') frequency_pending,
               COUNT(*) FILTER (WHERE data_quality->'gross_margin'->>'status'='pending_data') gross_margin_pending,
               MAX(source_updated_at) source_updated_at,MAX(generated_at) generated_at,
               MAX(rule_version) rule_version
        FROM dm.dm_member_segment_snapshot
        WHERE calc_date=:calc_date AND store_code=ANY(:store_codes)
    """), {"calc_date": target_date, "store_codes": codes})).mappings().one()
    data = dict(row)
    if _int(data.get("total_members")) == 0:
        return {
            "calc_date": target_date.isoformat(),
            "summary": {},
            "labels": {},
            "risks": {},
            "status": "pending_data",
            "reason": "该日期没有会员分层快照",
        }
    summary_keys = ("total_members", "labelled_members", "risk_members", "wakeup_members", "frequency_pending", "gross_margin_pending")
    label_keys = ("high_value", "high_balance", "high_repurchase", "high_aov", "high_margin", "dormant", "churn_risk")
    risk_keys = ("negative_balance", "high_balance_dormant", "high_value_inactive", "frequency_decline", "recharge_no_second_consume", "excessive_discount", "return_anomaly")
    return {
        "calc_date": target_date.isoformat(),
        "summary": {key: _int(data.get(key)) for key in summary_keys},
        "labels": {key: _int(data.get(key)) for key in label_keys},
        "risks": {key: _int(data.get(key)) for key in risk_keys},
        "status": "ready",
        "rule_version": data.get("rule_version"),
        "source_updated_at": str(data.get("source_updated_at") or ""),
        "generated_at": str(data.get("generated_at") or ""),
    }


async def list_member_segment_rows(
    db: AsyncSession,
    store_codes: Iterable[str],
    *,
    calc_date: date | None = None,
    kind: str = "segments",
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    label_code: str | None = None,
    risk_code: str | None = None,
) -> dict[str, Any]:
    codes = sorted({str(code).upper() for code in store_codes})
    target_date = calc_date or await latest_member_segment_date(db, codes)
    if not target_date:
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "calc_date": None}
    conditions = ["s.calc_date=:calc_date", "s.store_code=ANY(:store_codes)"]
    params: dict[str, Any] = {
        "calc_date": target_date,
        "store_codes": codes,
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    if kind == "risks":
        conditions.append("jsonb_array_length(s.risks)>0")
    elif kind == "wakeups":
        conditions.append("s.is_wakeup_candidate=true")
    elif kind != "segments":
        raise ValueError("unsupported member segment list kind")
    if keyword and keyword.strip():
        conditions.append("(s.member_no ILIKE :keyword OR m.member_name ILIKE :keyword)")
        params["keyword"] = f"%{keyword.strip()}%"
    if label_code:
        conditions.append("s.labels @> CAST(:label_filter AS jsonb)")
        params["label_filter"] = json.dumps([{"code": label_code.upper()}])
    if risk_code:
        conditions.append("s.risks @> CAST(:risk_filter AS jsonb)")
        params["risk_filter"] = json.dumps([{"code": risk_code.upper()}])
    where_sql = " AND ".join(conditions)
    total = (await db.execute(text(f"""
        SELECT COUNT(*) FROM dm.dm_member_segment_snapshot s
        JOIN dim.dim_member m ON m.member_no=s.member_no
        WHERE {where_sql}
    """), params)).scalar() or 0
    rows = (await db.execute(text(f"""
        SELECT s.calc_date,s.member_no,m.member_name,m.phone,s.store_code,
               COALESCE(ds.store_name,dw.warehouse_name,s.store_code) store_name,
               COALESCE(NULLIF(s.metrics->>'current_balance','')::numeric,0) current_balance,
               COALESCE(NULLIF(s.metrics->>'total_amount','')::numeric,0) total_amount,
               COALESCE(NULLIF(s.metrics->>'total_count','')::integer,0) total_count,
               NULLIF(s.metrics->>'last_consume_date','')::date last_consume_date,
               s.labels,s.risks,s.metrics,s.data_quality,s.is_wakeup_candidate,
               s.wakeup_priority,s.wakeup_reasons,s.preferences,s.suggested_products,
               s.responsibility_status,s.responsible_employee_no,s.candidate_guide_ids,
               s.rule_version,s.source_updated_at,s.generated_at
        FROM dm.dm_member_segment_snapshot s
        JOIN dim.dim_member m ON m.member_no=s.member_no
        LEFT JOIN dim.dim_store ds ON ds.store_code=s.store_code AND ds.source_system='baison'
        LEFT JOIN dim.dim_warehouse dw ON UPPER(dw.warehouse_code)=s.store_code AND dw.source_system='baison'
        WHERE {where_sql}
        ORDER BY CASE WHEN :kind='wakeups' THEN COALESCE(s.wakeup_priority,99) ELSE 99 END,
                 jsonb_array_length(s.risks) DESC,current_balance DESC NULLS LAST,
                 total_amount DESC NULLS LAST,s.member_no
        LIMIT :limit OFFSET :offset
    """), {**params, "kind": kind})).mappings().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for key in ("current_balance", "total_amount"):
            item[key] = round(_num(item.get(key)), 2)
        for key in ("calc_date", "last_consume_date"):
            item[key] = str(item.get(key) or "")[:10] or None
        for key in ("source_updated_at", "generated_at"):
            item[key] = str(item.get(key) or "")
        items.append(item)
    return {"items": items, "total": int(total), "page": page, "page_size": page_size, "calc_date": target_date.isoformat()}
