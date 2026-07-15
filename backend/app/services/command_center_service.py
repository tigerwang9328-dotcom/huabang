"""Daily boss command-center snapshot, inventory age and risk orchestration."""

from __future__ import annotations

import json
import hashlib
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.store_whitelist import ALLOWED_INVENTORY_CODES, ALLOWED_STORE_CODES
from app.services.sales_metric_service import PAY_DETAIL_SQL, rebuild_confirmed_sales_dws


ZERO = Decimal("0")
VALID_METRIC_STATUSES = {"ready", "estimated", "pending_data", "stale"}


def inventory_warning_source_id(
    warning_date: date,
    store_code: str | None,
    product_code: str | None,
    sku_code: str | None,
    warning_type: str,
) -> int:
    """Build a stable bigint key even when warning rows are rebuilt."""
    identity = "|".join(
        [str(warning_date), store_code or "", product_code or "", sku_code or "", warning_type]
    )
    return int.from_bytes(hashlib.sha256(identity.encode("utf-8")).digest()[:8], "big") & ((1 << 63) - 1)


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return ZERO


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else _decimal(value)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def build_metric(
    value: Any,
    *,
    source: str,
    as_of: Any = None,
    status: str | None = None,
    reason: str | None = None,
    decimals: int = 2,
) -> dict[str, Any]:
    if status is not None and status not in VALID_METRIC_STATUSES:
        raise ValueError(f"unknown metric status: {status}")
    if value is None:
        missing_status = "pending_data" if status in {None, "ready"} else status
        return {
            "value": None,
            "display": "待接入",
            "status": missing_status,
            "source": source,
            "as_of": _json_value(as_of),
            "reason": reason or "数据源尚未接入",
        }
    numeric = _decimal(value)
    display_value: float | int = round(float(numeric), decimals)
    if decimals == 0:
        display_value = int(round(float(numeric)))
    return {
        "value": display_value,
        "display": str(display_value),
        "status": status or "ready",
        "source": source,
        "as_of": _json_value(as_of),
        "reason": reason,
    }


def derive_metric_statuses(
    *,
    sales: dict[str, Any],
    ticket: dict[str, Any],
    inventory: dict[str, Any],
    members: dict[str, Any],
) -> dict[str, str]:
    sales_status = "ready" if ticket.get("synced_at") else "stale"
    sales_detail_status = "ready" if sales.get("etl_at") else "stale"
    returns_status = (
        "ready"
        if ticket.get("return_sync_completed_at") and ticket.get("return_amount") is not None
        else "stale"
    )
    coverage = sales.get("cost_coverage_rate")
    coverage_complete = coverage is None or _decimal(coverage) >= Decimal("1")
    gross_profit_status = (
        "ready"
        if bool(sales.get("is_cost_complete")) and coverage_complete
        else "estimated"
    )
    gross_margin_status = gross_profit_status if _decimal(sales.get("total_sales_amount")) != ZERO else "pending_data"
    return {
        "sales": sales_status,
        "sales_detail": sales_detail_status,
        "returns": returns_status,
        "actual_pay": sales_status,
        "gross_profit": gross_profit_status,
        "gross_margin": gross_margin_status,
        "online_sales": sales_status,
        "inventory": "ready" if inventory.get("updated_at") else "stale",
        "inventory_age": "estimated" if _decimal(inventory.get("age_unknown_qty")) > 0 else "ready",
        "vip_balance": "ready" if members.get("updated_at") else "stale",
        "operating_profit": "pending_data",
    }


def preserve_trusted_value(current: Any, *, source_ready: bool, previous: Any) -> Any:
    """Keep the last trusted value when a source is temporarily unavailable."""
    return current if source_ready else previous


def allocate_fifo_inventory(
    current_qty: Decimal,
    batches: Iterable[tuple[date, Decimal]],
    as_of: date,
) -> dict[str, Decimal]:
    """Allocate current stock to newest receipts after older receipts were sold first."""
    remaining = max(_decimal(current_qty), ZERO)
    result = {
        "qty_0_90": ZERO,
        "qty_91_180": ZERO,
        "qty_180_plus": ZERO,
        "qty_unknown": ZERO,
    }
    for received_on, quantity in sorted(batches, key=lambda item: item[0], reverse=True):
        if remaining <= 0:
            break
        allocated = min(max(_decimal(quantity), ZERO), remaining)
        age_days = max((as_of - received_on).days, 0)
        if age_days <= 90:
            bucket = "qty_0_90"
        elif age_days <= 180:
            bucket = "qty_91_180"
        else:
            bucket = "qty_180_plus"
        result[bucket] += allocated
        remaining -= allocated
    result["qty_unknown"] = remaining
    return result


def build_template_summary(
    *,
    sales: Decimal | None,
    gross_profit: Decimal | None,
    gross_margin: Decimal | None,
    finance_complete: bool,
    risk_count: int,
    pending_task_count: int,
) -> str:
    parts = (
        ["昨日销售数据未就绪"]
        if sales is None else [f"昨日销售{float(_decimal(sales)):,.0f}元"]
    )
    if gross_profit is not None and gross_margin is not None:
        parts.append(
            f"已接成本口径毛利{float(_decimal(gross_profit)):,.0f}元、毛利率{float(_decimal(gross_margin)) * 100:.1f}%"
        )
    if not finance_complete:
        parts.append("费用未完整接入，暂不判断最终盈亏")
    parts.append(f"当前重大异常{int(risk_count)}项、待处理任务{int(pending_task_count)}项")
    return "；".join(parts) + "。"


