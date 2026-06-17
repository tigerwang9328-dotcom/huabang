"""DWD → DWS 汇总聚合"""
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from sqlalchemy import text


class DwdToDws:
    async def run(self, stat_date: str, db: AsyncSession, etl_log) -> dict:
        store_rows = await self._agg_store_daily(stat_date, db, etl_log)
        company_rows = await self._agg_company_daily(stat_date, db, etl_log)
        product_rows = await self._agg_product_daily(stat_date, db, etl_log)
        inventory_rows = await self._agg_inventory_daily(stat_date, db, etl_log)
        finance_rows = await self._agg_finance_daily(stat_date, db, etl_log)
        return {
            "store_daily_rows": store_rows,
            "company_daily_rows": company_rows,
            "product_daily_rows": product_rows,
            "inventory_daily_rows": inventory_rows,
            "finance_daily_rows": finance_rows,
        }

    async def _agg_store_daily(self, stat_date: str, db: AsyncSession, etl_log) -> int:
        run_id = etl_log.start_task("dwd_to_dws_store_daily", stat_date)
        try:
            sql = text("""
                INSERT INTO dws.dws_store_daily (
                    stat_date, store_code, channel,
                    order_count, item_count, return_count, net_item_count,
                    tag_amount, sales_amount, return_amount, net_sales_amount,
                    cost_amount, gross_profit, gross_margin,
                    avg_order_value, items_per_order, avg_discount_rate,
                    member_sales_amount, member_order_count, member_ratio,
                    is_cost_complete
                )
                SELECT
                    CAST(:stat_date AS DATE) AS stat_date,
                    s.store_code,
                    s.channel,
                    COUNT(DISTINCT s.order_no) AS order_count,
                    SUM(s.quantity) AS item_count,
                    COALESCE(r.return_count, 0) AS return_count,
                    SUM(s.quantity) - COALESCE(r.return_qty, 0) AS net_item_count,
                    COALESCE(SUM(s.tag_amount), 0) AS tag_amount,
                    COALESCE(SUM(s.actual_amount), 0) AS sales_amount,
                    COALESCE(r.return_amount, 0) AS return_amount,
                    COALESCE(SUM(s.actual_amount), 0) - COALESCE(r.return_amount, 0) AS net_sales_amount,
                    COALESCE(SUM(s.cost_amount), 0) AS cost_amount,
                    COALESCE(SUM(s.gross_profit), 0) AS gross_profit,
                    CASE
                        WHEN COALESCE(SUM(s.actual_amount), 0) = 0 THEN NULL
                        ELSE COALESCE(SUM(s.gross_profit), 0) / SUM(s.actual_amount)
                    END AS gross_margin,
                    CASE
                        WHEN COUNT(DISTINCT s.order_no) = 0 THEN NULL
                        ELSE (COALESCE(SUM(s.actual_amount), 0) - COALESCE(r.return_amount, 0))
                             / COUNT(DISTINCT s.order_no)
                    END AS avg_order_value,
                    CASE
                        WHEN COUNT(DISTINCT s.order_no) = 0 THEN NULL
                        ELSE COALESCE(SUM(s.quantity), 0)::numeric / COUNT(DISTINCT s.order_no)
                    END AS items_per_order,
                    AVG(COALESCE(s.discount_rate, 0)) AS avg_discount_rate,
                    0 AS member_sales_amount,
                    0 AS member_order_count,
                    0 AS member_ratio,
                    CASE WHEN COUNT(CASE WHEN s.is_cost_missing THEN 1 END) = 0 THEN TRUE ELSE FALSE END AS is_cost_complete
                FROM dwd.dwd_sales_detail s
                LEFT JOIN (
                    SELECT store_code, channel,
                           COUNT(*) AS return_count,
                           SUM(quantity) AS return_qty,
                           SUM(actual_amount) AS return_amount
                    FROM dwd.dwd_return_detail
                    WHERE return_date = :stat_date
                    GROUP BY store_code, channel
                ) r ON s.store_code = r.store_code AND s.channel = r.channel
                WHERE s.order_date = :stat_date
                GROUP BY s.store_code, s.channel, r.return_count, r.return_qty, r.return_amount
                ON CONFLICT (stat_date, store_code, channel) DO UPDATE SET
                    order_count         = EXCLUDED.order_count,
                    item_count          = EXCLUDED.item_count,
                    sales_amount        = EXCLUDED.sales_amount,
                    return_amount       = EXCLUDED.return_amount,
                    net_sales_amount    = EXCLUDED.net_sales_amount,
                    cost_amount         = EXCLUDED.cost_amount,
                    gross_profit        = EXCLUDED.gross_profit,
                    gross_margin        = EXCLUDED.gross_margin,
                    avg_order_value     = EXCLUDED.avg_order_value,
                    items_per_order     = EXCLUDED.items_per_order,
                    is_cost_complete    = EXCLUDED.is_cost_complete,
                    etl_at              = NOW()
            """)
            result = await db.execute(sql, {"stat_date": date.fromisoformat(stat_date)})
            await db.commit()
            n = result.rowcount if result.rowcount >= 0 else 0
            etl_log.finish_task(run_id, output_rows=n)
            return n
        except Exception as exc:
            await db.rollback()
            etl_log.fail_task(run_id, str(exc))
            print(f"[DwdToDws] store_daily 失败: {exc}")
            return 0

    async def _agg_company_daily(self, stat_date: str, db: AsyncSession, etl_log) -> int:
        run_id = etl_log.start_task("dwd_to_dws_company_daily", stat_date)
        try:
            sql = text("""
                INSERT INTO dws.dws_company_daily (
                    stat_date, total_sales_amount, offline_sales_amount, online_sales_amount,
                    online_ratio, total_order_count, total_item_count, total_return_amount,
                    net_sales_amount, total_cost_amount, gross_profit, gross_margin,
                    avg_order_value, items_per_order, avg_discount_rate,
                    active_store_count, is_cost_complete
                )
                SELECT
                    CAST(:stat_date AS DATE),
                    SUM(sales_amount),
                    SUM(CASE WHEN channel = 'offline' THEN sales_amount ELSE 0 END),
                    SUM(CASE WHEN channel != 'offline' THEN sales_amount ELSE 0 END),
                    CASE WHEN SUM(sales_amount) = 0 THEN 0
                         ELSE SUM(CASE WHEN channel != 'offline' THEN sales_amount ELSE 0 END) / SUM(sales_amount)
                    END,
                    SUM(order_count),
                    SUM(item_count),
                    SUM(return_amount),
                    SUM(net_sales_amount),
                    SUM(cost_amount),
                    SUM(gross_profit),
                    CASE WHEN SUM(sales_amount) = 0 THEN NULL
                         ELSE SUM(gross_profit) / SUM(sales_amount)
                    END,
                    CASE WHEN SUM(order_count) = 0 THEN NULL
                         ELSE SUM(net_sales_amount) / SUM(order_count)
                    END,
                    CASE WHEN SUM(order_count) = 0 THEN NULL
                         ELSE SUM(item_count)::numeric / SUM(order_count)
                    END,
                    AVG(avg_discount_rate),
                    COUNT(DISTINCT store_code),
                    BOOL_AND(is_cost_complete)
                FROM dws.dws_store_daily
                WHERE stat_date = :stat_date
                ON CONFLICT (stat_date) DO UPDATE SET
                    total_sales_amount   = EXCLUDED.total_sales_amount,
                    net_sales_amount     = EXCLUDED.net_sales_amount,
                    total_order_count    = EXCLUDED.total_order_count,
                    gross_profit         = EXCLUDED.gross_profit,
                    gross_margin         = EXCLUDED.gross_margin,
                    is_cost_complete     = EXCLUDED.is_cost_complete,
                    etl_at               = NOW()
            """)
            result = await db.execute(sql, {"stat_date": date.fromisoformat(stat_date)})
            await db.commit()
            n = result.rowcount if result.rowcount >= 0 else 0
            etl_log.finish_task(run_id, output_rows=n)
            return n
        except Exception as exc:
            await db.rollback()
            etl_log.fail_task(run_id, str(exc))
            print(f"[DwdToDws] company_daily 失败: {exc}")
            return 0

    async def _agg_product_daily(self, stat_date: str, db: AsyncSession, etl_log) -> int:
        run_id = etl_log.start_task("dwd_to_dws_product_daily", stat_date)
        try:
            sql = text("""
                INSERT INTO dws.dws_product_daily (
                    stat_date, product_code, store_code,
                    sales_quantity, return_quantity, net_quantity,
                    sales_amount, return_amount, net_sales_amount,
                    cost_amount, gross_profit, gross_margin, avg_discount_rate,
                    is_cost_complete
                )
                SELECT
                    CAST(:stat_date AS DATE),
                    s.product_code,
                    s.store_code,
                    SUM(s.quantity) AS sales_quantity,
                    COALESCE(r.return_qty, 0) AS return_quantity,
                    SUM(s.quantity) - COALESCE(r.return_qty, 0) AS net_quantity,
                    SUM(s.actual_amount) AS sales_amount,
                    COALESCE(r.return_amount, 0) AS return_amount,
                    SUM(s.actual_amount) - COALESCE(r.return_amount, 0) AS net_sales_amount,
                    SUM(s.cost_amount) AS cost_amount,
                    SUM(s.gross_profit) AS gross_profit,
                    CASE WHEN SUM(s.actual_amount) = 0 THEN NULL
                         ELSE SUM(s.gross_profit) / SUM(s.actual_amount)
                    END AS gross_margin,
                    AVG(s.discount_rate) AS avg_discount_rate,
                    CASE WHEN COUNT(CASE WHEN s.is_cost_missing THEN 1 END) = 0 THEN TRUE ELSE FALSE END
                FROM dwd.dwd_sales_detail s
                LEFT JOIN (
                    SELECT product_code, store_code,
                           SUM(quantity) AS return_qty,
                           SUM(actual_amount) AS return_amount
                    FROM dwd.dwd_return_detail
                    WHERE return_date = :stat_date
                    GROUP BY product_code, store_code
                ) r ON s.product_code = r.product_code AND s.store_code = r.store_code
                WHERE s.order_date = :stat_date
                  AND s.product_code IS NOT NULL
                GROUP BY s.product_code, s.store_code, r.return_qty, r.return_amount
                ON CONFLICT (stat_date, product_code, store_code) DO UPDATE SET
                    sales_quantity   = EXCLUDED.sales_quantity,
                    net_quantity     = EXCLUDED.net_quantity,
                    sales_amount     = EXCLUDED.sales_amount,
                    gross_profit     = EXCLUDED.gross_profit,
                    gross_margin     = EXCLUDED.gross_margin,
                    is_cost_complete = EXCLUDED.is_cost_complete,
                    etl_at           = NOW()
            """)
            result = await db.execute(sql, {"stat_date": date.fromisoformat(stat_date)})
            await db.commit()
            n = result.rowcount if result.rowcount >= 0 else 0
            etl_log.finish_task(run_id, output_rows=n)
            return n
        except Exception as exc:
            await db.rollback()
            etl_log.fail_task(run_id, str(exc))
            print(f"[DwdToDws] product_daily 失败: {exc}")
            return 0

    async def _agg_inventory_daily(self, stat_date: str, db: AsyncSession, etl_log) -> int:
        run_id = etl_log.start_task("dwd_to_dws_inventory_daily", stat_date)
        try:
            sql = text("""
                INSERT INTO dws.dws_inventory_daily (
                    stat_date, store_code,
                    total_quantity, total_cost_amount,
                    age_0_30_amount, age_31_60_amount, age_61_90_amount,
                    age_91_180_amount, age_180_plus_amount,
                    negative_sku_count, sku_count, is_cost_complete
                )
                SELECT
                    CAST(:stat_date AS DATE),
                    store_code,
                    SUM(quantity),
                    SUM(cost_amount),
                    SUM(CASE WHEN age_bucket = '0-30'  THEN cost_amount ELSE 0 END),
                    SUM(CASE WHEN age_bucket = '31-60' THEN cost_amount ELSE 0 END),
                    SUM(CASE WHEN age_bucket = '61-90' THEN cost_amount ELSE 0 END),
                    SUM(CASE WHEN age_bucket IN ('91-180') THEN cost_amount ELSE 0 END),
                    SUM(CASE WHEN age_bucket IN ('181-365','365+') THEN cost_amount ELSE 0 END),
                    COUNT(CASE WHEN is_negative THEN 1 END),
                    COUNT(*),
                    BOOL_AND(NOT is_cost_missing)
                FROM dwd.dwd_inventory_snapshot
                WHERE snapshot_date = :stat_date
                GROUP BY store_code
                ON CONFLICT (stat_date, store_code) DO UPDATE SET
                    total_quantity      = EXCLUDED.total_quantity,
                    total_cost_amount   = EXCLUDED.total_cost_amount,
                    age_91_180_amount   = EXCLUDED.age_91_180_amount,
                    age_180_plus_amount = EXCLUDED.age_180_plus_amount,
                    negative_sku_count  = EXCLUDED.negative_sku_count,
                    sku_count           = EXCLUDED.sku_count,
                    is_cost_complete    = EXCLUDED.is_cost_complete,
                    etl_at              = NOW()
            """)
            result = await db.execute(sql, {"stat_date": date.fromisoformat(stat_date)})
            await db.commit()
            n = result.rowcount if result.rowcount >= 0 else 0
            etl_log.finish_task(run_id, output_rows=n)
            return n
        except Exception as exc:
            await db.rollback()
            etl_log.fail_task(run_id, str(exc))
            print(f"[DwdToDws] inventory_daily 失败: {exc}")
            return 0

    async def _agg_finance_daily(self, stat_date: str, db: AsyncSession, etl_log) -> int:
        run_id = etl_log.start_task("dwd_to_dws_finance_daily", stat_date)
        try:
            sql = text("""
                INSERT INTO dws.dws_finance_daily (
                    stat_date, store_code,
                    net_sales_amount, cost_amount, gross_profit, gross_margin,
                    total_expense, rent_expense, labor_expense, utilities_expense,
                    logistics_expense, admin_expense, other_expense,
                    operating_profit_estimate, data_type, is_profit_complete
                )
                SELECT
                    CAST(:stat_date AS DATE),
                    COALESCE(e.store_code, 'ALL') AS store_code,
                    COALESCE(sd.net_sales_amount, 0) AS net_sales_amount,
                    COALESCE(sd.cost_amount, 0) AS cost_amount,
                    COALESCE(sd.gross_profit, 0) AS gross_profit,
                    sd.gross_margin,
                    COALESCE(SUM(e.expense_amount), 0) AS total_expense,
                    SUM(CASE WHEN e.expense_type = 'rent'      THEN e.expense_amount ELSE 0 END),
                    SUM(CASE WHEN e.expense_type = 'labor'     THEN e.expense_amount ELSE 0 END),
                    SUM(CASE WHEN e.expense_type = 'utilities' THEN e.expense_amount ELSE 0 END),
                    SUM(CASE WHEN e.expense_type = 'logistics' THEN e.expense_amount ELSE 0 END),
                    SUM(CASE WHEN e.expense_type = 'admin'     THEN e.expense_amount ELSE 0 END),
                    SUM(CASE WHEN e.expense_type NOT IN ('rent','labor','utilities','logistics','admin') THEN e.expense_amount ELSE 0 END),
                    COALESCE(sd.gross_profit, 0) - COALESCE(SUM(e.expense_amount), 0) AS operating_profit_estimate,
                    COALESCE(MAX(e.data_type), 'estimate') AS data_type,
                    CASE WHEN COUNT(e.id) > 0 THEN TRUE ELSE FALSE END AS is_profit_complete
                FROM dwd.dwd_finance_expense e
                LEFT JOIN (
                    SELECT SUM(net_sales_amount) AS net_sales_amount,
                           SUM(cost_amount) AS cost_amount,
                           SUM(gross_profit) AS gross_profit,
                           CASE WHEN SUM(sales_amount) = 0 THEN NULL
                                ELSE SUM(gross_profit) / SUM(sales_amount) END AS gross_margin
                    FROM dws.dws_store_daily
                    WHERE stat_date = :stat_date
                ) sd ON TRUE
                WHERE e.expense_date = :stat_date
                GROUP BY e.store_code, sd.net_sales_amount, sd.cost_amount, sd.gross_profit, sd.gross_margin
                ON CONFLICT (stat_date, store_code) DO UPDATE SET
                    total_expense               = EXCLUDED.total_expense,
                    operating_profit_estimate   = EXCLUDED.operating_profit_estimate,
                    data_type                   = EXCLUDED.data_type,
                    etl_at                      = NOW()
            """)
            result = await db.execute(sql, {"stat_date": date.fromisoformat(stat_date)})
            await db.commit()
            n = result.rowcount if result.rowcount >= 0 else 0
            etl_log.finish_task(run_id, output_rows=n)
            return n
        except Exception as exc:
            await db.rollback()
            etl_log.fail_task(run_id, str(exc))
            print(f"[DwdToDws] finance_daily 失败: {exc}")
            return 0
