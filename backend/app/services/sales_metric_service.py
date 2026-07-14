"""Shared Baison POS payment formula for sales and actual receipts."""

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.store_whitelist import ALLOWED_STORE_CODES


PAY_DETAIL_SQL = """
    SELECT t.ticket_no,
           SUM(CASE
                 WHEN p->>'jsdm' IN ('000', '003', '004', '011', '666', '971')
                  AND COALESCE(NULLIF(p->>'je','')::numeric, 0) > 0
                 THEN COALESCE(NULLIF(p->>'je','')::numeric, 0)
                 ELSE 0
               END) AS sales_amount,
           SUM(CASE
                 WHEN p->>'jsdm' IN ('000', '003', '004', '666', '971')
                  AND COALESCE(NULLIF(p->>'je','')::numeric, 0) > 0
                 THEN COALESCE(NULLIF(p->>'je','')::numeric, 0)
                 ELSE 0
               END) AS offline_sales_amount,
           SUM(CASE
                 WHEN p->>'jsdm' = '011'
                  AND COALESCE(NULLIF(p->>'je','')::numeric, 0) > 0
                 THEN COALESCE(NULLIF(p->>'je','')::numeric, 0)
                 ELSE 0
               END) AS online_sales_amount,
           SUM(CASE
                 WHEN p->>'jsdm' IN ('000', '011', '666', '971')
                  AND COALESCE(NULLIF(p->>'je','')::numeric, 0) > 0
                 THEN COALESCE(NULLIF(p->>'je','')::numeric, 0)
                 ELSE 0
               END)
           + SUM(CASE
                   WHEN p->>'jsdm' IN ('000', '003', '004', '011', '666', '971')
                    AND COALESCE(NULLIF(p->>'je','')::numeric, 0) < 0
                   THEN COALESCE(NULLIF(p->>'je','')::numeric, 0)
                   ELSE 0
                 END) AS actual_pay_amount,
           -SUM(CASE
                  WHEN p->>'jsdm' IN ('000', '003', '004', '011', '666', '971')
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


async def rebuild_confirmed_sales_dws(db: AsyncSession, stat_date: date) -> None:
    """Recalculate DWS sales fields with the confirmed Baison payment formula."""
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
                   COALESCE(SUM(COALESCE(pay.sales_amount, t.sales_amount)), 0) AS sales_amount
            FROM dwd.dwd_pos_ticket t
            LEFT JOIN pay ON pay.ticket_no=t.ticket_no
            WHERE t.biz_date=:stat_date
              AND t.store_code=ANY(:store_codes)
              AND COALESCE(t.is_void,false)=false
              AND COALESCE(t.is_pending,false)=false
            GROUP BY t.store_code
        ), daily AS (
            SELECT s.store_code, COALESCE(t.sales_amount, 0) AS sales_amount
            FROM stores s LEFT JOIN ticket_daily t USING (store_code)
        )
        UPDATE dws.dws_store_daily d
        SET sales_amount=x.sales_amount,
            net_sales_amount=x.sales_amount-COALESCE(d.return_amount,0),
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
                       AS online_sales_amount
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
            SELECT company.*, channels.offline_sales_amount, channels.online_sales_amount
            FROM company CROSS JOIN channels
        )
        UPDATE dws.dws_company_daily d
        SET total_sales_amount=x.sales_amount,
            offline_sales_amount=x.offline_sales_amount,
            online_sales_amount=x.online_sales_amount,
            online_ratio=CASE WHEN x.sales_amount<>0
                THEN x.online_sales_amount/x.sales_amount ELSE NULL END,
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