async def rebuild_inventory_age(db: AsyncSession, snapshot_date: date) -> dict[str, Any]:
    inventory_rows = (await db.execute(text("""
        SELECT b.warehouse_code,
               b.product_code,
               SUM(GREATEST(COALESCE(b.qty, 0), 0)) AS current_qty,
               MAX(b.synced_at) AS as_of_at,
               COALESCE(SUM(
                   GREATEST(COALESCE(b.qty, 0), 0) * sp.standard_purchase_price
               ) FILTER (
                   WHERE sp.standard_purchase_price IS NOT NULL
               ), 0) AS known_cost_amount
        FROM dwd.v_apparel_inventory_balance b
        LEFT JOIN dim.v_baison_sku_standard_purchase_price sp
          ON sp.product_code = b.product_code
         AND sp.color_code = COALESCE(BTRIM(b.color_code::text), '')
         AND sp.size_code = COALESCE(BTRIM(b.size_code::text), '')
        WHERE UPPER(b.warehouse_code) = ANY(:codes)
          AND b.product_code IS NOT NULL
        GROUP BY b.warehouse_code, b.product_code
        HAVING SUM(GREATEST(COALESCE(b.qty, 0), 0)) > 0
    """), {"codes": sorted(ALLOWED_INVENTORY_CODES)})).mappings().all()

    inbound_rows = (await db.execute(text("""
        WITH inbound AS (
            SELECT warehouse_code, product_code, record_date, quantity
            FROM dwd.dwd_baison_purchase_inbound
            UNION ALL
            SELECT warehouse_code, product_code, record_date, quantity
            FROM dwd.dwd_baison_transfer_inbound
        )
        SELECT UPPER(warehouse_code) AS warehouse_code, product_code, record_date,
               SUM(GREATEST(COALESCE(quantity, 0), 0)) AS quantity
        FROM inbound
        WHERE UPPER(warehouse_code) = ANY(:codes)
          AND product_code IS NOT NULL
          AND record_date <= :snapshot_date
        GROUP BY UPPER(warehouse_code), product_code, record_date
        HAVING SUM(GREATEST(COALESCE(quantity, 0), 0)) > 0
        ORDER BY warehouse_code, product_code, record_date DESC
    """), {"codes": sorted(ALLOWED_INVENTORY_CODES), "snapshot_date": snapshot_date})).mappings().all()

    batches: dict[tuple[str, str], list[tuple[date, Decimal]]] = defaultdict(list)
    for row in inbound_rows:
        batches[(row["warehouse_code"], row["product_code"])].append(
            (row["record_date"], _decimal(row["quantity"]))
        )

    await db.execute(
        text("DELETE FROM dm.dm_inventory_age_daily WHERE snapshot_date=:snapshot_date"),
        {"snapshot_date": snapshot_date},
    )
    payload = []
    for row in inventory_rows:
        key = (str(row["warehouse_code"]).upper(), row["product_code"])
        current_qty = _decimal(row["current_qty"])
        allocation = allocate_fifo_inventory(current_qty, batches.get(key, []), snapshot_date)
        effective_unit_cost = _decimal(row["known_cost_amount"]) / current_qty if current_qty else ZERO
        dates = [item[0] for item in batches.get(key, [])]
        payload.append({
            "snapshot_date": snapshot_date,
            "as_of_at": row["as_of_at"],
            "warehouse_code": key[0],
            "product_code": key[1],
            "current_quantity": current_qty,
            "cost_unit": effective_unit_cost if effective_unit_cost > 0 else None,
            **allocation,
            "amount_0_90": allocation["qty_0_90"] * effective_unit_cost,
            "amount_91_180": allocation["qty_91_180"] * effective_unit_cost,
            "amount_180_plus": allocation["qty_180_plus"] * effective_unit_cost,
            "amount_unknown": allocation["qty_unknown"] * effective_unit_cost,
            "first_inbound_date": min(dates) if dates else None,
            "last_inbound_date": max(dates) if dates else None,
            "data_quality": "ready" if allocation["qty_unknown"] == 0 else "partial",
        })

    insert_sql = text("""
        INSERT INTO dm.dm_inventory_age_daily (
            snapshot_date, as_of_at, warehouse_code, product_code,
            current_quantity, cost_unit, qty_0_90, qty_91_180, qty_180_plus,
            qty_unknown, amount_0_90, amount_91_180, amount_180_plus,
            amount_unknown, first_inbound_date, last_inbound_date, data_quality, generated_at
        ) VALUES (
            :snapshot_date, :as_of_at, :warehouse_code, :product_code,
            :current_quantity, :cost_unit, :qty_0_90, :qty_91_180, :qty_180_plus,
            :qty_unknown, :amount_0_90, :amount_91_180, :amount_180_plus,
            :amount_unknown, :first_inbound_date, :last_inbound_date, :data_quality, now()
        )
    """)
    for offset in range(0, len(payload), 1000):
        await db.execute(insert_sql, payload[offset:offset + 1000])

    await db.execute(text("""
        UPDATE dws.dws_inventory_daily d SET
            age_91_180_amount = a.amount_91_180,
            age_180_plus_amount = a.amount_180_plus
        FROM (
            SELECT warehouse_code,
                   COALESCE(SUM(amount_91_180), 0) amount_91_180,
                   COALESCE(SUM(amount_180_plus), 0) amount_180_plus
            FROM dm.dm_inventory_age_daily
            WHERE snapshot_date=:snapshot_date
            GROUP BY warehouse_code
        ) a
        WHERE d.stat_date=:snapshot_date AND UPPER(d.store_code)=a.warehouse_code
    """), {"snapshot_date": snapshot_date})

    unknown_qty = sum((_decimal(item["qty_unknown"]) for item in payload), ZERO)
    return {"snapshot_date": str(snapshot_date), "rows": len(payload), "unknown_qty": float(unknown_qty)}


async def _inventory_warning_thresholds(db: AsyncSession) -> dict[str, dict[str, Any]]:
    defaults = {
        "R007": {"max_ratio": 0.30},
        "R008": {"max_amount": 30000},
        "R016": {"min_inventory": 10, "max_product_year_age": 1},
        "R017": {"max_available_sizes": 1, "min_inventory": 3},
        "R018": {"min_inventory": 30, "sales_days": 30},
        "R019": {"max_sellable_days": 7},
        "R020": {"high_inventory": 12, "low_inventory": 1},
        "R021": {"min_age_days": 180, "risk_amount": 30000},
    }
    rows = (await db.execute(text("""
        SELECT rule_id, thresholds
        FROM app.app_business_rule_config
        WHERE enabled=true AND rule_id BETWEEN 'R006' AND 'R021'
    """))).mappings().all()
    for row in rows:
        defaults.setdefault(row["rule_id"], {}).update(row["thresholds"] or {})
    return defaults


