"""VIP sales analysis from Baison POS tickets and stored-value logs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _metric(value: Any, source: str = "baison_pos", status: str = "ready", reason: str | None = None) -> dict[str, Any]:
    result = {"value": value, "status": status, "source": source}
    if reason:
        result["reason"] = reason
    return result


def _pending(reason: str) -> dict[str, Any]:
    return _metric(None, status="pending_data", source="pending", reason=reason)


def build_vip_sales_summary(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    total_sales = _num(row.get("total_sales"))
    vip_sales = _num(row.get("vip_sales"))
    vip_actual = _num(row.get("vip_actual"))
    vip_standard = _num(row.get("vip_standard"))
    vip_orders = int(row.get("vip_orders") or 0)
    vip_qty = _num(row.get("vip_qty"))
    vip_members = int(row.get("vip_members") or 0)
    repeat_members = int(row.get("repeat_members") or 0)
    return_amount = _num(row.get("return_amount"))
    return_orders = int(row.get("return_orders") or 0)
    recharge_members = int(row.get("recharge_members") or 0)
    converted_members = int(row.get("converted_members") or 0)
    return {
        "vip_sales_amount": _metric(round(vip_sales, 2)),
        "vip_sales_ratio": _metric(round(vip_sales / total_sales, 4) if total_sales else 0),
        "vip_actual_amount": _metric(round(vip_actual, 2)),
        "order_count": _metric(vip_orders),
        "sales_quantity": _metric(round(vip_qty, 2)),
        "avg_order_value": _metric(round(vip_sales / vip_orders, 2) if vip_orders else 0),
        "attachment_rate": _metric(round(vip_qty / vip_orders, 2) if vip_orders else 0),
        "vip_member_count": _metric(vip_members),
        "repurchase_member_count": _metric(repeat_members),
        "repurchase_rate": _metric(round(repeat_members / vip_members, 4) if vip_members else 0),
        "avg_discount_rate": _metric(round(vip_sales / vip_standard, 4) if vip_standard else 0),
        "return_amount": _metric(round(return_amount, 2)),
        "return_order_count": _metric(return_orders),
        "return_rate": _metric(round(return_amount / vip_sales, 4) if vip_sales else 0),
        "recharge_member_count": _metric(recharge_members, source="baison_deposit"),
        "recharge_consume_member_count": _metric(converted_members, source="baison_deposit"),
        "recharge_consume_conversion_rate": _metric(
            round(converted_members / recharge_members, 4) if recharge_members else 0,
            source="baison_deposit",
        ),
        "gross_profit": _pending("VIP小票与商品成本明细尚无可靠逐单关联"),
        "gross_margin": _pending("VIP小票与商品成本明细尚无可靠逐单关联"),
        "category_analysis": _pending("商品销售明细暂不能可靠关联VIP小票"),
        "style_analysis": _pending("商品销售明细暂不能可靠关联VIP小票"),
    }


def _decorate_group(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    for key in ("vip_sales", "vip_actual", "vip_qty", "vip_standard", "return_amount"):
        item[key] = round(_num(item.get(key)), 2)
    item["vip_orders"] = int(item.get("vip_orders") or 0)
    item["avg_order_value"] = round(item["vip_sales"] / item["vip_orders"], 2) if item["vip_orders"] else 0
    item["attachment_rate"] = round(item["vip_qty"] / item["vip_orders"], 2) if item["vip_orders"] else 0
    item["avg_discount_rate"] = round(item["vip_sales"] / item["vip_standard"], 4) if item["vip_standard"] else 0
    item["return_rate"] = round(item["return_amount"] / item["vip_sales"], 4) if item["vip_sales"] else 0
    return item


async def get_vip_sales_analysis(
    db: AsyncSession,
    start_date: date,
    end_date: date,
    store_codes: list[str],
) -> dict[str, Any]:
    if start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期")
    params = {"start_date": start_date, "end_date": end_date, "store_codes": store_codes}
    ticket_base = """
        WITH ticket_base AS (
            SELECT t.biz_date, t.ticket_no, t.store_code,
                   COALESCE(s.store_name,t.store_name,t.store_code) store_name,
                   NULLIF(BTRIM(COALESCE(NULLIF(t.vip_code::text,''),
                                          NULLIF(t.customer_code::text,''),'')),'') member_key,
                   COALESCE(t.sales_amount,0) sales_amount,
                   COALESCE(t.actual_pay_amount,0) actual_pay_amount,
                   COALESCE(t.sales_qty,0) sales_qty,
                   COALESCE(t.standard_amount,0) standard_amount,
                   t.synced_at
            FROM dwd.dwd_pos_ticket t
            LEFT JOIN dim.dim_store s ON s.store_code=t.store_code AND s.source_system='baison'
            WHERE t.biz_date BETWEEN :start_date AND :end_date
              AND t.store_code=ANY(:store_codes)
              AND COALESCE(t.is_void,false)=false
              AND COALESCE(t.is_pending,false)=false
        )
    """
    summary = (await db.execute(text(ticket_base + """
        , member_stats AS (
            SELECT member_key, COUNT(*) FILTER (WHERE sales_amount>0) order_count
            FROM ticket_base WHERE member_key IS NOT NULL GROUP BY member_key
        )
        SELECT COALESCE(SUM(sales_amount),0) total_sales,
               COALESCE(SUM(sales_amount) FILTER (WHERE member_key IS NOT NULL),0) vip_sales,
               COALESCE(SUM(actual_pay_amount) FILTER (WHERE member_key IS NOT NULL),0) vip_actual,
               COUNT(*) FILTER (WHERE member_key IS NOT NULL AND sales_amount>0) vip_orders,
               COALESCE(SUM(GREATEST(sales_qty,0)) FILTER (WHERE member_key IS NOT NULL),0) vip_qty,
               COUNT(DISTINCT member_key) FILTER (WHERE member_key IS NOT NULL AND sales_amount>0) vip_members,
               COALESCE(SUM(GREATEST(standard_amount,0)) FILTER (WHERE member_key IS NOT NULL AND sales_amount>0),0) vip_standard,
               COALESCE(SUM(ABS(sales_amount)) FILTER (WHERE member_key IS NOT NULL AND sales_amount<0),0) return_amount,
               COUNT(*) FILTER (WHERE member_key IS NOT NULL AND sales_amount<0) return_orders,
               (SELECT COUNT(*) FROM member_stats WHERE order_count>=2) repeat_members,
               MAX(synced_at) updated_at
        FROM ticket_base
    """), params)).mappings().one()
    deposit = (await db.execute(text("""
        WITH recharge AS (
            SELECT DISTINCT member_no
            FROM dwd.dwd_baison_member_deposit_log
            WHERE biz_date BETWEEN :start_date AND :end_date
              AND UPPER(store_code)=ANY(:store_codes) AND change_type='0'
        ), consumed AS (
            SELECT DISTINCT member_no
            FROM dwd.dwd_baison_member_deposit_log
            WHERE biz_date BETWEEN :start_date AND :end_date
              AND UPPER(store_code)=ANY(:store_codes) AND change_type='2'
        )
        SELECT COUNT(*) recharge_members,
               COUNT(*) FILTER (WHERE c.member_no IS NOT NULL) converted_members
        FROM recharge r LEFT JOIN consumed c ON c.member_no=r.member_no
    """), params)).mappings().one()
    summary_row = {**dict(summary), **dict(deposit)}

    group_select = """
        SELECT {dimension},
               COALESCE(SUM(sales_amount) FILTER (WHERE member_key IS NOT NULL),0) vip_sales,
               COALESCE(SUM(actual_pay_amount) FILTER (WHERE member_key IS NOT NULL),0) vip_actual,
               COUNT(*) FILTER (WHERE member_key IS NOT NULL AND sales_amount>0) vip_orders,
               COALESCE(SUM(GREATEST(sales_qty,0)) FILTER (WHERE member_key IS NOT NULL),0) vip_qty,
               COALESCE(SUM(GREATEST(standard_amount,0)) FILTER (WHERE member_key IS NOT NULL AND sales_amount>0),0) vip_standard,
               COALESCE(SUM(ABS(sales_amount)) FILTER (WHERE member_key IS NOT NULL AND sales_amount<0),0) return_amount
        FROM ticket_base
        GROUP BY {group_by}
        ORDER BY {order_by}
    """
    stores = (await db.execute(text(ticket_base + group_select.format(
        dimension="store_code, MAX(store_name) store_name",
        group_by="store_code",
        order_by="vip_sales DESC, store_code",
    )), params)).mappings().all()
    trend = (await db.execute(text(ticket_base + group_select.format(
        dimension="biz_date",
        group_by="biz_date",
        order_by="biz_date",
    )), params)).mappings().all()
    return {
        "date_range": {"start_date": str(start_date), "end_date": str(end_date)},
        "summary": build_vip_sales_summary(summary_row),
        "stores": [_decorate_group(dict(row)) for row in stores],
        "trend": [_decorate_group(dict(row)) for row in trend],
        "pending_dimensions": ["gross_profit", "gross_margin", "category_analysis", "style_analysis"],
        "sources": {
            "sales": {"name": "baison_pos", "updated_at": str(summary.get("updated_at") or "")},
            "deposit": {"name": "baison_deposit"},
        },
    }
