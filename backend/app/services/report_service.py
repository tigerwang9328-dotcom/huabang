"""老板日报生成服务：聚合25项内容 + DeepSeek AI摘要"""
import json
import logging
import httpx
from datetime import date, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.config import settings
from app.services.command_center_service import build_template_summary

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
        ai_result = await self._generate_ai_summary(report_data)

        # 写回数据库
        await db.execute(text("""
            UPDATE dm.dm_boss_daily_report SET
                ai_summary          = :ai_summary,
                ai_today_focus      = :today_focus,
                ai_risk_summary     = :risk_summary,
                ai_data_completeness = :data_completeness,
                ai_model_used       = :model_used,
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
                   exception_count, is_cost_complete
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
            "gross_margin": float(boss[11] or 0),
            "cash_balance": float(boss[12] or 0),
            "cash_safety_days": int(boss[13] or 0),
            "total_inventory": float(boss[14] or 0),
            "age_90_plus": float(boss[15] or 0),
            "age_180_plus": float(boss[16] or 0),
            "exception_count": int(boss[17] or 0),
            "is_cost_complete": bool(boss[18]),
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

    async def _generate_ai_summary(self, data: dict) -> dict:
        if "error" in data:
            return {"summary": f"⚠️ {data['error']}", "today_focus": "", "risk_summary": "",
                    "data_completeness": "", "model_used": "none"}

        cost_note = "（成本数据完整）" if data.get("is_cost_complete") else "（⚠️ 成本数据不完整，毛利为预估值）"
        fallback = {
            "summary": build_template_summary(
                sales=data.get("total_sales", 0),
                gross_profit=data.get("gross_profit"),
                gross_margin=data.get("gross_margin"),
                finance_complete=False,
                risk_count=data.get("exception_count", 0),
                pending_task_count=0,
            ),
            "today_focus": "优先处理重大异常和逾期任务。",
            "risk_summary": "以规则引擎结构化结果为准。",
            "data_completeness": "费用未完整接入，暂不判断最终盈亏。",
            "model_used": "template",
        }

        prompt = f"""你是华邦服饰的经营分析AI。请根据以下{data['stat_date']}的实际经营数据，生成简洁的老板日报摘要。

【当日核心数据】{cost_note}
- 总销售额：{data['total_sales']:.0f}元（日环比{(data['dod_growth'] or 0):+.1f}%，周同比{(data['wow_growth'] or 0):+.1f}%）
- 线下：{data['offline_sales']:.0f}元 | 线上：{data['online_sales']:.0f}元（占比{data['online_ratio']*100:.1f}%）
- 订单数：{data['order_count']}单，客单价：{data['avg_order_value']:.0f}元，件单价：{data['items_per_order']:.1f}件
- 毛利：{data['gross_profit']:.0f}元，毛利率：{data['gross_margin']*100:.1f}%
- 今日费用录入：{data['today_expense']:.0f}元

【库存状况】
- 库存总金额：{data['total_inventory']:.0f}元
- 90天以上滞销：{data['age_90_plus']:.0f}元（占比{data['age_90_plus']/data['total_inventory']*100:.1f}%）
- 180天以上滞销：{data['age_180_plus']:.0f}元

【现金与安全】
- 现金余额：{data['cash_balance']:.0f}元，安全天数：{data['cash_safety_days']}天
- 异常预警数：{data['exception_count']}条
- 紧急补货SKU：{len(data.get('urgent_replenishment', []))}个

【门店TOP3】
{json.dumps(data.get('top_stores', []), ensure_ascii=False, indent=2)}

请严格按以下JSON格式输出（不要输出代码块标记，直接输出JSON）：
{{
  "summary": "100字以内的总体经营情况总结",
  "today_focus": "今日需要老板重点关注的1-2件事（具体、可执行）",
  "risk_summary": "最主要的风险提示（如有），无风险则写'当日经营正常'",
  "data_completeness": "数据完整性说明（一句话）"
}}

注意：
1. 只描述事实，不编造数据
2. 不生成任何操作指令（不说"已调整"、"已采购"等）
3. 如果数据为0或无数据，直接说明"暂无数据"
4. 数字保留一位小数"""

        try:
            api_key = settings.DEEPSEEK_API_KEY
            if not api_key:
                return fallback

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 500,
                        "temperature": 0.3,
                        "stream": False,
                    }
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"].strip()

                # 尝试解析JSON
                try:
                    result = json.loads(content)
                except json.JSONDecodeError:
                    import re
                    m = re.search(r'\{.*\}', content, re.DOTALL)
                    if m:
                        result = json.loads(m.group())
                    else:
                        result = {"summary": content[:200], "today_focus": "",
                                  "risk_summary": "", "data_completeness": ""}

                result["model_used"] = "deepseek-chat"
                return result

        except Exception as e:
            logger.error(f"AI摘要生成失败: {e}")
            return fallback

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
                   , inventory_age_unknown_qty, inventory_age_unknown_amount
            FROM dm.dm_boss_daily_report WHERE report_date = :d
        """), {"d": d})
        row = r.fetchone()
        if not row:
            return {"error": f"{stat_date} 无日报数据，请先运行ETL"}

        return {
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
            "gross_margin": float(row[12] or 0),
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
            "data_completeness_label": "成本缺失，利润不可准确计算。" if not row[29] else "",
        }

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