async def rebuild_inventory_warnings(db: AsyncSession, snapshot_date: date) -> dict[str, Any]:
    rule_thresholds = await _inventory_warning_thresholds(db)
    age_90_ratio = float(rule_thresholds["R007"].get("max_ratio", 0.30))
    age_180_risk = float(rule_thresholds["R008"].get("max_amount", 30000))
    clearance_risk = float(rule_thresholds["R021"].get("risk_amount", 30000))
    max_sellable_days = int(rule_thresholds["R019"].get("max_sellable_days", 7))
    min_high_inventory = int(rule_thresholds["R018"].get("min_inventory", 30))
    max_available_sizes = int(rule_thresholds["R017"].get("max_available_sizes", 1))
    min_size_inventory = int(rule_thresholds["R017"].get("min_inventory", 3))
    max_product_year_age = int(rule_thresholds["R016"].get("max_product_year_age", 1))
    low_motion_sales_days = int(rule_thresholds["R018"].get("sales_days", 30))
    transfer_high = int(rule_thresholds["R020"].get("high_inventory", 12))
    transfer_low = int(rule_thresholds["R020"].get("low_inventory", 1))
    seasonal_min_inventory = int(rule_thresholds["R016"].get("min_inventory", 10))
    await db.execute(
        text("DELETE FROM dm.dm_inventory_warning WHERE warning_date=:snapshot_date"),
        {"snapshot_date": snapshot_date},
    )
    await db.execute(text("""
        INSERT INTO dm.dm_inventory_warning (
            warning_date, store_code, product_code, warning_type, warning_level,
            current_quantity, current_cost_amount, age_days, description,
            rule_id, thresholds, evidence, source_name, generated_at
        )
        SELECT snapshot_date, warehouse_code, product_code,
               CASE WHEN qty_180_plus > 0 THEN 'age_180' ELSE 'age_90' END,
               CASE WHEN qty_180_plus > 0 AND COALESCE(amount_180_plus,0) >= :age_180_risk THEN 'risk' ELSE 'warning' END,
               ROUND(current_quantity)::int,
               CASE WHEN qty_180_plus > 0 THEN amount_180_plus ELSE amount_91_180 END,
               CASE WHEN qty_180_plus > 0 THEN 181 ELSE 91 END,
               CASE WHEN qty_180_plus > 0
                    THEN product_code || '含180天以上库存，建议清仓或返仓'
                    ELSE product_code || '含90天以上库存，建议复核动销和调拨' END,
               CASE WHEN qty_180_plus > 0 THEN 'R008' ELSE 'R007' END,
               CASE WHEN qty_180_plus > 0
                    THEN jsonb_build_object('max_amount', CAST(:age_180_risk AS numeric))
                    ELSE jsonb_build_object('max_ratio', CAST(:age_90_ratio AS numeric)) END,
               jsonb_build_object('qty_91_180', qty_91_180, 'qty_180_plus', qty_180_plus,
                                  'amount_91_180', amount_91_180, 'amount_180_plus', amount_180_plus),
               'fifo_inbound',
               now()
        FROM dm.dm_inventory_age_daily
        WHERE snapshot_date=:snapshot_date
          AND (qty_180_plus > 0
               OR (current_quantity > 0
                   AND qty_91_180/current_quantity>=CAST(:age_90_ratio AS numeric)))
    """), {
        "snapshot_date": snapshot_date,
        "age_90_ratio": age_90_ratio,
        "age_180_risk": age_180_risk,
    })
    await db.execute(text("""
        INSERT INTO dm.dm_inventory_warning (
            warning_date, store_code, product_code, sku_code, warning_type,
            warning_level, current_quantity, description,
            rule_id, thresholds, evidence, source_name, generated_at
        )
        SELECT :snapshot_date, UPPER(warehouse_code), product_code, sku_code,
               'negative', 'critical', ROUND(SUM(qty))::int,
               product_code || '存在负库存，请核对入库、调拨或销售出库',
               'R006', '{}'::jsonb,
               jsonb_build_object('quantity', ROUND(SUM(qty))::int),
               'apparel_inventory', now()
        FROM dwd.v_apparel_inventory_balance
        WHERE UPPER(warehouse_code)=ANY(:codes) AND qty < 0
        GROUP BY UPPER(warehouse_code), product_code, sku_code
    """), {"snapshot_date": snapshot_date, "codes": sorted(ALLOWED_INVENTORY_CODES)})
    await db.execute(text("""
        INSERT INTO dm.dm_inventory_warning (
            warning_date, store_code, product_code, warning_type, warning_level,
            current_quantity, current_cost_amount, sellable_days, description,
            rule_id, thresholds, evidence, source_name, generated_at
        )
        WITH sales AS (
            SELECT store_code, product_code,
                   SUM(net_quantity) FILTER (WHERE stat_date >= :sales_7_start) qty_7d,
                   SUM(net_quantity) FILTER (WHERE stat_date >= :sales_30_start) qty_30d
            FROM dws.dws_product_daily
            WHERE stat_date BETWEEN :sales_30_start AND :snapshot_date
            GROUP BY store_code, product_code
        )
        SELECT a.snapshot_date, a.warehouse_code, a.product_code,
               CASE WHEN COALESCE(s.qty_7d,0) > 0 THEN 'low_sellable_days' ELSE 'low_motion_high_stock' END,
               'warning', ROUND(a.current_quantity)::int,
               COALESCE(a.amount_0_90,0)+COALESCE(a.amount_91_180,0)+COALESCE(a.amount_180_plus,0),
               CASE WHEN COALESCE(s.qty_7d,0)>0 THEN CEIL(a.current_quantity/(s.qty_7d/7.0))::int END,
               CASE WHEN COALESCE(s.qty_7d,0)>0
                    THEN a.product_code || '有销量但可售天数不超过7天，建议补货或调拨'
                    ELSE a.product_code || '库存较高且30天无销量，建议清仓或调拨' END,
               CASE WHEN COALESCE(s.qty_7d,0)>0 THEN 'R019' ELSE 'R018' END,
               jsonb_build_object('max_sellable_days', CAST(:max_sellable_days AS integer),
                                  'min_inventory', CAST(:min_high_inventory AS integer)),
               jsonb_build_object('qty_7d', COALESCE(s.qty_7d,0), 'qty_30d', COALESCE(s.qty_30d,0),
                                  'inventory_qty', a.current_quantity),
               'dws_product_daily+fifo_inbound',
               now()
        FROM dm.dm_inventory_age_daily a
        LEFT JOIN sales s ON s.store_code=a.warehouse_code AND s.product_code=a.product_code
        WHERE a.snapshot_date=:snapshot_date
          AND ((COALESCE(s.qty_7d,0)>0 AND a.current_quantity/(s.qty_7d/7.0)<=CAST(:max_sellable_days AS integer))
            OR (a.current_quantity>=CAST(:min_high_inventory AS integer) AND COALESCE(s.qty_30d,0)<=0))
    """), {
        "snapshot_date": snapshot_date,
        "sales_7_start": snapshot_date - timedelta(days=6),
        "sales_30_start": snapshot_date - timedelta(days=29),
        "max_sellable_days": max_sellable_days,
        "min_high_inventory": min_high_inventory,
    })
    await db.execute(text("""
        INSERT INTO dm.dm_inventory_warning (
            warning_date, store_code, product_code, warning_type, warning_level,
            current_quantity, description, rule_id, thresholds, evidence,
            source_name, generated_at
        )
        WITH inventory AS (
            SELECT UPPER(warehouse_code) store_code, product_code,
                   TRIM(LEADING '-' FROM COALESCE(color_code,'')) color_code,
                   ROUND(SUM(GREATEST(COALESCE(qty,0),0)))::int inventory_qty,
                   COUNT(DISTINCT NULLIF(TRIM(size_code),''))
                       FILTER (WHERE COALESCE(qty,0)>0) available_sizes
            FROM dwd.v_apparel_inventory_balance
            WHERE UPPER(warehouse_code)=ANY(:codes)
            GROUP BY UPPER(warehouse_code), product_code,
                     TRIM(LEADING '-' FROM COALESCE(color_code,''))
        ), listed AS (
            SELECT product_code,
                   TRIM(LEADING '-' FROM COALESCE(color_code,'')) color_code,
                   COUNT(DISTINCT NULLIF(TRIM(size_code),'')) listed_sizes
            FROM dim.dim_sku
            WHERE source_system='baison' AND COALESCE(status,'active')='active'
              AND NULLIF(TRIM(size_code),'') IS NOT NULL
            GROUP BY product_code, TRIM(LEADING '-' FROM COALESCE(color_code,''))
        )
        SELECT :snapshot_date, i.store_code, i.product_code, 'size_break', 'warning',
               i.inventory_qty,
               i.product_code || '仅剩' || i.available_sizes || '个尺码，建议复核断码调拨',
               'R017',
               jsonb_build_object('max_available_sizes', CAST(:max_available_sizes AS integer),
                                  'min_inventory', CAST(:min_size_inventory AS integer)),
               jsonb_build_object('color_code', i.color_code,
                                  'available_sizes', i.available_sizes,
                                  'listed_sizes', l.listed_sizes,
                                  'inventory_qty', i.inventory_qty),
               'apparel_inventory+dim_sku', now()
        FROM inventory i
        JOIN listed l ON l.product_code=i.product_code AND l.color_code=i.color_code
        WHERE i.inventory_qty>=CAST(:min_size_inventory AS integer)
          AND i.available_sizes<=CAST(:max_available_sizes AS integer)
          AND l.listed_sizes>i.available_sizes
    """), {
        "snapshot_date": snapshot_date,
        "codes": sorted(ALLOWED_INVENTORY_CODES),
        "max_available_sizes": max_available_sizes,
        "min_size_inventory": min_size_inventory,
    })
    await db.execute(text("""
        INSERT INTO dm.dm_inventory_warning (
            warning_date, store_code, product_code, warning_type, warning_level,
            current_quantity, description, rule_id, thresholds, evidence,
            source_name, generated_at
        )
        WITH product_year AS (
            SELECT product_code, MAX(year) FILTER (WHERE year IS NOT NULL) product_year
            FROM dim.dim_product
            WHERE source_system='baison'
            GROUP BY product_code
        ), inventory AS (
            SELECT UPPER(warehouse_code) store_code, product_code,
                   ROUND(SUM(GREATEST(COALESCE(qty,0),0)))::int inventory_qty
            FROM dwd.v_apparel_inventory_balance
            WHERE UPPER(warehouse_code)=ANY(:codes)
            GROUP BY UPPER(warehouse_code), product_code
        )
        SELECT :snapshot_date, i.store_code, i.product_code, 'seasonal', 'warning',
               i.inventory_qty,
               i.product_code || '为' || p.product_year || '年旧款且仍有库存，建议评估清仓或返仓',
               'R016',
               jsonb_build_object('max_product_year_age', CAST(:max_product_year_age AS integer),
                                  'min_inventory', CAST(:seasonal_min_inventory AS integer)),
               jsonb_build_object('product_year', p.product_year,
                                  'analysis_year', EXTRACT(YEAR FROM CAST(:snapshot_date AS date))::int,
                                  'inventory_qty', i.inventory_qty),
               'apparel_inventory+dim_product', now()
        FROM inventory i
        JOIN product_year p ON p.product_code=i.product_code
        WHERE i.inventory_qty>=CAST(:seasonal_min_inventory AS integer)
          AND p.product_year IS NOT NULL
          AND EXTRACT(YEAR FROM CAST(:snapshot_date AS date))::int-p.product_year>CAST(:max_product_year_age AS integer)
    """), {
        "snapshot_date": snapshot_date,
        "codes": sorted(ALLOWED_INVENTORY_CODES),
        "max_product_year_age": max_product_year_age,
        "seasonal_min_inventory": seasonal_min_inventory,
    })
    await db.execute(text("""
        INSERT INTO dm.dm_inventory_warning (
            warning_date, store_code, product_code, warning_type, warning_level,
            current_quantity, description, rule_id, thresholds, evidence,
            source_name, generated_at
        )
        WITH recent_sales AS (
            SELECT store_code, product_code,
                   ROUND(SUM(GREATEST(COALESCE(net_quantity,0),0)))::int sales_qty
            FROM dws.dws_product_daily
            WHERE stat_date BETWEEN :sales_start AND :snapshot_date
              AND store_code=ANY(:store_codes)
            GROUP BY store_code, product_code
            HAVING SUM(GREATEST(COALESCE(net_quantity,0),0))>0
        ), inventory AS (
            SELECT UPPER(warehouse_code) store_code, product_code,
                   ROUND(SUM(COALESCE(qty,0)))::int inventory_qty
            FROM dwd.v_apparel_inventory_balance
            WHERE UPPER(warehouse_code)=ANY(:store_codes)
            GROUP BY UPPER(warehouse_code), product_code
        )
        SELECT :snapshot_date, s.store_code, s.product_code, 'stockout', 'warning',
               COALESCE(i.inventory_qty,0),
               s.product_code || '近' || CAST(:sales_days AS integer) || '天有销量但当前缺货，建议补货或调拨',
               'R019', jsonb_build_object('sales_days', CAST(:sales_days AS integer), 'stockout_quantity', 0),
               jsonb_build_object('sales_qty', s.sales_qty,
                                  'inventory_qty', COALESCE(i.inventory_qty,0)),
               'dws_product_daily+apparel_inventory', now()
        FROM recent_sales s
        LEFT JOIN inventory i ON i.store_code=s.store_code AND i.product_code=s.product_code
        WHERE COALESCE(i.inventory_qty,0)<=0
    """), {
        "snapshot_date": snapshot_date,
        "sales_start": snapshot_date - timedelta(days=max(low_motion_sales_days - 1, 0)),
        "sales_days": low_motion_sales_days,
        "store_codes": sorted(ALLOWED_STORE_CODES),
    })
    await db.execute(text("""
        INSERT INTO dm.dm_inventory_warning (
            warning_date, store_code, product_code, warning_type, warning_level,
            current_quantity, description, rule_id, thresholds, evidence,
            source_name, generated_at
        )
        WITH inventory AS (
            SELECT UPPER(warehouse_code) store_code, product_code,
                   ROUND(SUM(GREATEST(COALESCE(qty,0),0)))::int inventory_qty
            FROM dwd.v_apparel_inventory_balance
            WHERE UPPER(warehouse_code)=ANY(:store_codes)
            GROUP BY UPPER(warehouse_code), product_code
        ), candidates AS (
            SELECT DISTINCT ON (low.store_code, low.product_code)
                   low.store_code target_store, low.product_code,
                   low.inventory_qty target_qty, high.store_code source_store,
                   high.inventory_qty source_qty
            FROM inventory low
            JOIN inventory high ON high.product_code=low.product_code
                               AND high.store_code<>low.store_code
            WHERE low.inventory_qty<=CAST(:transfer_low AS integer)
              AND high.inventory_qty>=CAST(:transfer_high AS integer)
            ORDER BY low.store_code, low.product_code, high.inventory_qty DESC, high.store_code
        )
        SELECT :snapshot_date, c.target_store, c.product_code, kind.warning_type, 'warning',
               c.target_qty,
               CASE kind.warning_type
                    WHEN 'store_imbalance' THEN c.product_code || '门店库存分布不均，建议复核'
                    ELSE c.product_code || '可从' || c.source_store || '调拨至' || c.target_store END,
               'R020',
               jsonb_build_object('high_inventory', CAST(:transfer_high AS integer),
                                  'low_inventory', CAST(:transfer_low AS integer)),
               jsonb_build_object('source_store', c.source_store, 'source_qty', c.source_qty,
                                  'target_store', c.target_store, 'target_qty', c.target_qty,
                                  'suggested_transfer_qty', GREATEST(LEAST(c.source_qty-CAST(:transfer_high AS integer),
                                                                         CAST(:transfer_high AS integer)-c.target_qty),1)),
               'apparel_inventory', now()
        FROM candidates c
        CROSS JOIN (VALUES ('store_imbalance'), ('transfer')) kind(warning_type)
    """), {
        "snapshot_date": snapshot_date,
        "store_codes": sorted(ALLOWED_STORE_CODES),
        "transfer_high": transfer_high,
        "transfer_low": transfer_low,
    })
    await db.execute(text("""
        INSERT INTO dm.dm_inventory_warning (
            warning_date, store_code, product_code, warning_type, warning_level,
            current_quantity, current_cost_amount, age_days, description,
            rule_id, thresholds, evidence, source_name, generated_at
        )
        WITH sales AS (
            SELECT store_code, product_code, COALESCE(SUM(net_quantity),0) qty_30d
            FROM dws.dws_product_daily
            WHERE stat_date BETWEEN :sales_30_start AND :snapshot_date
            GROUP BY store_code, product_code
        )
        SELECT a.snapshot_date, a.warehouse_code, a.product_code,
               'clearance_return',
               CASE WHEN COALESCE(a.amount_180_plus,0)>=CAST(:clearance_risk AS numeric) THEN 'risk' ELSE 'warning' END,
               ROUND(a.qty_180_plus)::int, a.amount_180_plus, 181,
               a.product_code || '存在180天以上库存，建议清仓或返仓并保留处理记录',
               'R021',
               jsonb_build_object('min_age_days', 180, 'risk_amount', CAST(:clearance_risk AS numeric)),
               jsonb_build_object('qty_180_plus', a.qty_180_plus,
                                  'amount_180_plus', a.amount_180_plus,
                                  'qty_30d', COALESCE(s.qty_30d,0)),
               'fifo_inbound+dws_product_daily', now()
        FROM dm.dm_inventory_age_daily a
        LEFT JOIN sales s ON s.store_code=a.warehouse_code AND s.product_code=a.product_code
        WHERE a.snapshot_date=:snapshot_date AND a.qty_180_plus>0
          AND (COALESCE(s.qty_30d,0)<=0 OR COALESCE(a.amount_180_plus,0)>=CAST(:clearance_risk AS numeric))
    """), {
        "snapshot_date": snapshot_date,
        "sales_30_start": snapshot_date - timedelta(days=29),
        "clearance_risk": clearance_risk,
    })
    count = (await db.execute(
        text("SELECT COUNT(*) FROM dm.dm_inventory_warning WHERE warning_date=:snapshot_date"),
        {"snapshot_date": snapshot_date},
    )).scalar() or 0
    return {"snapshot_date": str(snapshot_date), "warning_count": int(count)}


