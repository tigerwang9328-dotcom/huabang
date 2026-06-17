"""指标计算服务：24个核心经营指标（纯查询，不修改数据）"""
from datetime import date, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


def safe_div(a, b, default=None):
    if b is None or b == 0:
        return default
    return a / b if a is not None else default


class MetricsService:
    async def get_daily_metrics(self, stat_date: str, db: AsyncSession, store_code: Optional[str] = None) -> dict:
        """获取指定日期的全量经营指标"""
        d = date.fromisoformat(stat_date)
        prev_day = (d - timedelta(days=1)).isoformat()
        prev_week = (d - timedelta(days=7)).isoformat()

        sales = await self._sales_metrics(stat_date, prev_day, prev_week, db, store_code)
        inventory = await self._inventory_metrics(stat_date, db, store_code)
        finance = await self._finance_metrics(stat_date, db, store_code)
        task_metrics = await self._task_metrics(db)

        return {
            "stat_date": stat_date,
            "store_code": store_code,
            "is_cost_complete": sales.get("is_cost_complete", False),
            "data_tip": None if sales.get("is_cost_complete") else "成本数据不完整，毛利率为预估值",
            **sales,
            **inventory,
            **finance,
            **task_metrics,
        }

    async def _sales_metrics(self, stat_date, prev_day, prev_week, db, store_code):
        where = "WHERE stat_date = :d"
        params = {"d": date.fromisoformat(stat_date)}
        if store_code:
            where += " AND store_code = :sc"
            params["sc"] = store_code

        r = await db.execute(text(f"""
            SELECT
                SUM(sales_amount) AS total_sales,
                SUM(net_sales_amount) AS net_sales,
                SUM(return_amount) AS return_amount,
                SUM(order_count) AS order_count,
                SUM(item_count) AS item_count,
                CASE WHEN SUM(sales_amount) = 0 THEN NULL
                     ELSE SUM(return_amount) / SUM(sales_amount) END AS return_rate,
                CASE WHEN SUM(order_count) = 0 THEN NULL
                     ELSE SUM(net_sales_amount) / SUM(order_count) END AS avg_order_value,
                CASE WHEN SUM(order_count) = 0 THEN NULL
                     ELSE SUM(item_count)::numeric / SUM(order_count) END AS items_per_order,
                AVG(avg_discount_rate) AS avg_discount_rate,
                SUM(gross_profit) AS gross_profit,
                CASE WHEN SUM(sales_amount) = 0 THEN NULL
                     ELSE SUM(gross_profit) / SUM(sales_amount) END AS gross_margin,
                BOOL_AND(is_cost_complete) AS is_cost_complete
            FROM dws.dws_store_daily {where}
        """), params)
        row = r.fetchone()

        # 昨日/上周同期对比
        prev_r = await db.execute(text(f"""
            SELECT SUM(sales_amount), SUM(net_sales_amount), SUM(order_count)
            FROM dws.dws_store_daily WHERE stat_date = :pd {' AND store_code = :sc' if store_code else ''}
        """), {"pd": date.fromisoformat(prev_day), **({"sc": store_code} if store_code else {})})
        prev_row = prev_r.fetchone()

        week_r = await db.execute(text(f"""
            SELECT SUM(sales_amount) FROM dws.dws_store_daily
            WHERE stat_date = :pw {' AND store_code = :sc' if store_code else ''}
        """), {"pw": date.fromisoformat(prev_week), **({"sc": store_code} if store_code else {})})
        week_row = week_r.fetchone()

        total_sales = float(row[0] or 0) if row else 0
        prev_sales = float(prev_row[0] or 0) if prev_row and prev_row[0] else 0
        week_sales = float(week_row[0] or 0) if week_row and week_row[0] else 0

        return {
            "total_sales": total_sales,
            "net_sales": float(row[1] or 0) if row else 0,
            "return_amount": float(row[2] or 0) if row else 0,
            "order_count": int(row[3] or 0) if row else 0,
            "item_count": int(row[4] or 0) if row else 0,
            "return_rate": float(row[5] or 0) if row and row[5] else 0,
            "avg_order_value": float(row[6] or 0) if row and row[6] else 0,
            "items_per_order": float(row[7] or 0) if row and row[7] else 0,
            "avg_discount_rate": float(row[8] or 0) if row and row[8] else 0,
            "gross_profit": float(row[9] or 0) if row else 0,
            "gross_margin": float(row[10] or 0) if row and row[10] else 0,
            "is_cost_complete": bool(row[11]) if row and row[11] is not None else False,
            "wow_growth": safe_div(total_sales - week_sales, week_sales, 0),
            "dod_growth": safe_div(total_sales - prev_sales, prev_sales, 0),
        }

    async def _inventory_metrics(self, stat_date, db, store_code):
        where = "WHERE stat_date = :d"
        params = {"d": date.fromisoformat(stat_date)}
        if store_code:
            where += " AND store_code = :sc"
            params["sc"] = store_code

        r = await db.execute(text(f"""
            SELECT
                SUM(total_cost_amount) AS total_inventory,
                SUM(age_91_180_amount + age_180_plus_amount) AS age_90_plus,
                SUM(age_180_plus_amount) AS age_180_plus,
                CASE WHEN SUM(total_cost_amount) = 0 THEN NULL
                     ELSE SUM(age_91_180_amount + age_180_plus_amount) / SUM(total_cost_amount)
                END AS age_90_plus_rate,
                SUM(negative_sku_count) AS negative_sku_count,
                SUM(sku_count) AS total_sku_count,
                BOOL_AND(is_cost_complete) AS is_cost_complete
            FROM dws.dws_inventory_daily {where}
        """), params)
        row = r.fetchone()
        if not row or row[0] is None:
            return {"total_inventory": 0, "age_90_plus_inventory": 0, "age_90_plus_rate": 0,
                    "age_180_plus_inventory": 0, "negative_sku_count": 0, "total_sku_count": 0}

        total_inv = float(row[0] or 0)
        net_sales_r = await db.execute(text(f"""
            SELECT SUM(net_sales_amount) / 30.0
            FROM dws.dws_store_daily
            WHERE stat_date BETWEEN :start AND :end
            {' AND store_code = :sc' if store_code else ''}
        """), {
            "start": date.fromisoformat(stat_date) - timedelta(days=30),
            "end": date.fromisoformat(stat_date),
            **({"sc": store_code} if store_code else {})
        })
        daily_sales = float(net_sales_r.scalar() or 0)

        cost_ratio_r = await db.execute(text(f"""
            SELECT AVG(cost_amount / NULLIF(sales_amount, 0))
            FROM dws.dws_store_daily
            WHERE stat_date BETWEEN :start AND :end
            {' AND store_code = :sc' if store_code else ''}
        """), {
            "start": date.fromisoformat(stat_date) - timedelta(days=30),
            "end": date.fromisoformat(stat_date),
            **({"sc": store_code} if store_code else {})
        })
        cost_ratio = float(cost_ratio_r.scalar() or 0.6)
        daily_cost_of_sales = daily_sales * cost_ratio
        sell_through_days = int(safe_div(total_inv, daily_cost_of_sales, 9999))

        return {
            "total_inventory": total_inv,
            "age_90_plus_inventory": float(row[1] or 0),
            "age_180_plus_inventory": float(row[2] or 0),
            "age_90_plus_rate": float(row[3] or 0),
            "negative_sku_count": int(row[4] or 0),
            "total_sku_count": int(row[5] or 0),
            "sell_through_days": sell_through_days,
        }

    async def _finance_metrics(self, stat_date, db, store_code):
        cash_r = await db.execute(text("""
            SELECT COALESCE(SUM(balance), 0) FROM dwd.dwd_finance_cash
            WHERE record_date <= :d
        """), {"d": date.fromisoformat(stat_date)})
        total_cash = float(cash_r.scalar() or 0)

        expense_r = await db.execute(text("""
            SELECT COALESCE(SUM(expense_amount)/30.0, 0)
            FROM dwd.dwd_finance_expense
            WHERE expense_date BETWEEN :start AND :end
        """), {
            "start": date.fromisoformat(stat_date) - timedelta(days=30),
            "end": date.fromisoformat(stat_date),
        })
        daily_expense = float(expense_r.scalar() or 0)
        cash_safety_days = int(safe_div(total_cash, daily_expense, 9999))

        profit_r = await db.execute(text("""
            SELECT operating_profit, data_type
            FROM dm.dm_finance_profit_daily
            WHERE stat_date = :d AND store_code = 'ALL'
            LIMIT 1
        """), {"d": date.fromisoformat(stat_date)})
        prow = profit_r.fetchone()

        return {
            "total_cash": total_cash,
            "daily_avg_expense": daily_expense,
            "cash_safety_days": cash_safety_days,
            "operating_profit_estimate": float(prow[0] or 0) if prow else 0,
            "finance_data_type": prow[1] if prow else "no_data",
            "cash_risk_level": "critical" if cash_safety_days < 15 else ("warning" if cash_safety_days < 30 else "safe"),
        }

    async def _task_metrics(self, db):
        r = await db.execute(text("""
            SELECT
                COUNT(CASE WHEN status = 'pending' THEN 1 END) AS pending_count,
                COUNT(CASE WHEN status = 'overdue' THEN 1 END) AS overdue_count,
                COUNT(CASE WHEN status = 'processing' THEN 1 END) AS processing_count
            FROM app.app_action_task WHERE is_deleted = FALSE
        """))
        row = r.fetchone()
        return {
            "pending_task_count": int(row[0] or 0) if row else 0,
            "overdue_task_count": int(row[1] or 0) if row else 0,
            "processing_task_count": int(row[2] or 0) if row else 0,
        }

    async def get_store_ranking(self, stat_date: str, db: AsyncSession, limit: int = 10) -> list:
        r = await db.execute(text("""
            SELECT store_code, net_sales_amount, gross_profit, gross_margin,
                   order_count, avg_order_value, is_cost_complete
            FROM dws.dws_store_daily
            WHERE stat_date = :d AND channel = 'offline'
            ORDER BY net_sales_amount DESC
            LIMIT :limit
        """), {"d": date.fromisoformat(stat_date), "limit": limit})
        return [
            {"rank": i + 1, "store_code": row[0], "net_sales": float(row[1] or 0),
             "gross_profit": float(row[2] or 0), "gross_margin": float(row[3] or 0),
             "order_count": int(row[4] or 0), "avg_order_value": float(row[5] or 0),
             "is_cost_complete": bool(row[6])}
            for i, row in enumerate(r.fetchall())
        ]

    async def get_product_ranking(self, stat_date: str, db: AsyncSession, limit: int = 10) -> list:
        r = await db.execute(text("""
            SELECT product_code, SUM(net_sales_amount) AS total_net_sales,
                   SUM(net_quantity) AS total_qty, SUM(gross_profit) AS total_gp
            FROM dws.dws_product_daily
            WHERE stat_date = :d
            GROUP BY product_code
            ORDER BY total_net_sales DESC
            LIMIT :limit
        """), {"d": date.fromisoformat(stat_date), "limit": limit})
        return [
            {"rank": i + 1, "product_code": row[0], "net_sales": float(row[1] or 0),
             "qty": int(row[2] or 0), "gross_profit": float(row[3] or 0)}
            for i, row in enumerate(r.fetchall())
        ]
