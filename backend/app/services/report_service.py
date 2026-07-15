"""老板日报生成服务：聚合25项内容 + DeepSeek AI摘要"""
import json
import logging
from datetime import date, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.services.ai_engine import (
    AIEngine,
    build_template_command_conclusion,
    sanitize_command_context,
)

logger = logging.getLogger(__name__)


class ReportService:
    async def generate_boss_daily(self, stat_date: str, db: AsyncSession, force: bool = False) -> dict:
        d = date.fromisoformat(stat_date)

        # 检查是否已生成（不强制重生成时跳过）
        if not force:
            exists = await db.execute(text(
                "SELECT ai_summary FROM dm.dm_boss_daily_report WHERE report_date = :d"
            ), {"d": d})
            row = exists.fetchone()
            if row and row[0]:
                return await self._get_existing_report(stat_date, db)

        # 数据完整性前置检查（9项）
        quality = await self._check_data_quality(stat_date, d, db)
        if quality["block_generation"]:
            return {
                "report_date": stat_date,
                "data_quality": quality,
                "blocked": True,
                "block_reason": quality["block_reason"],
                "ai_summary": "⚠️ 当前数据不完整，报告生成被阻断。" + quality["block_reason"],
            }

        # 收集25项数据
        report_data = await self._collect_report_data(stat_date, d, db)

        # 生成AI摘要
        ai_result = await self._generate_ai_summary(report_data, db)

        # 写回数据库
        await db.execute(text("""
            UPDATE dm.dm_boss_daily_report SET
                ai_summary          = :ai_summary,
                ai_today_focus      = :today_focus,
                ai_risk_summary     = :risk_summary,
                ai_data_completeness = :data_completeness,
                ai_model_used       = :model_used,
                ai_command_conclusion = CAST(:command_conclusion AS jsonb),
                ai_generated_at     = NOW(),
                updated_at          = NOW()
            WHERE report_date = :d
        """), {
            "d": d,
            "ai_summary": ai_result.get("summary", ""),
            "today_focus": ai_result.get("today_focus", ""),
            "risk_summary": ai_result.get("risk_summary", ""),
            "data_completeness": ai_result.get("data_completeness", ""),
            "model_used": ai_result.get("model_used", ""),
            "command_conclusion": json.dumps(
                ai_result.get("command_conclusion") or {}, ensure_ascii=False
            ),
        })
        await db.commit()

        return await self._get_existing_report(stat_date, db)

    async def _collect_report_data(self, stat_date: str, d: date, db: AsyncSession) -> dict:
        prev_day = (d - timedelta(days=1)).isoformat()
        prev_week = (d - timedelta(days=7)).isoformat()
        prev_month = (d - timedelta(days=30)).isoformat()

        # 1. 当日销售核心指标
        boss_r = await db.execute(text("""
            SELECT total_sales, offline_sales, online_sales, online_ratio,
                   net_sales, order_count, item_count, avg_order_value, items_per_order,
                   avg_discount_rate, gross_profit, gross_margin,
                   cash_balance, cash_safety_days,
                   total_inventory_amount, age_90_plus_amount, age_180_plus_amount,
                   exception_count, is_cost_complete, is_finance_complete, metric_status,
                   actual_pay_amount, return_amount, return_rate,
                   vip_balance, vip_sales_amount, operating_profit_estimate
            FROM dm.dm_boss_daily_report WHERE report_date = :d
        """), {"d": d})
        boss = boss_r.fetchone()
        if not boss:
            return {"error": "当日日报数据未生成，请先运行ETL"}

        # 2. 日环比/周同比
        prev_day_r = await db.execute(text("""
            SELECT total_sales, order_count FROM dm.dm_boss_daily_report WHERE report_date = :d
        """), {"d": date.fromisoformat(prev_day)})
        prev_day_row = prev_day_r.fetchone()

        prev_week_r = await db.execute(text("""
            SELECT total_sales FROM dm.dm_boss_daily_report WHERE report_date = :d
        """), {"d": date.fromisoformat(prev_week)})
        prev_week_row = prev_week_r.fetchone()

        def pct(now, prev):
            if not prev or not prev[0] or prev[0] == 0:
                return None
            return round((float(now) - float(prev[0])) / float(prev[0]) * 100, 1)

        total_sales = float(boss[0] or 0)
        dod_growth = pct(total_sales, prev_day_row)
        wow_growth = pct(total_sales, prev_week_row)

        # 3. 门店排行
        stores_r = await db.execute(text("""
            SELECT store_code, net_sales_amount, gross_margin, order_count
            FROM dws.dws_store_daily WHERE stat_date = :d AND channel = 'offline'
            ORDER BY net_sales_amount DESC LIMIT 5
        """), {"d": d})
        stores = [{"store": r[0], "sales": float(r[1] or 0), "margin": float(r[2] or 0),
                   "orders": int(r[3] or 0)} for r in stores_r.fetchall()]

        # 4. 商品TOP5
        products_r = await db.execute(text("""
            SELECT pd.product_code, p.product_name, SUM(pd.net_sales_amount) AS sales
            FROM dws.dws_product_daily pd
            LEFT JOIN ods.ods_baison_product p ON pd.product_code = p.product_code
            WHERE pd.stat_date = :d
            GROUP BY pd.product_code, p.product_name
            ORDER BY sales DESC LIMIT 5
        """), {"d": d})
        products = [{"code": r[0], "name": r[1] or r[0], "sales": float(r[2] or 0)}
                    for r in products_r.fetchall()]

        # 5. 库存预警
        warn_r = await db.execute(text("""
            SELECT warning_type, warning_level, COUNT(*) as cnt
            FROM dm.dm_inventory_warning WHERE warning_date = :d
            GROUP BY warning_type, warning_level
        """), {"d": d})
        warnings = [{"type": r[0], "level": r[1], "count": int(r[2])} for r in warn_r.fetchall()]

        # 6. 补货建议（紧急）
        repl_r = await db.execute(text("""
            SELECT store_code, product_code, current_quantity, daily_avg_sales_7d, sellable_days
            FROM dm.dm_replenishment_advice WHERE advice_date = :d AND urgency = 'urgent'
            ORDER BY sellable_days LIMIT 5
        """), {"d": d})
        urgent_replenishment = [{"store": r[0], "product": r[1], "qty": int(r[2] or 0),
                                  "daily_avg": float(r[3] or 0), "days": int(r[4] or 0)}
                                 for r in repl_r.fetchall()]

        # 7. 近30天趋势（简化为最近7天）
        trend_r = await db.execute(text("""
            SELECT report_date, total_sales, order_count, gross_margin
            FROM dm.dm_boss_daily_report
            WHERE report_date BETWEEN :start AND :end
            ORDER BY report_date
        """), {"start": date.fromisoformat(prev_week), "end": d})
        trend = [{"date": str(r[0]), "sales": float(r[1] or 0), "orders": int(r[2] or 0),
                  "margin": float(r[3] or 0)} for r in trend_r.fetchall()]

        # 8. 财务数据
        expense_r = await db.execute(text("""
            SELECT COALESCE(SUM(expense_amount), 0)
            FROM dwd.dwd_finance_expense WHERE expense_date = :d
        """), {"d": d})
        today_expense = float(expense_r.scalar() or 0)

        return {
            "stat_date": stat_date,
            "total_sales": total_sales,
            "offline_sales": float(boss[1] or 0),
            "online_sales": float(boss[2] or 0),
            "online_ratio": float(boss[3] or 0),
            "net_sales": float(boss[4] or 0),
            "order_count": int(boss[5] or 0),
            "item_count": int(boss[6] or 0),
            "avg_order_value": float(boss[7] or 0),
            "items_per_order": float(boss[8] or 0),
            "avg_discount_rate": float(boss[9] or 0),
            "gross_profit": float(boss[10] or 0),
            "gross_margin": float(boss[11]) if boss[11] is not None else None,
            "cash_balance": float(boss[12] or 0),
            "cash_safety_days": int(boss[13] or 0),
            "total_inventory": float(boss[14] or 0),
            "age_90_plus": float(boss[15] or 0),
            "age_180_plus": float(boss[16] or 0),
            "exception_count": int(boss[17] or 0),
            "is_cost_complete": bool(boss[18]),
            "is_finance_complete": bool(boss[19]),
            "metric_status": boss[20] or {},
            "actual_pay_amount": float(boss[21] or 0),
            "return_amount": float(boss[22] or 0),
            "return_rate": float(boss[23] or 0),
            "vip_balance": float(boss[24] or 0),
            "vip_sales_amount": float(boss[25] or 0),
            "operating_profit": float(boss[26]) if boss[26] is not None else None,
            "dod_growth": dod_growth,
            "wow_growth": wow_growth,
            "top_stores": stores[:3],
            "bottom_stores": stores[-3:] if len(stores) >= 3 else stores,
            "top_products": products[:3],
            "inventory_warnings": warnings,
            "urgent_replenishment": urgent_replenishment,
            "today_expense": today_expense,
            "trend_7d": trend,
        }

    async def _generate_ai_summary(
        self, data: dict, db: AsyncSession, *, allow_model: bool = True
    ) -> dict:
        if "error" in data:
            return {"summary": f"⚠️ {data['error']}", "today_focus": "", "risk_summary": "",
                    "data_completeness": "", "model_used": "none"}
        stat_date = data.get("stat_date")
        statuses = data.get("metric_status") or {}
        cost_status = "ready" if data.get("is_cost_complete") else "estimated"
        gross_margin_status = statuses.get("gross_margin")
        if not gross_margin_status:
            gross_margin_status = (
                statuses.get("gross_profit") or cost_status
            ) if data.get("gross_margin") is not None and data.get("total_sales") not in (None, 0) else "pending_data"
        finance_status = "ready" if data.get("is_finance_complete") else "pending_data"
        metrics = {
            "sales_amount": {"value": data.get("total_sales"), "status": statuses.get("sales") or "pending_data", "source": "baison_pos", "as_of": stat_date},
            "actual_pay_amount": {"value": data.get("actual_pay_amount"), "status": statuses.get("actual_pay") or "pending_data", "source": "baison_payment", "as_of": stat_date},
            "offline_sales": {"value": data.get("offline_sales"), "status": statuses.get("sales") or "pending_data", "source": "baison_pos", "as_of": stat_date},
            "online_sales": {"value": data.get("online_sales"), "status": statuses.get("online_sales") or "pending_data", "source": "baison_pos.online_payment", "as_of": stat_date},
            "order_count": {"value": data.get("order_count"), "status": statuses.get("sales_detail") or "pending_data", "source": "baison_pos", "as_of": stat_date},
            "item_count": {"value": data.get("item_count"), "status": statuses.get("sales_detail") or "pending_data", "source": "baison_pos", "as_of": stat_date},
            "avg_order_value": {"value": data.get("avg_order_value"), "status": statuses.get("sales_detail") or "pending_data", "source": "baison_pos", "as_of": stat_date},
            "items_per_order": {"value": data.get("items_per_order"), "status": statuses.get("sales_detail") or "pending_data", "source": "baison_pos", "as_of": stat_date},
            "gross_profit": {"value": data.get("gross_profit"), "status": statuses.get("gross_profit") or cost_status, "source": "baison_standard_purchase_price", "as_of": stat_date},
            "gross_margin": {"value": data.get("gross_margin"), "status": gross_margin_status, "source": "baison_standard_purchase_price", "as_of": stat_date},
            "inventory_amount": {"value": data.get("total_inventory"), "status": statuses.get("inventory") or "pending_data", "source": "apparel_inventory", "as_of": stat_date},
            "age_90_plus_amount": {"value": data.get("age_90_plus"), "status": statuses.get("inventory_age") or statuses.get("inventory") or "pending_data", "source": "fifo_inbound", "as_of": stat_date},
            "return_amount": {"value": data.get("return_amount"), "status": statuses.get("returns") or "pending_data", "source": "baison_pos.refund_amount", "as_of": stat_date},
            "return_rate": {"value": data.get("return_rate"), "status": statuses.get("returns") or "pending_data", "source": "baison_pos.refund_amount", "as_of": stat_date},
            "vip_balance": {"value": data.get("vip_balance"), "status": statuses.get("vip_balance") or "pending_data", "source": "baison_member.CZ_DQJE", "as_of": stat_date},
            "vip_sales": {"value": data.get("vip_sales_amount"), "status": statuses.get("sales") or "pending_data", "source": "baison_pos", "as_of": stat_date},
            "operating_profit": {
                "value": data.get("operating_profit"),
                "status": statuses.get("operating_profit") or finance_status,
                "source": "finance",
                "as_of": stat_date,
                "reason": None if data.get("is_finance_complete") else "费用未完整接入，当前经营利润为估算值",
            },
            "expense_amount": {
                "value": data.get("today_expense") if data.get("is_finance_complete") else None,
                "status": finance_status,
                "source": "finance_expense",
                "as_of": stat_date,
                "reason": None if data.get("is_finance_complete") else "费用来源未完整接入",
            },
        }
        rules = [{
            "id": f"inventory:{item.get('type')}:{index}",
            "title": f"{item.get('type') or '库存'}预警 {item.get('count', 0)} 项",
            "level": item.get("level") or "warning",
            "evidence": [f"数量={item.get('count', 0)}"],
            "source": "dm_inventory_warning",
        } for index, item in enumerate(data.get("inventory_warnings") or [])]
        command_context = {
            "metrics": metrics,
            "rules": rules,
            "tasks": [],
            "finance_complete": bool(data.get("is_finance_complete")),
        }
        if allow_model:
            conclusion = await AIEngine(db).generate_command_conclusion(command_context)
        else:
            conclusion = build_template_command_conclusion(
                sanitize_command_context(command_context)
            )
            conclusion.update({
                "mode": "template",
                "model_used": "deterministic_rules",
                "fallback_reason": "legacy_report_without_persisted_conclusion",
            })
        fact_text = "；".join(
            f"{item['label']}{item['value']}{'（预估）' if item['status'] == 'estimated' else ''}"
            for item in conclusion["facts"][:6]
        )
        risk_text = "；".join(item["title"] for item in conclusion["risks"][:3]) or "暂无确定性重大风险"
        focus_text = "；".join(item["title"] for item in conclusion["recommendations"][:2]) or "复核数据质量和待处理任务"
        return {
            "summary": fact_text or "；".join(conclusion["limitations"][:2]) or "当日核心指标尚未就绪",
            "today_focus": focus_text,
            "risk_summary": risk_text,
            "data_completeness": "；".join(conclusion["limitations"]) or "已接入指标均已就绪",
            "model_used": conclusion.get("model_used") or conclusion.get("mode") or "template",
            "command_conclusion": conclusion,
        }

    async def _get_existing_report(self, stat_date: str, db: AsyncSession) -> dict:
        d = date.fromisoformat(stat_date)
        r = await db.execute(text("""
            SELECT report_date, total_sales, offline_sales, online_sales, online_ratio,
                   net_sales, order_count, item_count, avg_order_value, items_per_order,
                   avg_discount_rate, gross_profit, gross_margin,
                   total_expense, operating_profit_estimate,
                   cash_balance, cash_safety_days,
                   total_inventory_amount, age_90_plus_amount, age_180_plus_amount,
                   pending_task_count, overdue_task_count, exception_count,
                   ai_summary, ai_today_focus, ai_risk_summary,
                   ai_data_completeness, ai_model_used, ai_generated_at,
                   is_cost_complete, is_finance_complete, generated_at,
                   actual_pay_amount, return_amount, return_rate,
                   inventory_total_qty, vip_balance, vip_negative_balance_count,
                   vip_sales_amount, vip_sales_ratio, major_exception_count,
                   source_freshness, metric_status
                   , inventory_age_unknown_qty, inventory_age_unknown_amount,
                   ai_command_conclusion
            FROM dm.dm_boss_daily_report WHERE report_date = :d
        """), {"d": d})
        row = r.fetchone()
        if not row:
            return {"error": f"{stat_date} 无日报数据，请先运行ETL"}

        report = {
            "report_date": str(row[0]),
            "total_sales": float(row[1] or 0),
            "offline_sales": float(row[2] or 0),
            "online_sales": float(row[3] or 0),
            "online_ratio": float(row[4] or 0),
            "net_sales": float(row[5] or 0),
            "order_count": int(row[6] or 0),
            "item_count": int(row[7] or 0),
            "avg_order_value": float(row[8] or 0),
            "items_per_order": float(row[9] or 0),
            "avg_discount_rate": float(row[10] or 0),
            "gross_profit": float(row[11] or 0),
            "gross_margin": float(row[12]) if row[12] is not None else None,
            "total_expense": float(row[13] or 0),
            "operating_profit_estimate": float(row[14] or 0),
            "cash_balance": float(row[15] or 0),
            "cash_safety_days": int(row[16] or 0),
            "total_inventory_amount": float(row[17] or 0),
            "age_90_plus_amount": float(row[18] or 0),
            "age_180_plus_amount": float(row[19] or 0),
            "pending_task_count": int(row[20] or 0),
            "overdue_task_count": int(row[21] or 0),
            "exception_count": int(row[22] or 0),
            "ai_summary": row[23],
            "ai_today_focus": row[24],
            "ai_risk_summary": row[25],
            "ai_data_completeness": row[26],
            "ai_model_used": row[27],
            "ai_generated_at": str(row[28]) if row[28] else None,
            "is_cost_complete": bool(row[29]),
            "is_finance_complete": bool(row[30]) if row[30] is not None else False,
            "generated_at": str(row[31]) if row[31] else None,
            "actual_pay_amount": float(row[32] or 0),
            "return_amount": float(row[33] or 0),
            "return_rate": float(row[34] or 0),
            "inventory_total_qty": float(row[35] or 0),
            "vip_balance": float(row[36] or 0),
            "vip_negative_balance_count": int(row[37] or 0),
            "vip_sales_amount": float(row[38] or 0),
            "vip_sales_ratio": float(row[39] or 0),
            "major_exception_count": int(row[40] or 0),
            "source_freshness": row[41] or {},
            "metric_status": row[42] or {},
            "inventory_age_unknown_qty": float(row[43] or 0),
            "inventory_age_unknown_amount": float(row[44] or 0),
            "command_conclusion": row[45] or None,
            "data_completeness_label": "成本缺失，利润不可准确计算。" if not row[29] else "",
        }
        if report["command_conclusion"]:
            return report
        risk_count = report["major_exception_count"] or report["exception_count"]
        structured = await self._generate_ai_summary({
            "stat_date": report["report_date"],
            "total_sales": report["total_sales"],
            "offline_sales": report["offline_sales"],
            "online_sales": report["online_sales"],
            "actual_pay_amount": report["actual_pay_amount"],
            "order_count": report["order_count"],
            "item_count": report["item_count"],
            "avg_order_value": report["avg_order_value"],
            "items_per_order": report["items_per_order"],
            "gross_profit": report["gross_profit"],
            "gross_margin": report["gross_margin"],
            "total_inventory": report["total_inventory_amount"],
            "age_90_plus": report["age_90_plus_amount"],
            "today_expense": report["total_expense"],
            "operating_profit": report["operating_profit_estimate"],
            "return_amount": report["return_amount"],
            "return_rate": report["return_rate"],
            "vip_balance": report["vip_balance"],
            "vip_sales_amount": report["vip_sales_amount"],
            "is_cost_complete": report["is_cost_complete"],
            "is_finance_complete": report["is_finance_complete"],
            "exception_count": report["exception_count"],
            "metric_status": report["metric_status"],
            "inventory_warnings": ([{
                "type": "重大经营异常",
                "count": risk_count,
                "level": "critical",
            }] if risk_count else []),
        }, db, allow_model=False)
        report["command_conclusion"] = structured["command_conclusion"]
        return report

    async def _check_data_quality(self, stat_date: str, d, db) -> dict:
        """检查9项数据完整性，决定是否阻断日报生成"""
        issues = []
        warnings = []
        has_sales = has_return = has_inventory = has_cost = False
        has_finance = has_cash = False

        r = await db.execute(text("SELECT COUNT(*) FROM dwd.dwd_sales_detail WHERE order_date = :d"), {"d": d})
        if int(r.scalar() or 0) > 0:
            has_sales = True
        else:
            issues.append("无销售明细数据")

        r = await db.execute(text("SELECT COUNT(*) FROM dwd.dwd_return_detail WHERE return_date = :d"), {"d": d})
        has_return = int(r.scalar() or 0) > 0
        if not has_return:
            warnings.append("无退货数据（可能当日无退货）")

        r = await db.execute(text("SELECT COUNT(*) FROM dwd.v_apparel_inventory_snapshot WHERE snapshot_date = :d"), {"d": d})
        if int(r.scalar() or 0) > 0:
            has_inventory = True
        else:
            issues.append("无库存快照数据")

        r = await db.execute(text("SELECT COUNT(*) FROM dwd.dwd_sales_detail WHERE order_date = :d AND cost_price > 0"), {"d": d})
        has_cost = int(r.scalar() or 0) > 0
        if not has_cost:
            warnings.append("成本缺失，利润不可准确计算")

        r = await db.execute(text("SELECT COUNT(*) FROM dws.dws_store_daily WHERE stat_date = :d"), {"d": d})
        if int(r.scalar() or 0) == 0:
            issues.append("DWS汇总数据未生成，请先运行ETL")

        r = await db.execute(text("SELECT COUNT(*) FROM dwd.dwd_finance_expense WHERE expense_date = :d"), {"d": d})
        has_finance = int(r.scalar() or 0) > 0
        if not has_finance:
            warnings.append("无财务费用数据")

        r = await db.execute(text("SELECT COUNT(*) FROM dwd.dwd_finance_cash WHERE record_date = :d"), {"d": d})
        has_cash = int(r.scalar() or 0) > 0
        if not has_cash:
            warnings.append("无现金余额数据")

        r = await db.execute(text("""
            SELECT COUNT(*) FROM app.app_metrics_reconciliation
            WHERE reconcile_date = :d AND is_blocking = TRUE AND is_passed = FALSE
        """), {"d": d})
        blocking_reconcile = int(r.scalar() or 0)
        if blocking_reconcile > 0:
            issues.append(f"存在{blocking_reconcile}个指标对账高风险项未处理")

        r = await db.execute(text("SELECT COUNT(*) FROM dm.dm_boss_daily_report WHERE report_date = :d"), {"d": d})
        if int(r.scalar() or 0) == 0:
            issues.append("老板日报基础数据未生成，请先运行完整ETL")

        block_generation = len(issues) > 0
        return {
            "has_sales": has_sales, "has_return": has_return,
            "has_inventory": has_inventory, "has_cost": has_cost,
            "has_finance": has_finance, "has_cash": has_cash,
            "blocking_issues": issues, "warnings": warnings,
            "block_generation": block_generation,
            "block_reason": "；".join(issues) if issues else "",
            "data_completeness_label": (
                "当前数据不完整，以下结果仅供参考。"
                if (not has_cost or not has_finance or not has_cash) else "数据完整"
            ),
            "cost_missing_label": "成本缺失，利润不可准确计算。" if not has_cost else "",
        }