async def create_inventory_warning_task_drafts(
    db: AsyncSession,
    warning_date: date,
    creator_id: int,
) -> list[int]:
    warnings = (await db.execute(text("""
        SELECT id, warning_date, store_code, product_code, sku_code, warning_type,
               warning_level, current_quantity, current_cost_amount, description,
               rule_id, thresholds, evidence, source_name
        FROM dm.dm_inventory_warning
        WHERE warning_date=:warning_date AND warning_level IN ('critical','risk')
        ORDER BY id
    """), {"warning_date": warning_date})).mappings().all()
    created: list[int] = []
    for warning in warnings:
        source_id = inventory_warning_source_id(
            warning["warning_date"], warning.get("store_code"), warning.get("product_code"),
            warning.get("sku_code"), warning["warning_type"],
        )
        task_id = (await db.execute(text("""
            SELECT id FROM app.app_action_task
            WHERE source_type='inventory_warning' AND source_id=:source_id AND is_deleted=false
            ORDER BY id DESC LIMIT 1
        """), {"source_id": source_id})).scalar()
        if task_id is None:
            task_no = f"INV-{warning_date:%Y%m%d}-{source_id & 0xFFFFFF:06X}"
            task_id = (await db.execute(text("""
                INSERT INTO app.app_action_task (
                    task_no, title, description, data_evidence_text, suggested_actions,
                    feedback_requirement, source_type, source_id, related_store_code,
                    related_product_code, related_date, assignee_role, creator_id, status,
                    priority, risk_level, requires_human_confirm, due_date, is_deleted
                ) VALUES (
                    :task_no, :title, :description, :evidence, CAST(:actions AS json),
                    '提交处理结果、图片或调拨/清仓记录', 'inventory_warning', :source_id,
                    :store_code, :product_code, :related_date, 'store_manager', :creator_id,
                    'draft', :priority, :risk_level, true, :due_date, false
                ) RETURNING id
            """), {
                "task_no": task_no,
                "title": f"【库存预警】{warning.get('product_code') or warning.get('sku_code') or '库存异常'}",
                "description": warning.get("description") or "请复核库存预警",
                "evidence": json.dumps({
                    "rule_id": warning.get("rule_id"),
                    "source_name": warning.get("source_name"),
                    "thresholds": warning.get("thresholds") or {},
                    "evidence": warning.get("evidence") or {},
                    "current_quantity": float(warning.get("current_quantity") or 0),
                    "current_cost_amount": float(warning.get("current_cost_amount") or 0),
                }, ensure_ascii=False, default=str),
                "actions": json.dumps(["复核库存、动销和尺码；提交补货、调拨、返仓或清仓处理意见"], ensure_ascii=False),
                "source_id": source_id,
                "store_code": warning.get("store_code"),
                "product_code": warning.get("product_code"),
                "related_date": warning_date,
                "creator_id": creator_id,
                "priority": 10 if warning["warning_level"] == "critical" else 8,
                "risk_level": warning["warning_level"],
                "due_date": warning_date + timedelta(days=3),
            })).scalar_one()
            created.append(int(task_id))
        await db.execute(text("""
            UPDATE dm.dm_inventory_warning
            SET is_converted_to_task=true, task_id=:task_id
            WHERE id=:warning_id
        """), {"task_id": task_id, "warning_id": warning["id"]})
    return created


