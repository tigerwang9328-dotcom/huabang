"""Shared Baison POS payment formula for sales and actual receipts."""

from datetime import date
from decimal import Decimal
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.store_whitelist import ALLOWED_STORE_CODES


SALES_PAYMENT_CODES = ("000", "003", "004", "011", "666", "971")
ACTUAL_RECEIPT_PAYMENT_CODES = ("000", "011", "666", "971")
ONLINE_PAYMENT_CODE = "011"


def summarize_payment_rows(
    rows: Iterable[tuple[str, Decimal | int | float | str]],
    *,
    recharge_amount: Decimal | int | float | str = 0,
) -> dict[str, Decimal]:
    """Apply the confirmed sales and receipt formula to payment rows."""
    sales = Decimal("0")
    offline = Decimal("0")
    online = Decimal("0")
    receipts = Decimal(str(recharge_amount or 0))
    refunds = Decimal("0")

    for raw_code, raw_amount in rows:
        code = str(raw_code or "").strip()
        amount = Decimal(str(raw_amount or 0))
        if code not in SALES_PAYMENT_CODES:
            continue
        if amount > 0:
            sales += amount
            if code == ONLINE_PAYMENT_CODE:
                online += amount
            else:
                offline += amount
            if code in ACTUAL_RECEIPT_PAYMENT_CODES:
                receipts += amount
        elif amount < 0:
            receipts += amount
            refunds += -amount

    return {
        "sales_amount": sales,
        "offline_sales_amount": offline,
        "online_sales_amount": online,
        "actual_pay_amount": receipts,
        "refund_amount": refunds,
    }


