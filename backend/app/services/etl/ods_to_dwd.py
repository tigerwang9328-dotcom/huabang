"""ODS → DWD 数据清洗"""
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from sqlalchemy import text
from app.core.standard_purchase_price import effective_sales_standard_cost_sql
from app.core.store_whitelist import ALLOWED_STORE_CODES


def _age_bucket(age_days_expr: str) -> str:
    return f"""
    CASE
        WHEN {age_days_expr} <= 30  THEN '0-30'
        WHEN {age_days_expr} <= 60  THEN '31-60'
        WHEN {age_days_expr} <= 90  THEN '61-90'
        WHEN {age_days_expr} <= 180 THEN '91-180'
        WHEN {age_days_expr} <= 365 THEN '181-365'
        ELSE '365+'
    END"""


class OdsToDwd:
    async def run(self, stat_date: str, db: AsyncSession, etl_log) -> dict:
        sales_rows = await self._clean_sales(stat_date, db, etl_log)
        return_rows = await self._clean_return(stat_date, db, etl_log)
        inventory_rows = await self._clean_inventory(stat_date, db, etl_log)
        return {"sales_rows": sales_rows, "return_rows": return_rows, "inventory_rows": inventory_rows}

    async def _clean_sales(self, stat_date: str, db: AsyncSession, etl_log) -> int:
        run_id = etl_log.start_task("ods_to_dwd_sales", stat_date)
        try:
            cost_amount_sql = effective_sales_standard_cost_sql(
                "product.supplier_code",
                "price.standard_purchase_price",
                "s.actual_amount",
                "s.quantity",
            )
            sql = text(f"""
                INSERT INTO dwd.dwd_sales_detail (
                    order_date, order_no, detail_no, store_code, channel,
                    product_code, sku_code, color, size, guide_id,
                    quantity, tag_price, actual_price, tag_amount, actual_amount,
                    cost_price, cost_amount, gross_profit, gross_margin, discount_rate,
                    is_cost_missing, is_discount_abnormal, is_member_sale
                )
                WITH source AS (
                    SELECT s.*,
                           {cost_amount_sql} AS standard_cost_amount
                    FROM ods.ods_baison_sales_detail s
                    LEFT JOIN LATERAL (
                        SELECT p.supplier_code
                        FROM dim.dim_product p
                        WHERE p.product_code = s.product_code
                          AND p.source_system = 'baison'
                        ORDER BY p.synced_at DESC NULLS LAST, p.id DESC
                        LIMIT 1
                    ) product ON true
                    LEFT JOIN LATERAL (
                        SELECT sp.standard_purchase_price
                        FROM dim.v_baison_sku_standard_purchase_price sp
                        WHERE sp.sku_code = s.sku_code
                        ORDER BY sp.synced_at DESC NULLS LAST
                        LIMIT 1
                    ) price ON true
                    WHERE s.order_date = :stat_date
                      AND s.quantity > 0
                      AND COALESCE(s.actual_amount, 0) >= 0
                      AND s.store_code = ANY(:store_codes)
                )
                SELECT
                    s.order_date,
                    s.order_no,
                    s.detail_no,
                    s.store_code,
                    COALESCE(s.channel, 'offline'),
                    s.product_code,
                    s.sku_code,
                    s.color,
                    s.size,
                    s.guide_id,
                    s.quantity,
                    s.tag_price,
                    s.actual_price,
                    s.tag_amount,
                    s.actual_amount,
                    s.standard_cost_amount / NULLIF(s.quantity, 0) AS cost_price,
                    s.standard_cost_amount AS cost_amount,
                    CASE WHEN s.standard_cost_amount IS NOT NULL
                         THEN s.actual_amount - s.standard_cost_amount END AS gross_profit,
                    CASE
                        WHEN COALESCE(s.actual_amount, 0) = 0
                          OR s.standard_cost_amount IS NULL THEN NULL
                        ELSE (s.actual_amount - s.standard_cost_amount) / s.actual_amount
                    END AS gross_margin,
                    s.discount_rate,
                    s.standard_cost_amount IS NULL AS is_cost_missing,
                    CASE WHEN COALESCE(s.discount_rate, 0) > 0.5 THEN TRUE ELSE FALSE END AS is_discount_abnormal,
                    FALSE AS is_member_sale
                FROM source s
                ON CONFLICT (detail_no) DO UPDATE SET
                    order_date        = EXCLUDED.order_date,
                    store_code        = EXCLUDED.store_code,
                    quantity          = EXCLUDED.quantity,
                    actual_amount     = EXCLUDED.actual_amount,
                    cost_price       = EXCLUDED.cost_price,
                    cost_amount       = EXCLUDED.cost_amount,
                    gross_profit      = EXCLUDED.gross_profit,
                    gross_margin      = EXCLUDED.gross_margin,
                    is_cost_missing   = EXCLUDED.is_cost_missing
            """)
            result = await db.execute(sql, {
                "stat_date": date.fromisoformat(stat_date),
                "store_codes": sorted(ALLOWED_STORE_CODES),
            })
            await db.commit()
            n = result.rowcount if result.rowcount >= 0 else 0
            etl_log.finish_task(run_id, output_rows=n)
            return n
        except Exception as exc:
            await db.rollback()
            etl_log.fail_task(run_id, str(exc))
            print(f"[OdsToDwd] sales 失败: {exc}")
            return 0

    async def _clean_return(self, stat_date: str, db: AsyncSession, etl_log) -> int:
        run_id = etl_log.start_task("ods_to_dwd_return", stat_date)
        try:
            cost_amount_sql = effective_sales_standard_cost_sql(
                "product.supplier_code",
                "price.standard_purchase_price",
                "r.actual_amount",
                "r.quantity",
            )
            sql = text(f"""
                INSERT INTO dwd.dwd_return_detail (
                    return_date, return_no, detail_no, store_code, channel,
                    product_code, sku_code, quantity, actual_amount,
                    cost_price, cost_amount, is_abnormal
                )
                WITH source AS (
                    SELECT r.*,
                           {cost_amount_sql} AS standard_cost_amount
                    FROM ods.ods_baison_return_detail r
                    LEFT JOIN LATERAL (
                        SELECT p.supplier_code
                        FROM dim.dim_product p
                        WHERE p.product_code = r.product_code
                          AND p.source_system = 'baison'
                        ORDER BY p.synced_at DESC NULLS LAST, p.id DESC
                        LIMIT 1
                    ) product ON true
                    LEFT JOIN LATERAL (
                        SELECT sp.standard_purchase_price
                        FROM dim.v_baison_sku_standard_purchase_price sp
                        WHERE sp.sku_code = r.sku_code
                        ORDER BY sp.synced_at DESC NULLS LAST
                        LIMIT 1
                    ) price ON true
                    WHERE r.return_date = :stat_date
                      AND r.quantity > 0
                      AND r.store_code = ANY(:store_codes)
                )
                SELECT
                    r.return_date,
                    r.return_no,
                    r.detail_no,
                    r.store_code,
                    COALESCE(r.channel, 'offline'),
                    r.product_code,
                    r.sku_code,
                    r.quantity,
                    r.actual_amount,
                    r.standard_cost_amount / NULLIF(r.quantity, 0) AS cost_price,
                    r.standard_cost_amount AS cost_amount,
                    FALSE AS is_abnormal
                FROM source r
                ON CONFLICT (detail_no) DO UPDATE SET
                    return_date    = EXCLUDED.return_date,
                    store_code     = EXCLUDED.store_code,
                    quantity       = EXCLUDED.quantity,
                    actual_amount  = EXCLUDED.actual_amount,
                    cost_price     = EXCLUDED.cost_price,
                    cost_amount    = EXCLUDED.cost_amount
            """)
            result = await db.execute(sql, {
                "stat_date": date.fromisoformat(stat_date),
                "store_codes": sorted(ALLOWED_STORE_CODES),
            })
            await db.commit()
            n = result.rowcount if result.rowcount >= 0 else 0
            etl_log.finish_task(run_id, output_rows=n)
            return n
        except Exception as exc:
            await db.rollback()
            etl_log.fail_task(run_id, str(exc))
            print(f"[OdsToDwd] return 失败: {exc}")
            return 0

    async def _clean_inventory(self, stat_date: str, db: AsyncSession, etl_log) -> int:
        run_id = etl_log.start_task("ods_to_dwd_inventory", stat_date)
        try:
            sql = text(f"""
                INSERT INTO dwd.dwd_inventory_snapshot (
                    snapshot_date, store_code, product_code, sku_code,
                    color, size, quantity, cost_price, cost_amount,
                    age_days, age_bucket, is_negative, is_cost_missing
                )
                SELECT
                    i.snapshot_date,
                    i.store_code,
                    i.product_code,
                    i.sku_code,
                    i.color,
                    i.size,
                    i.quantity,
                    sp.standard_purchase_price AS cost_price,
                    CASE WHEN sp.standard_purchase_price IS NOT NULL
                         THEN i.quantity * sp.standard_purchase_price
                         ELSE NULL
                    END AS cost_amount,
                    COALESCE(i.age_days, 0) AS age_days,
                    {_age_bucket('COALESCE(i.age_days,0)')} AS age_bucket,
                    CASE WHEN COALESCE(i.quantity, 0) < 0 THEN TRUE ELSE FALSE END AS is_negative,
                    CASE WHEN sp.standard_purchase_price IS NULL THEN TRUE ELSE FALSE END AS is_cost_missing
                FROM ods.ods_baison_inventory i
                LEFT JOIN dim.v_baison_sku_standard_purchase_price sp
                  ON sp.sku_code = i.sku_code
                WHERE i.snapshot_date = :stat_date
                ON CONFLICT (snapshot_date, store_code, sku_code) DO UPDATE SET
                    quantity       = EXCLUDED.quantity,
                    cost_amount    = EXCLUDED.cost_amount,
                    age_days       = EXCLUDED.age_days,
                    age_bucket     = EXCLUDED.age_bucket,
                    is_negative    = EXCLUDED.is_negative,
                    is_cost_missing = EXCLUDED.is_cost_missing
            """)
            result = await db.execute(sql, {"stat_date": date.fromisoformat(stat_date)})
            await db.commit()
            n = result.rowcount if result.rowcount >= 0 else 0
            etl_log.finish_task(run_id, output_rows=n)
            return n
        except Exception as exc:
            await db.rollback()
            etl_log.fail_task(run_id, str(exc))
            print(f"[OdsToDwd] inventory 失败: {exc}")
            return 0