async def _persist_rule_results(db: AsyncSession, report_date: date, results: list[dict[str, Any]]) -> int:
    from app.services.exception_rule_service import persist_rule_findings

    return await persist_rule_findings(db, report_date, results)


async def build_boss_snapshot(db: AsyncSession, report_date: date, inventory_date: date) -> dict[str, Any]:
    existing_row = (await db.execute(text("""
        SELECT * FROM dm.dm_boss_daily_report WHERE report_date=:report_date
    """), {"report_date": report_date})).mappings().first()
    existing = dict(existing_row) if existing_row else {}
    previous_freshness = existing.get("source_freshness") or {}

    sales = (await db.execute(text("""
        SELECT total_sales_amount, offline_sales_amount, total_order_count,
               total_item_count, total_return_amount, gross_profit, gross_margin,
               avg_order_value, items_per_order, avg_discount_rate,
               is_cost_complete, etl_at,
               (SELECT COALESCE(
                    SUM(ABS(net_sales_amount)) FILTER (WHERE is_cost_complete)
                    / NULLIF(SUM(ABS(net_sales_amount)), 0), 0
                )
                FROM dws.dws_product_daily p
                WHERE p.stat_date=:report_date AND p.store_code=ANY(:store_codes)) AS cost_coverage_rate
        FROM dws.dws_company_daily WHERE stat_date=:report_date
    """), {
        "report_date": report_date,
        "store_codes": sorted(ALLOWED_STORE_CODES),
    })).mappings().first() or {}
    finance = (await db.execute(text("""
        SELECT operating_profit, operating_margin, total_expense,
               expense_coverage_rate, missing_expense_types,
               finance_approved, operating_profit_status, profit_reasons, etl_at
        FROM dws.dws_finance_daily
        WHERE stat_date=:report_date AND store_code='ALL'
    """), {"report_date": report_date})).mappings().first() or {}
    ticket = (await db.execute(text(f"""
        WITH pay AS ({PAY_DETAIL_SQL}), recharge AS (
            SELECT COALESCE(SUM(recharge_amount),0) recharge_amount
            FROM dwd.dwd_store_recharge_daily
            WHERE biz_date=:report_date AND store_code=ANY(:store_codes)
        ), return_sync AS (
            SELECT CASE
                     WHEN r.status='success'
                      AND r.biz_start_time <= CAST(:report_date AS date)
                      AND r.biz_end_time >= CAST(:report_date AS date) + INTERVAL '1 day' - INTERVAL '1 second'
                     THEN r.completed_at
                   END AS completed_at
            FROM ods.ods_baison_pos_ticket_sync_run r
            WHERE r.biz_start_time < CAST(:report_date AS date) + INTERVAL '1 day'
              AND r.biz_end_time >= CAST(:report_date AS date)
            ORDER BY r.started_at DESC, r.id DESC
            LIMIT 1
        )
        SELECT COALESCE(SUM(COALESCE(pay.sales_amount,t.sales_amount)),0) sales_amount,
               COALESCE(SUM(COALESCE(pay.online_sales_amount,0)),0) online_sales_amount,
               COALESCE(SUM(COALESCE(pay.offline_sales_amount,t.sales_amount)),0) offline_sales_amount,
               COALESCE(SUM(COALESCE(pay.actual_pay_amount,t.actual_pay_amount)),0)+(SELECT recharge_amount FROM recharge) actual_pay_amount,
               COALESCE(SUM(COALESCE(pay.refund_amount,0)),0) return_amount,
               COALESCE(SUM(COALESCE(pay.sales_amount,t.sales_amount)) FILTER (
                   WHERE COALESCE(NULLIF(BTRIM(t.vip_code::text), ''),
                                  NULLIF(BTRIM(t.customer_code::text), '')) IS NOT NULL
               ),0) vip_sales_amount,
               MAX(t.synced_at) synced_at,
               (SELECT completed_at FROM return_sync) return_sync_completed_at
        FROM dwd.dwd_pos_ticket t
        LEFT JOIN pay ON pay.ticket_no=t.ticket_no
        WHERE t.biz_date=:report_date AND t.store_code=ANY(:store_codes)
          AND COALESCE(t.is_void,false)=false AND COALESCE(t.is_pending,false)=false
    """), {
        "sd": report_date, "ed": report_date, "report_date": report_date,
        "store_codes": sorted(ALLOWED_STORE_CODES),
    })).mappings().first() or {}
    inventory = (await db.execute(text("""
        SELECT COALESCE(SUM(total_quantity),0) total_qty,
               COALESCE(SUM(total_cost_amount),0) total_amount,
               COALESCE(SUM(age_91_180_amount),0) age_91_180_amount,
               COALESCE(SUM(age_180_plus_amount),0) age_180_plus_amount,
               COALESCE((SELECT SUM(qty_unknown) FROM dm.dm_inventory_age_daily
                         WHERE snapshot_date=:inventory_date),0) age_unknown_qty,
               COALESCE((SELECT SUM(amount_unknown) FROM dm.dm_inventory_age_daily
                         WHERE snapshot_date=:inventory_date),0) age_unknown_amount,
               BOOL_AND(is_cost_complete) cost_complete,
               (SELECT MAX(synced_at) FROM dwd.v_apparel_inventory_balance
                WHERE UPPER(warehouse_code)=ANY(:codes)) updated_at
        FROM dws.dws_inventory_daily WHERE stat_date=:inventory_date
          AND UPPER(store_code)=ANY(:codes)
    """), {"inventory_date": inventory_date, "codes": sorted(ALLOWED_INVENTORY_CODES)})).mappings().first() or {}
    members = (await db.execute(text("""
        SELECT COALESCE(SUM(GREATEST(COALESCE(current_balance,0),0)),0) vip_balance,
               COUNT(*) FILTER (WHERE current_balance<0) negative_count,
               COALESCE(SUM(ABS(current_balance)) FILTER (WHERE current_balance<0),0) negative_amount,
               MAX(balance_updated_at) updated_at
        FROM dim.dim_member
        WHERE UPPER(register_store)=ANY(:codes) AND COALESCE(status,'active')='active'
    """), {"codes": sorted(ALLOWED_INVENTORY_CODES)})).mappings().first() or {}
    tasks = (await db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE status IN ('draft','pending','processing','overdue')) pending,
               COUNT(*) FILTER (WHERE status='overdue' OR (due_date<CURRENT_DATE AND status NOT IN ('closed','cancelled'))) overdue
        FROM app.app_action_task WHERE is_deleted=false
    """))).mappings().first() or {}
    risks = (await db.execute(text("""
        SELECT COUNT(*) total,
               COUNT(*) FILTER (WHERE severity IN ('critical','risk')) major
        FROM dm.dm_exception_audit WHERE audit_date=:report_date
    """), {"report_date": report_date})).mappings().first() or {}
    warning_count = (await db.execute(text(
        "SELECT COUNT(*) FROM dm.dm_inventory_warning WHERE warning_date=:inventory_date"
    ), {"inventory_date": inventory_date})).scalar() or 0

    ticket_ready = bool(ticket.get("synced_at"))
    return_source_ready = bool(ticket.get("return_sync_completed_at"))
    sales_detail_ready = bool(sales.get("etl_at"))
    inventory_ready = bool(inventory.get("updated_at"))
    member_ready = bool(members.get("updated_at"))
    finance_ready = bool(finance.get("etl_at"))

    total_sales = _optional_decimal(preserve_trusted_value(
        ticket.get("sales_amount"), source_ready=ticket_ready, previous=existing.get("total_sales")
    ))
    online_sales = _optional_decimal(preserve_trusted_value(
        ticket.get("online_sales_amount"), source_ready=ticket_ready, previous=existing.get("online_sales")
    ))
    offline_sales = _optional_decimal(preserve_trusted_value(
        ticket.get("offline_sales_amount"), source_ready=ticket_ready, previous=existing.get("offline_sales")
    ))
    actual_pay_amount = _optional_decimal(preserve_trusted_value(
        ticket.get("actual_pay_amount"), source_ready=ticket_ready, previous=existing.get("actual_pay_amount")
    ))
    vip_sales = _optional_decimal(preserve_trusted_value(
        ticket.get("vip_sales_amount"), source_ready=ticket_ready, previous=existing.get("vip_sales_amount")
    ))
    return_amount = _optional_decimal(preserve_trusted_value(
        ticket.get("return_amount"),
        source_ready=return_source_ready,
        previous=existing.get("return_amount"),
    ))
    gross_profit = preserve_trusted_value(
        sales.get("gross_profit"), source_ready=sales_detail_ready, previous=existing.get("gross_profit")
    )
    cost_complete = (
        bool(sales.get("is_cost_complete"))
        if sales_detail_ready else bool(existing.get("is_cost_complete"))
    )
    source_freshness = {
        "sales": {
            "business_date": str(report_date),
            "updated_at": _json_value(sales.get("etl_at") or previous_freshness.get("sales", {}).get("updated_at")),
            "cost_coverage_rate": _json_value(sales.get("cost_coverage_rate")),
        },
        "inventory": {
            "snapshot_date": str(inventory_date),
            "updated_at": _json_value(inventory.get("updated_at") or previous_freshness.get("inventory", {}).get("updated_at")),
        },
        "member": {
            "scope": sorted(ALLOWED_INVENTORY_CODES),
            "updated_at": _json_value(members.get("updated_at") or previous_freshness.get("member", {}).get("updated_at")),
        },
        "online": {
            "status": "ready" if ticket_ready else "stale",
            "source": "baison_payment.011",
            "business_date": str(report_date),
        },
        "returns": {
            "status": "ready" if return_source_ready else "stale",
            "source": "baison_pos.refund_amount",
            "business_date": str(report_date),
            "updated_at": _json_value(ticket.get("return_sync_completed_at")),
        },
        "finance": {
            "status": finance.get("operating_profit_status") or "pending_data",
            "reason": (
                "费用完整并已核准"
                if finance.get("operating_profit_status") == "ready"
                else "费用不完整，经营利润为估算值"
            ),
            "expense_coverage_rate": _json_value(finance.get("expense_coverage_rate")),
            "missing_expense_types": _json_value(finance.get("missing_expense_types") or []),
            "known_expense_amount": _json_value(finance.get("total_expense")),
            "updated_at": _json_value(finance.get("etl_at")),
        },
    }
    metric_status = derive_metric_statuses(
        sales=dict(sales), ticket=dict(ticket), inventory=dict(inventory), members=dict(members)
    )
    metric_status["operating_profit"] = (
        finance.get("operating_profit_status") if finance_ready else "pending_data"
    ) or "pending_data"
    finance_complete = metric_status["operating_profit"] == "ready"
    summary = build_template_summary(
        sales=total_sales,
        gross_profit=_optional_decimal(gross_profit),
        gross_margin=(
            _optional_decimal(gross_profit) / total_sales
            if gross_profit is not None and total_sales else None
        ),
        finance_complete=finance_complete,
        risk_count=int(risks.get("major") or 0),
        pending_task_count=int(tasks.get("pending") or 0),
    )
    params = {
        "report_date": report_date,
        "total_sales": total_sales,
        "offline_sales": offline_sales,
        "online_sales": online_sales,
        "actual_pay_amount": actual_pay_amount,
        "net_sales": (
            total_sales - return_amount
            if total_sales is not None and return_amount is not None
            else None
            if sales_detail_ready
            else existing.get("net_sales")
        ),
        "order_count": preserve_trusted_value(
            int(sales.get("total_order_count") or 0), source_ready=sales_detail_ready, previous=existing.get("order_count")
        ),
        "item_count": preserve_trusted_value(
            int(sales.get("total_item_count") or 0), source_ready=sales_detail_ready, previous=existing.get("item_count")
        ),
        "avg_order_value": preserve_trusted_value(
            sales.get("avg_order_value"), source_ready=sales_detail_ready, previous=existing.get("avg_order_value")
        ),
        "items_per_order": preserve_trusted_value(
            sales.get("items_per_order"), source_ready=sales_detail_ready, previous=existing.get("items_per_order")
        ),
        "avg_discount_rate": preserve_trusted_value(
            sales.get("avg_discount_rate"), source_ready=sales_detail_ready, previous=existing.get("avg_discount_rate")
        ),
        "return_amount": return_amount,
        "return_rate": (
            return_amount / total_sales
            if total_sales and return_amount is not None
            else None
            if sales_detail_ready
            else existing.get("return_rate")
        ),
        "gross_profit": gross_profit,
        "gross_margin": (
            _optional_decimal(gross_profit) / total_sales
            if gross_profit is not None and total_sales else existing.get("gross_margin")
        ),
        "operating_profit_estimate": preserve_trusted_value(
            finance.get("operating_profit"),
            source_ready=finance_ready,
            previous=existing.get("operating_profit_estimate"),
        ),
        "total_inventory_amount": preserve_trusted_value(
            _decimal(inventory.get("total_amount")), source_ready=inventory_ready, previous=existing.get("total_inventory_amount")
        ),
        "inventory_total_qty": preserve_trusted_value(
            _decimal(inventory.get("total_qty")), source_ready=inventory_ready, previous=existing.get("inventory_total_qty")
        ),
        "inventory_age_unknown_qty": preserve_trusted_value(
            _decimal(inventory.get("age_unknown_qty")), source_ready=inventory_ready, previous=existing.get("inventory_age_unknown_qty")
        ),
        "inventory_age_unknown_amount": preserve_trusted_value(
            _decimal(inventory.get("age_unknown_amount")), source_ready=inventory_ready, previous=existing.get("inventory_age_unknown_amount")
        ),
        "age_90_plus_amount": preserve_trusted_value(
            _decimal(inventory.get("age_91_180_amount")) + _decimal(inventory.get("age_180_plus_amount")),
            source_ready=inventory_ready,
            previous=existing.get("age_90_plus_amount"),
        ),
        "age_180_plus_amount": preserve_trusted_value(
            _decimal(inventory.get("age_180_plus_amount")), source_ready=inventory_ready, previous=existing.get("age_180_plus_amount")
        ),
        "vip_balance": preserve_trusted_value(
            _decimal(members.get("vip_balance")), source_ready=member_ready, previous=existing.get("vip_balance")
        ),
        "vip_negative_balance_count": preserve_trusted_value(
            int(members.get("negative_count") or 0), source_ready=member_ready, previous=existing.get("vip_negative_balance_count")
        ),
        "vip_negative_balance_amount": preserve_trusted_value(
            _decimal(members.get("negative_amount")), source_ready=member_ready, previous=existing.get("vip_negative_balance_amount")
        ),
        "vip_sales_amount": vip_sales,
        "vip_sales_ratio": (
            vip_sales / total_sales
            if vip_sales is not None and total_sales else existing.get("vip_sales_ratio")
        ),
        "pending_task_count": int(tasks.get("pending") or 0),
        "overdue_task_count": int(tasks.get("overdue") or 0),
        "exception_count": int(risks.get("total") or 0) + int(warning_count),
        "major_exception_count": int(risks.get("major") or 0),
        "ai_summary": summary,
        "is_cost_complete": cost_complete,
        "is_finance_complete": finance_complete,
        "data_quality_status": "warning" if any(v != "ready" for v in metric_status.values()) else "normal",
        "source_freshness": json.dumps(source_freshness, ensure_ascii=False),
        "metric_status": json.dumps(metric_status, ensure_ascii=False),
    }
    await db.execute(text("""
        INSERT INTO dm.dm_boss_daily_report (
            report_date, total_sales, offline_sales, online_sales, net_sales,
            order_count, item_count, avg_order_value, items_per_order, avg_discount_rate,
            actual_pay_amount, return_amount, return_rate, gross_profit, gross_margin, operating_profit_estimate,
            total_inventory_amount, inventory_total_qty, age_90_plus_amount, age_180_plus_amount,
            inventory_age_unknown_qty, inventory_age_unknown_amount,
            vip_balance, vip_negative_balance_count, vip_negative_balance_amount, vip_sales_amount, vip_sales_ratio,
            pending_task_count, overdue_task_count, exception_count, major_exception_count,
            ai_summary, ai_model_used, is_cost_complete, is_finance_complete,
            data_quality_status, source_freshness, metric_status, generated_at, updated_at
        ) VALUES (
            :report_date, :total_sales, :offline_sales, :online_sales, :net_sales,
            :order_count, :item_count, :avg_order_value, :items_per_order, :avg_discount_rate,
            :actual_pay_amount, :return_amount, :return_rate, :gross_profit, :gross_margin, :operating_profit_estimate,
            :total_inventory_amount, :inventory_total_qty, :age_90_plus_amount, :age_180_plus_amount,
            :inventory_age_unknown_qty, :inventory_age_unknown_amount,
            :vip_balance, :vip_negative_balance_count, :vip_negative_balance_amount, :vip_sales_amount, :vip_sales_ratio,
            :pending_task_count, :overdue_task_count, :exception_count, :major_exception_count,
            :ai_summary, 'template', :is_cost_complete, :is_finance_complete,
            :data_quality_status, CAST(:source_freshness AS jsonb), CAST(:metric_status AS jsonb), now(), now()
        ) ON CONFLICT (report_date) DO UPDATE SET
            total_sales=EXCLUDED.total_sales, offline_sales=EXCLUDED.offline_sales,
            online_sales=EXCLUDED.online_sales, net_sales=EXCLUDED.net_sales, order_count=EXCLUDED.order_count,
            item_count=EXCLUDED.item_count, avg_order_value=EXCLUDED.avg_order_value,
            items_per_order=EXCLUDED.items_per_order, avg_discount_rate=EXCLUDED.avg_discount_rate,
            actual_pay_amount=EXCLUDED.actual_pay_amount, return_amount=EXCLUDED.return_amount,
            return_rate=EXCLUDED.return_rate, gross_profit=EXCLUDED.gross_profit,
            gross_margin=EXCLUDED.gross_margin, operating_profit_estimate=EXCLUDED.operating_profit_estimate,
            total_inventory_amount=EXCLUDED.total_inventory_amount,
            inventory_total_qty=EXCLUDED.inventory_total_qty, age_90_plus_amount=EXCLUDED.age_90_plus_amount,
            inventory_age_unknown_qty=EXCLUDED.inventory_age_unknown_qty,
            inventory_age_unknown_amount=EXCLUDED.inventory_age_unknown_amount,
            age_180_plus_amount=EXCLUDED.age_180_plus_amount, vip_balance=EXCLUDED.vip_balance,
            vip_negative_balance_count=EXCLUDED.vip_negative_balance_count,
            vip_negative_balance_amount=EXCLUDED.vip_negative_balance_amount,
            vip_sales_amount=EXCLUDED.vip_sales_amount, vip_sales_ratio=EXCLUDED.vip_sales_ratio,
            pending_task_count=EXCLUDED.pending_task_count, overdue_task_count=EXCLUDED.overdue_task_count,
            exception_count=EXCLUDED.exception_count, major_exception_count=EXCLUDED.major_exception_count,
            ai_summary=EXCLUDED.ai_summary, ai_model_used='template', is_cost_complete=EXCLUDED.is_cost_complete,
            is_finance_complete=EXCLUDED.is_finance_complete, data_quality_status=EXCLUDED.data_quality_status,
            source_freshness=EXCLUDED.source_freshness, metric_status=EXCLUDED.metric_status, updated_at=now()
    """), params)
    return await get_command_center_snapshot(db, report_date)


async def get_command_center_snapshot(db: AsyncSession, report_date: date) -> dict[str, Any]:
    row = (await db.execute(text("""
        SELECT * FROM dm.dm_boss_daily_report WHERE report_date=:report_date
    """), {"report_date": report_date})).mappings().first()
    if not row:
        return {"report_date": str(report_date), "available": False}
    data = dict(row)
    source_freshness = data.get("source_freshness") or {}
    statuses = data.get("metric_status") or {}
    cost_coverage = source_freshness.get("sales", {}).get("cost_coverage_rate")
    cost_reason = None
    if statuses.get("gross_profit") == "estimated" and cost_coverage is not None:
        cost_reason = f"成本覆盖率 {float(cost_coverage) * 100:.1f}%，当前指标为预估"
    metrics = {
        "sales": build_metric(data.get("total_sales"), source="baison_pos", as_of=report_date, status=statuses.get("sales")),
        "offline_sales": build_metric(data.get("offline_sales"), source="baison_payment", as_of=report_date, status=statuses.get("sales")),
        "actual_pay": build_metric(data.get("actual_pay_amount"), source="baison_payment", as_of=report_date, status=statuses.get("actual_pay")),
        "orders": build_metric(data.get("order_count"), source="baison_pos", as_of=report_date, status=statuses.get("sales_detail"), decimals=0),
        "items": build_metric(data.get("item_count"), source="baison_pos", as_of=report_date, status=statuses.get("sales_detail"), decimals=0),
        "avg_order_value": build_metric(data.get("avg_order_value"), source="baison_pos", as_of=report_date, status=statuses.get("sales_detail")),
        "items_per_order": build_metric(data.get("items_per_order"), source="baison_pos", as_of=report_date, status=statuses.get("sales_detail")),
        "avg_discount_rate": build_metric(data.get("avg_discount_rate"), source="baison_pos", as_of=report_date, status=statuses.get("sales_detail"), decimals=4),
        "return_amount": build_metric(data.get("return_amount"), source="baison_pos.refund_amount", as_of=report_date, status=statuses.get("returns")),
        "return_rate": build_metric(data.get("return_rate"), source="baison_pos.refund_amount", as_of=report_date, status=statuses.get("returns"), decimals=4),
        "major_exception_count": build_metric(data.get("major_exception_count"), source="rule_engine", as_of=report_date, status="ready", decimals=0),
        "pending_task_count": build_metric(data.get("pending_task_count"), source="action_task", as_of=report_date, status="ready", decimals=0),
        "gross_profit": build_metric(data.get("gross_profit"), source="baison_standard_purchase_price", as_of=report_date, status=statuses.get("gross_profit"), reason=cost_reason),
        "gross_margin": build_metric(data.get("gross_margin"), source="baison_standard_purchase_price", as_of=report_date, status=statuses.get("gross_margin"), reason=cost_reason, decimals=4),
        "inventory_amount": build_metric(data.get("total_inventory_amount"), source="apparel_inventory", as_of=source_freshness.get("inventory", {}).get("updated_at"), status=statuses.get("inventory")),
        "age_90_amount": build_metric(data.get("age_90_plus_amount"), source="fifo_inbound", as_of=source_freshness.get("inventory", {}).get("snapshot_date"), status=statuses.get("inventory")),
        "age_180_amount": build_metric(data.get("age_180_plus_amount"), source="fifo_inbound", as_of=source_freshness.get("inventory", {}).get("snapshot_date"), status=statuses.get("inventory")),
        "inventory_age_unknown_qty": build_metric(data.get("inventory_age_unknown_qty"), source="fifo_inbound", as_of=source_freshness.get("inventory", {}).get("snapshot_date"), status=statuses.get("inventory_age"), decimals=0),
        "vip_balance": build_metric(data.get("vip_balance"), source="baison_member.CZ_DQJE", as_of=source_freshness.get("member", {}).get("updated_at"), status=statuses.get("vip_balance")),
        "vip_negative_balance_amount": build_metric(data.get("vip_negative_balance_amount"), source="baison_member.CZ_DQJE", as_of=source_freshness.get("member", {}).get("updated_at"), status=statuses.get("vip_balance")),
        "vip_sales": build_metric(data.get("vip_sales_amount"), source="baison_pos", as_of=report_date, status=statuses.get("sales")),
        "online_sales": build_metric(data.get("online_sales"), source="baison_payment.011", as_of=report_date, status=statuses.get("online_sales")),
        "operating_profit": build_metric(
            data.get("operating_profit_estimate"),
            source="finance",
            as_of=source_freshness.get("finance", {}).get("updated_at"),
            status=statuses.get("operating_profit"),
            reason=source_freshness.get("finance", {}).get("reason"),
        ),
    }
    risks = (await db.execute(text("""
        SELECT id, exception_type, severity, store_code, product_code, sku_code,
               description, data_snapshot, is_converted_to_task, task_id
        FROM dm.dm_exception_audit
        WHERE audit_date=:report_date AND severity IN ('critical','risk')
        ORDER BY CASE severity WHEN 'critical' THEN 1 ELSE 2 END, id DESC LIMIT 8
    """), {"report_date": report_date})).mappings().all()
    inventory_snapshot_date = source_freshness.get("inventory", {}).get("snapshot_date")
    inventory_risks = []
    if inventory_snapshot_date:
        warning_rows = (await db.execute(text("""
            SELECT id, warning_type, warning_level, store_code, product_code, sku_code,
                   description, current_quantity, current_cost_amount, age_days,
                   sellable_days, is_converted_to_task, task_id
            FROM dm.dm_inventory_warning
            WHERE warning_date=:warning_date AND warning_level IN ('critical','risk')
            ORDER BY CASE warning_level WHEN 'critical' THEN 1 ELSE 2 END, id DESC
            LIMIT 8
        """), {"warning_date": date.fromisoformat(inventory_snapshot_date)})).mappings().all()
        inventory_risks = [{
            "id": item["id"],
            "exception_type": f"inventory_{item['warning_type']}",
            "severity": item["warning_level"],
            "store_code": item["store_code"],
            "product_code": item["product_code"],
            "sku_code": item["sku_code"],
            "description": item["description"],
            "data_snapshot": {
                "current_quantity": _json_value(item["current_quantity"]),
                "current_cost_amount": _json_value(item["current_cost_amount"]),
                "age_days": item["age_days"],
                "sellable_days": item["sellable_days"],
            },
            "is_converted_to_task": item["is_converted_to_task"],
            "task_id": item["task_id"],
        } for item in warning_rows]
    actions = (await db.execute(text("""
        SELECT id, task_no, title, status, priority, risk_level, assignee_name,
               assignee_role, due_date, related_store_code
        FROM app.app_action_task
        WHERE is_deleted=false AND status IN ('draft','pending','processing','overdue')
        ORDER BY CASE status WHEN 'overdue' THEN 1 WHEN 'pending' THEN 2 WHEN 'processing' THEN 3 ELSE 4 END,
                 due_date NULLS LAST, id DESC LIMIT 8
    """))).mappings().all()
    return {
        "available": True,
        "report_date": str(report_date),
        "generated_at": _json_value(data.get("updated_at") or data.get("generated_at")),
        "decision_summary": data.get("ai_summary") or "",
        "core_metrics": metrics,
        "major_risks": (inventory_risks + [dict(item) for item in risks])[:8],
        "today_actions": [dict(item) for item in actions],
        "data_quality": {
            "status": data.get("data_quality_status"),
            "cost_complete": bool(data.get("is_cost_complete")),
            "finance_complete": bool(data.get("is_finance_complete")),
            "source_freshness": source_freshness,
            "metric_status": statuses,
        },
    }


async def run_daily_command_center(
    db: AsyncSession,
    report_date: date,
    inventory_date: date,
    creator_id: int = 1,
) -> dict[str, Any]:
    locked = (await db.execute(text(
        "SELECT pg_try_advisory_xact_lock(hashtext('huabang_boss_command_center'))"
    ))).scalar()
    if not locked:
        return {"ok": True, "skipped": True, "reason": "another run is active"}

    age_result = await rebuild_inventory_age(db, inventory_date)
    warning_result = await rebuild_inventory_warnings(db, inventory_date)
    inventory_drafts = await create_inventory_warning_task_drafts(db, inventory_date, creator_id)
    await rebuild_confirmed_sales_dws(db, report_date)
    await build_boss_snapshot(db, report_date, inventory_date)

    from app.services.rule_engine import RuleEngine

    engine = RuleEngine()
    rule_result = await engine.run_all(str(report_date), db)
    persisted = await _persist_rule_results(db, report_date, rule_result.get("results", []))
    actionable = [
        item for item in rule_result.get("results", [])
        if item.get("triggered") and item.get("severity") in {"critical", "risk"}
    ]
    drafts = await engine.create_task_drafts(
        actionable, str(report_date), db, creator_id=creator_id, commit=False
    )
    await db.execute(text("""
        UPDATE dm.dm_exception_audit e
        SET is_converted_to_task=true, task_id=t.id
        FROM app.app_action_task t
        WHERE e.audit_date=:report_date
          AND t.source_type='rule' AND t.related_date=:report_date
          AND t.task_no LIKE 'DRAFT-' || UPPER(REPLACE(e.exception_type, 'rule_', '')) || '-%'
          AND t.related_store_code IS NOT DISTINCT FROM e.store_code
          AND t.is_deleted=false
    """), {"report_date": report_date})
    snapshot = await build_boss_snapshot(db, report_date, inventory_date)
    await db.commit()
    return {
        "ok": True,
        "skipped": False,
        "inventory_age": age_result,
        "inventory_warnings": warning_result,
        "rule_exception_count": persisted,
        "task_drafts_created": len(drafts) + len(inventory_drafts),
        "snapshot": snapshot,
    }