def _sql_codes(codes: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{code}'" for code in codes) + ")"


PAY_DETAIL_SQL = f"""
    SELECT t.ticket_no,
           SUM(CASE
                 WHEN p->>'jsdm' IN {_sql_codes(SALES_PAYMENT_CODES)}
                  AND COALESCE(NULLIF(p->>'je','')::numeric, 0) > 0
                 THEN COALESCE(NULLIF(p->>'je','')::numeric, 0)
                 ELSE 0
               END) AS sales_amount,
           SUM(CASE
                 WHEN p->>'jsdm' IN {_sql_codes(tuple(code for code in SALES_PAYMENT_CODES if code != ONLINE_PAYMENT_CODE))}
                  AND COALESCE(NULLIF(p->>'je','')::numeric, 0) > 0
                 THEN COALESCE(NULLIF(p->>'je','')::numeric, 0)
                 ELSE 0
               END) AS offline_sales_amount,
           SUM(CASE
                 WHEN p->>'jsdm' = '{ONLINE_PAYMENT_CODE}'
                  AND COALESCE(NULLIF(p->>'je','')::numeric, 0) > 0
                 THEN COALESCE(NULLIF(p->>'je','')::numeric, 0)
                 ELSE 0
               END) AS online_sales_amount,
           SUM(CASE
                 WHEN p->>'jsdm' IN {_sql_codes(ACTUAL_RECEIPT_PAYMENT_CODES)}
                  AND COALESCE(NULLIF(p->>'je','')::numeric, 0) > 0
                 THEN COALESCE(NULLIF(p->>'je','')::numeric, 0)
                 ELSE 0
               END)
           + SUM(CASE
                   WHEN p->>'jsdm' IN {_sql_codes(SALES_PAYMENT_CODES)}
                    AND COALESCE(NULLIF(p->>'je','')::numeric, 0) < 0
                   THEN COALESCE(NULLIF(p->>'je','')::numeric, 0)
                   ELSE 0
                 END) AS actual_pay_amount,
           -SUM(CASE
                  WHEN p->>'jsdm' IN {_sql_codes(SALES_PAYMENT_CODES)}
                   AND COALESCE(NULLIF(p->>'je','')::numeric, 0) < 0
                  THEN COALESCE(NULLIF(p->>'je','')::numeric, 0)
                  ELSE 0
                END) AS refund_amount
    FROM dwd.dwd_pos_ticket t
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(t.raw_data->'qtlsdjs_mx') = 'array' THEN t.raw_data->'qtlsdjs_mx'
            ELSE '[]'::jsonb
        END
    ) p
    WHERE t.biz_date >= CAST(:sd AS date) AND t.biz_date <= CAST(:ed AS date)
      AND t.store_code = ANY(:store_codes)
      AND COALESCE(t.is_void, false) = false
      AND COALESCE(t.is_pending, false) = false
    GROUP BY t.ticket_no
"""

RETURN_SYNC_COMPLETE_SQL = """
    SELECT COALESCE((
        SELECT r.status='success'
               AND r.biz_start_time <= CAST(:stat_date AS date)
               AND r.biz_end_time >= CAST(:stat_date AS date) + INTERVAL '1 day' - INTERVAL '1 second'
        FROM ods.ods_baison_pos_ticket_sync_run r
        WHERE r.biz_start_time < CAST(:stat_date AS date) + INTERVAL '1 day'
          AND r.biz_end_time >= CAST(:stat_date AS date)
        ORDER BY r.started_at DESC, r.id DESC
        LIMIT 1
    ), false)
"""


async def has_complete_pos_ticket_sync(db: AsyncSession, stat_date: date) -> bool:
    result = await db.execute(text(RETURN_SYNC_COMPLETE_SQL), {"stat_date": stat_date})
    return bool(result.scalar())


async def rebuild_confirmed_sales_dws(db: AsyncSession, stat_date: date) -> bool:
    """Recalculate DWS sales fields with the confirmed Baison payment formula."""
    if not await has_complete_pos_ticket_sync(db, stat_date):
        return False
    params = {
        "sd": stat_date,
        "ed": stat_date,
        "stat_date": stat_date,
        "store_codes": sorted(ALLOWED_STORE_CODES),
    }
    await db.execute(text(f"""
        WITH pay AS ({PAY_DETAIL_SQL}), stores AS (
            SELECT UNNEST(CAST(:store_codes AS text[])) AS store_code
        ), ticket_daily AS (
            SELECT t.store_code,
                   COALESCE(SUM(COALESCE(pay.sales_amount, t.sales_amount)), 0) AS sales_amount,
                   COALESCE(SUM(COALESCE(pay.refund_amount, 0)), 0) AS return_amount
            FROM dwd.dwd_pos_ticket t
            LEFT JOIN pay ON pay.ticket_no=t.ticket_no
            WHERE t.biz_date=:stat_date
              AND t.store_code=ANY(:store_codes)
              AND COALESCE(t.is_void,false)=false
              AND COALESCE(t.is_pending,false)=false
            GROUP BY t.store_code
        ), daily AS (
            SELECT s.store_code, COALESCE(t.sales_amount, 0) AS sales_amount,
                   COALESCE(t.return_amount, 0) AS return_amount
            FROM stores s LEFT JOIN ticket_daily t USING (store_code)
        )
        UPDATE dws.dws_store_daily d
        SET sales_amount=x.sales_amount,
            return_amount=x.return_amount,
            net_sales_amount=x.sales_amount-x.return_amount,
            avg_order_value=CASE WHEN d.order_count>0 THEN x.sales_amount/d.order_count ELSE 0 END,
            gross_profit=x.sales_amount-COALESCE(d.cost_amount,0),
            gross_margin=CASE
                WHEN x.sales_amount<>0
                THEN (x.sales_amount-COALESCE(d.cost_amount,0))/x.sales_amount
                ELSE NULL
            END,
            etl_at=now()
        FROM daily x
        WHERE d.stat_date=:stat_date AND d.store_code=x.store_code AND d.channel='offline'
    """), params)
    await db.execute(text(f"""
        WITH pay AS ({PAY_DETAIL_SQL}), channels AS (
            SELECT COALESCE(SUM(COALESCE(pay.offline_sales_amount, t.sales_amount)), 0)
                       AS offline_sales_amount,
                   COALESCE(SUM(COALESCE(pay.online_sales_amount, 0)), 0)
                       AS online_sales_amount,
                   COALESCE(SUM(COALESCE(pay.refund_amount, 0)), 0)
                       AS return_amount
            FROM dwd.dwd_pos_ticket t
            LEFT JOIN pay ON pay.ticket_no=t.ticket_no
            WHERE t.biz_date=:stat_date
              AND t.store_code=ANY(:store_codes)
              AND COALESCE(t.is_void,false)=false
              AND COALESCE(t.is_pending,false)=false
        ), company AS (
            SELECT COALESCE(SUM(sales_amount),0) AS sales_amount,
                   COALESCE(SUM(net_sales_amount),0) AS net_sales_amount,
                   COALESCE(SUM(cost_amount),0) AS cost_amount,
                   COALESCE(SUM(order_count),0) AS order_count,
                   COUNT(*) FILTER (WHERE sales_amount>0) AS active_store_count,
                   BOOL_AND(is_cost_complete) AS is_cost_complete
            FROM dws.dws_store_daily
            WHERE stat_date=:stat_date AND store_code=ANY(:store_codes) AND channel='offline'
        ), company_with_channels AS (
            SELECT company.*, channels.offline_sales_amount, channels.online_sales_amount,
                   channels.return_amount
            FROM company CROSS JOIN channels
        )
        UPDATE dws.dws_company_daily d
        SET total_sales_amount=x.sales_amount,
            offline_sales_amount=x.offline_sales_amount,
            online_sales_amount=x.online_sales_amount,
            online_ratio=CASE WHEN x.sales_amount<>0
                THEN x.online_sales_amount/x.sales_amount ELSE NULL END,
            total_return_amount=x.return_amount,
            net_sales_amount=x.net_sales_amount,
            total_cost_amount=x.cost_amount,
            gross_profit=x.sales_amount-x.cost_amount,
            gross_margin=CASE
                WHEN x.sales_amount<>0
                THEN (x.sales_amount-x.cost_amount)/x.sales_amount
                ELSE NULL
            END,
            avg_order_value=CASE WHEN x.order_count>0 THEN x.sales_amount/x.order_count ELSE 0 END,
            active_store_count=x.active_store_count,
            is_cost_complete=COALESCE(x.is_cost_complete,false),
            etl_at=now()
        FROM company_with_channels x
        WHERE d.stat_date=:stat_date
    """), params)
    return True
