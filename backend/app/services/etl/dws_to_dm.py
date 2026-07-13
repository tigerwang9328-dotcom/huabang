"""DWS → DM 集市层生成"""
import json
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class DwsToDm:
    async def run(self, stat_date: str, db: AsyncSession, etl_log) -> dict:
        boss_rows = await self._boss_daily_report(stat_date, db, etl_log)
        diag_rows = await self._store_diagnosis(stat_date, db, etl_log)
        warn_rows = await self._inventory_warnings(stat_date, db, etl_log)
        repl_rows = await self._replenishment_advice(stat_date, db, etl_log)
        fin_rows  = await self._finance_profit(stat_date, db, etl_log)
        return {
            "boss_report_rows": boss_rows,
            "store_diagnosis_rows": diag_rows,
            "inventory_warning_rows": warn_rows,
            "replenishment_rows": repl_rows,
            "finance_profit_rows": fin_rows,
        }

    async def _boss_daily_report(self, stat_date: str, db: AsyncSession, etl_log) -> int:
        run_id = etl_log.start_task("dws_to_dm_boss_report", stat_date)
        try:
            r = await db.execute(text("""
                SELECT
                    total_sales_amount, offline_sales_amount, online_sales_amount, online_ratio,
                    net_sales_amount, total_order_count, total_item_count,
                    avg_order_value, items_per_order, avg_discount_rate,
                    gross_profit, gross_margin, total_cost_amount, is_cost_complete
                FROM dws.dws_company_daily WHERE stat_date = :d
            """), {"d": date.fromisoformat(stat_date)})
            row = r.fetchone()
            if not row:
                etl_log.finish_task(run_id, output_rows=0)
                return 0

            # 门店排行 top3/bottom3
            stores_r = await db.execute(text("""
                SELECT store_code, net_sales_amount
                FROM dws.dws_store_daily
                WHERE stat_date = :d
                ORDER BY net_sales_amount DESC
                LIMIT 10
            """), {"d": date.fromisoformat(stat_date)})
            stores = [{"store": r2[0], "amount": float(r2[1] or 0)} for r2 in stores_r.fetchall()]
            top_stores = stores[:3]
            bottom_stores = stores[-3:] if len(stores) >= 3 else stores

            # 库存预警数
            warn_r = await db.execute(text("SELECT COUNT(*) FROM dm.dm_inventory_warning WHERE warning_date = :d"), {"d": date.fromisoformat(stat_date)})
            exception_count = warn_r.scalar() or 0

            # 现金余额
            cash_r = await db.execute(text("""
                SELECT SUM(balance) FROM dwd.dwd_finance_cash WHERE record_date <= :d
            """), {"d": date.fromisoformat(stat_date)})
            cash_balance = float(cash_r.scalar() or 0)

            # 近30天日均支出
            thirty_days_ago = date.fromisoformat(stat_date) - timedelta(days=30)
            expense_r = await db.execute(text("""
                SELECT COALESCE(SUM(expense_amount)/30.0, 0)
                FROM dwd.dwd_finance_expense
                WHERE expense_date BETWEEN :start AND :end
            """), {"start": thirty_days_ago, "end": date.fromisoformat(stat_date)})
            daily_avg_expense = float(expense_r.scalar() or 0)
            cash_safety_days = int(cash_balance / daily_avg_expense) if daily_avg_expense > 0 else 9999

            # 库存90天+
            inv_r = await db.execute(text("""
                SELECT COALESCE(SUM(age_91_180_amount + age_180_plus_amount), 0),
                       COALESCE(SUM(age_180_plus_amount), 0),
                       COALESCE(SUM(total_cost_amount), 0)
                FROM dws.dws_inventory_daily WHERE stat_date = :d
            """), {"d": date.fromisoformat(stat_date)})
            inv_row = inv_r.fetchone()
            age_90_plus = float(inv_row[0] or 0) if inv_row else 0
            age_180_plus = float(inv_row[1] or 0) if inv_row else 0
            total_inventory = float(inv_row[2] or 0) if inv_row else 0

            await db.execute(text("""
                INSERT INTO dm.dm_boss_daily_report (
                    report_date, total_sales, offline_sales, online_sales, online_ratio,
                    net_sales, order_count, item_count, avg_order_value, items_per_order,
                    avg_discount_rate, gross_profit, gross_margin,
                    cash_balance, cash_safety_days,
                    total_inventory_amount, age_90_plus_amount, age_180_plus_amount,
                    exception_count, is_cost_complete, generated_at
                ) VALUES (
                    :report_date, :total_sales, :offline, :online, :online_ratio,
                    :net_sales, :order_count, :item_count, :avg_order, :items_per_order,
                    :avg_discount, :gross_profit, :gross_margin,
                    :cash_balance, :cash_safety_days,
                    :total_inventory, :age_90_plus, :age_180_plus,
                    :exception_count, :is_cost_complete, NOW()
                )
                ON CONFLICT (report_date) DO UPDATE SET
                    total_sales         = EXCLUDED.total_sales,
                    offline_sales       = EXCLUDED.offline_sales,
                    online_sales        = EXCLUDED.online_sales,
                    online_ratio        = EXCLUDED.online_ratio,
                    net_sales           = EXCLUDED.net_sales,
                    order_count         = EXCLUDED.order_count,
                    item_count          = EXCLUDED.item_count,
                    avg_order_value     = EXCLUDED.avg_order_value,
                    items_per_order     = EXCLUDED.items_per_order,
                    avg_discount_rate   = EXCLUDED.avg_discount_rate,
                    gross_profit        = EXCLUDED.gross_profit,
                    gross_margin        = EXCLUDED.gross_margin,
                    cash_balance        = EXCLUDED.cash_balance,
                    total_inventory_amount = EXCLUDED.total_inventory_amount,
                    age_90_plus_amount  = EXCLUDED.age_90_plus_amount,
                    age_180_plus_amount = EXCLUDED.age_180_plus_amount,
                    cash_safety_days    = EXCLUDED.cash_safety_days,
                    exception_count     = EXCLUDED.exception_count,
                    is_cost_complete    = EXCLUDED.is_cost_complete,
                    generated_at        = NOW()
            """), {
                "report_date": date.fromisoformat(stat_date),
                "total_sales": float(row[0] or 0),
                "offline": float(row[1] or 0),
                "online": float(row[2] or 0),
                "online_ratio": float(row[3] or 0),
                "net_sales": float(row[4] or 0),
                "order_count": int(row[5] or 0),
                "item_count": int(row[6] or 0),
                "avg_order": float(row[7] or 0),
                "items_per_order": float(row[8] or 0),
                "avg_discount": float(row[9] or 0),
                "gross_profit": float(row[10] or 0),
                "gross_margin": float(row[11] or 0),
                "cash_balance": cash_balance,
                "cash_safety_days": cash_safety_days,
                "total_inventory": total_inventory,
                "age_90_plus": age_90_plus,
                "age_180_plus": age_180_plus,
                "exception_count": exception_count,
                "is_cost_complete": bool(row[13]),
            })
            await db.commit()
            etl_log.finish_task(run_id, output_rows=1)
            return 1
        except Exception as exc:
            await db.rollback()
            etl_log.fail_task(run_id, str(exc))
            print(f"[DwsToDm] boss_report 失败: {exc}")
            return 0

    async def _store_diagnosis(self, stat_date: str, db: AsyncSession, etl_log) -> int:
        run_id = etl_log.start_task("dws_to_dm_store_diag", stat_date)
        try:
            stores_r = await db.execute(text("""
                SELECT sd.store_code, sd.sales_amount, sd.net_sales_amount,
                       sd.gross_profit, sd.gross_margin, sd.order_count, sd.item_count,
                       sd.avg_order_value, sd.items_per_order, sd.avg_discount_rate,
                       sd.is_cost_complete,
                       id.total_cost_amount, id.age_91_180_amount, id.age_180_plus_amount, id.negative_sku_count
                FROM dws.dws_store_daily sd
                LEFT JOIN dws.dws_inventory_daily id
                    ON sd.store_code = id.store_code AND id.stat_date = sd.stat_date
                WHERE sd.stat_date = :d
            """), {"d": date.fromisoformat(stat_date)})
            rows = stores_r.fetchall()
            if not rows:
                etl_log.finish_task(run_id, output_rows=0)
                return 0

            count = 0
            for row in rows:
                store_code = row[0]
                issues = []
                level = "normal"
                if float(row[1] or 0) < 5000:
                    issues.append("日销售额低于5000元")
                    level = "warning"
                if row[4] and float(row[4]) < 0.1:
                    issues.append("毛利率低于10%")
                    level = "warning"
                if row[13] and float(row[13]) > 50000:
                    issues.append(f"180天以上滞销库存{float(row[13]):.0f}元")
                    level = "risk"
                if row[14] and int(row[14]) > 0:
                    issues.append(f"存在{row[14]}个负库存SKU")
                    level = "risk"
                if float(row[7] or 0) < 100:
                    issues.append("客单价低于100元")

                await db.execute(text("""
                    INSERT INTO dm.dm_store_diagnosis (
                        diagnosis_date, store_code, sales_amount,
                        avg_order_value, items_per_order, avg_discount_rate,
                        total_inventory_amount, age_90_plus_amount, negative_sku_count,
                        diagnosis_level, issues, is_cost_complete, generated_at
                    ) VALUES (
                        :d, :sc, :sa, :ao, :ipo, :adr, :inv, :age90, :neg, :level, :issues, :cost_ok, NOW()
                    )
                    ON CONFLICT (diagnosis_date, store_code) DO UPDATE SET
                        sales_amount        = EXCLUDED.sales_amount,
                        diagnosis_level     = EXCLUDED.diagnosis_level,
                        issues              = EXCLUDED.issues,
                        generated_at        = NOW()
                """), {
                    "d": date.fromisoformat(stat_date), "sc": store_code,
                    "sa": float(row[1] or 0),
                    "ao": float(row[7] or 0),
                    "ipo": float(row[8] or 0),
                    "adr": float(row[9] or 0),
                    "inv": float(row[11] or 0),
                    "age90": float((row[12] or 0) + (row[13] or 0)),
                    "neg": int(row[14] or 0),
                    "level": level,
                    "issues": json.dumps(issues, ensure_ascii=False),
                    "cost_ok": bool(row[10]),
                })
                count += 1
            await db.commit()
            etl_log.finish_task(run_id, output_rows=count)
            return count
        except Exception as exc:
            await db.rollback()
            etl_log.fail_task(run_id, str(exc))
            print(f"[DwsToDm] store_diag 失败: {exc}")
            return 0

    async def _inventory_warnings(self, stat_date: str, db: AsyncSession, etl_log) -> int:
        run_id = etl_log.start_task("dws_to_dm_inv_warning", stat_date)
        try:
            inv_r = await db.execute(text("""
                SELECT store_code, product_code, sku_code, quantity, cost_amount, age_days, age_bucket
                FROM dwd.v_apparel_inventory_snapshot
                WHERE snapshot_date = :d
                  AND (quantity < 0 OR age_days > 90 OR cost_amount > 50000)
                LIMIT 500
            """), {"d": date.fromisoformat(stat_date)})
            rows = inv_r.fetchall()
            count = 0
            for row in rows:
                sc, pc, sku, qty, cost, age, bucket = row
                if qty is not None and int(qty) < 0:
                    wtype, level, desc = "negative_qty", "critical", f"SKU库存为负数({qty})"
                elif age and int(age) > 180:
                    wtype, level, desc = "overstock", "high", f"库存滞压{age}天，金额{cost:.0f}元"
                elif age and int(age) > 90:
                    wtype, level, desc = "overstock", "medium", f"库存滞压{age}天，金额{cost:.0f}元"
                else:
                    wtype, level, desc = "overstock", "low", f"库存金额较高{cost:.0f}元"

                await db.execute(text("""
                    INSERT INTO dm.dm_inventory_warning (
                        warning_date, store_code, product_code, sku_code,
                        warning_type, warning_level, current_quantity, current_cost_amount,
                        age_days, description, generated_at
                    ) VALUES (:d,:sc,:pc,:sku,:wt,:wl,:qty,:cost,:age,:desc,NOW())
                    ON CONFLICT DO NOTHING
                """), {"d": date.fromisoformat(stat_date), "sc": sc, "pc": pc, "sku": sku,
                       "wt": wtype, "wl": level, "qty": int(qty or 0),
                       "cost": float(cost or 0), "age": int(age or 0), "desc": desc})
                count += 1
            await db.commit()
            etl_log.finish_task(run_id, output_rows=count)
            return count
        except Exception as exc:
            await db.rollback()
            etl_log.fail_task(run_id, str(exc))
            print(f"[DwsToDm] inv_warning 失败: {exc}")
            return 0

    async def _replenishment_advice(self, stat_date: str, db: AsyncSession, etl_log) -> int:
        run_id = etl_log.start_task("dws_to_dm_replenishment", stat_date)
        try:
            seven_ago = date.fromisoformat(stat_date) - timedelta(days=7)
            r = await db.execute(text("""
                SELECT pd.store_code, pd.product_code, AVG(pd.sales_quantity/7.0) AS daily_avg,
                       inv.quantity AS current_qty
                FROM dws.dws_product_daily pd
                JOIN (
                    SELECT store_code, product_code, SUM(quantity) AS quantity
                    FROM dwd.v_apparel_inventory_snapshot
                    WHERE snapshot_date = :snap
                    GROUP BY store_code, product_code
                ) inv ON pd.store_code = inv.store_code AND pd.product_code = inv.product_code
                WHERE pd.stat_date >= :start AND pd.stat_date <= :end
                  AND pd.sales_quantity > 0
                GROUP BY pd.store_code, pd.product_code, inv.quantity
                HAVING AVG(pd.sales_quantity/7.0) > 0
                   AND inv.quantity < AVG(pd.sales_quantity/7.0) * 7
                LIMIT 200
            """), {"snap": date.fromisoformat(stat_date), "start": seven_ago, "end": date.fromisoformat(stat_date)})
            rows = r.fetchall()
            count = 0
            for sc, pc, daily_avg, current_qty in rows:
                daily_avg = float(daily_avg or 0)
                current_qty = int(current_qty or 0)
                sellable_days = int(current_qty / daily_avg) if daily_avg > 0 else 0
                suggested = max(0, int(daily_avg * 14) - current_qty)
                urgency = "urgent" if sellable_days < 3 else ("soon" if sellable_days < 7 else "normal")
                await db.execute(text("""
                    INSERT INTO dm.dm_replenishment_advice (
                        advice_date, store_code, product_code, sku_code,
                        current_quantity, daily_avg_sales_7d, sellable_days,
                        suggested_quantity, urgency, reason, status, generated_at
                    ) VALUES (:d,:sc,:pc,'ALL',:qty,:daily,:days,:sugg,:urg,:reason,'pending',NOW())
                    ON CONFLICT DO NOTHING
                """), {"d": date.fromisoformat(stat_date), "sc": sc, "pc": pc, "qty": current_qty,
                       "daily": round(daily_avg, 2), "days": sellable_days,
                       "sugg": suggested, "urg": urgency,
                       "reason": f"近7天日均销{daily_avg:.1f}件，当前库存仅够{sellable_days}天"})
                count += 1
            await db.commit()
            etl_log.finish_task(run_id, output_rows=count)
            return count
        except Exception as exc:
            await db.rollback()
            etl_log.fail_task(run_id, str(exc))
            print(f"[DwsToDm] replenishment 失败: {exc}")
            return 0

    async def _finance_profit(self, stat_date: str, db: AsyncSession, etl_log) -> int:
        run_id = etl_log.start_task("dws_to_dm_finance_profit", stat_date)
        try:
            r = await db.execute(text("""
                SELECT
                    fd.store_code, fd.net_sales_amount, fd.cost_amount, fd.gross_profit,
                    fd.gross_margin, fd.total_expense, fd.operating_profit_estimate,
                    fd.data_type, fd.is_profit_complete
                FROM dws.dws_finance_daily fd
                WHERE fd.stat_date = :d
            """), {"d": date.fromisoformat(stat_date)})
            rows = r.fetchall()
            if not rows:
                etl_log.finish_task(run_id, output_rows=0)
                return 0

            count = 0
            for row in rows:
                sc = row[0]
                await db.execute(text("""
                    INSERT INTO dm.dm_finance_profit_daily (
                        stat_date, store_code, net_sales, cost_of_goods, gross_profit, gross_margin,
                        total_expense, operating_profit, data_type,
                        is_cost_complete, is_expense_complete, generated_at
                    ) VALUES (
                        :d,:sc,:net,:cog,:gp,:gm,:exp,:op,:dt,:cost,:exp_ok,NOW()
                    )
                    ON CONFLICT (stat_date, store_code) DO UPDATE SET
                        operating_profit = EXCLUDED.operating_profit,
                        gross_margin     = EXCLUDED.gross_margin,
                        data_type        = EXCLUDED.data_type,
                        generated_at     = NOW()
                """), {
                    "d": date.fromisoformat(stat_date), "sc": sc,
                    "net": float(row[1] or 0),
                    "cog": float(row[2] or 0),
                    "gp": float(row[3] or 0),
                    "gm": float(row[4] or 0),
                    "exp": float(row[5] or 0),
                    "op": float(row[6] or 0),
                    "dt": row[7] or "estimate",
                    "cost": True,
                    "exp_ok": bool(row[8]),
                })
                count += 1
            await db.commit()
            etl_log.finish_task(run_id, output_rows=count)
            return count
        except Exception as exc:
            await db.rollback()
            etl_log.fail_task(run_id, str(exc))
            print(f"[DwsToDm] finance_profit 失败: {exc}")
            return 0
