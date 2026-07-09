from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


LEVEL_LABEL = {"high": "高", "medium": "中", "low": "低"}


def _num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except Exception:
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(_num(value, default))
    except Exception:
        return default


def _date_str(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def _money(value: Any) -> str:
    n = _num(value)
    if abs(n) >= 10000:
        return f"{n / 10000:.2f}万"
    return f"{n:.0f}元"


def _pct(value: Any) -> str:
    if value is None:
        return "未接入"
    n = _num(value)
    if abs(n) <= 1:
        n *= 100
    return f"{n:.1f}%"


class AIDiagnosisService:
    """规则版 AI 经营诊断服务。

    第一阶段只做发现、解释、行动建议和复查建议，不自动写采购、价格、库存或处罚类动作。
    所有查询均走现有 dws/dm/dwd/dim/app 表，失败时降级为空结果和数据质量提示。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _rows(self, sql: str, params: Optional[dict] = None) -> list[dict]:
        try:
            result = await self.db.execute(text(sql), params or {})
            return [dict(r._mapping) for r in result.fetchall()]
        except Exception:
            return []

    async def _one(self, sql: str, params: Optional[dict] = None) -> dict:
        rows = await self._rows(sql, params)
        return rows[0] if rows else {}

    async def _latest_date(self) -> str:
        row = await self._one(
            """
            select max(stat_date)::text as dt from dws.dws_company_daily
            union all
            select max(report_date)::text as dt from dm.dm_boss_daily_report
            order by dt desc nulls last
            limit 1
            """
        )
        return row.get("dt") or (date.today() - timedelta(days=1)).isoformat()

    def _quality(self, warnings: list[str], missing: list[str], source_tables: list[str]) -> dict:
        return {
            "is_complete": len(warnings) == 0 and len(missing) == 0,
            "missing_fields": missing,
            "warnings": warnings,
            "source_tables": source_tables,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _diag(
        self,
        module: str,
        level: str,
        title: str,
        description: str,
        evidence: list[str],
        reason: str,
        action: str,
        owner: str,
        deadline: str,
        review: str,
        source: str,
    ) -> dict:
        return {
            "id": f"{module}-{abs(hash(title + description)) % 1000000}",
            "module": module,
            "level": level,
            "level_label": LEVEL_LABEL.get(level, level),
            "title": title,
            "description": description,
            "evidence": evidence,
            "possible_reason": reason,
            "suggested_action": action,
            "suggested_owner_role": owner,
            "deadline_suggestion": deadline,
            "review_metric": review,
            "data_source": source,
        }

    def _task_from_diag(self, diag: dict, idx: int) -> dict:
        return {
            "task_no": f"AI-{datetime.now():%Y%m%d}-{idx:03d}",
            "task_source": "AI经营诊断",
            "problem_type": diag.get("title"),
            "description": diag.get("description"),
            "possible_reason": diag.get("possible_reason"),
            "today_action": diag.get("suggested_action"),
            "owner": diag.get("suggested_owner_role"),
            "collaborator": "相关门店 / 商品部 / 财务按问题协同",
            "deadline": diag.get("deadline_suggestion"),
            "priority": diag.get("level_label"),
            "feedback_requirement": "提交处理过程、现场照片或数据截图，并说明是否影响指标改善。",
            "status": "建议任务",
            "review_metric": diag.get("review_metric"),
        }

    async def overview(self, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        dt = stat_date or await self._latest_date()
        company = await self._one("select * from dws.dws_company_daily where stat_date=:dt", {"dt": dt})
        if not company:
            company = await self._one("select * from dm.dm_boss_daily_report where report_date=:dt", {"dt": dt})

        sales = await self.sales(dt, store_code)
        products = await self.products(dt, store_code)
        inventory = await self.inventory(dt, store_code)
        hr = await self.hr(dt, store_code)
        finance = await self.finance(dt, store_code)
        audit = await self.audit(dt, store_code)

        module_sets = [sales, products, inventory, hr, finance, audit]
        diagnoses = []
        for item in module_sets:
            diagnoses.extend(item.get("diagnoses", []))
        high = sum(1 for d in diagnoses if d.get("level") == "high")
        medium = sum(1 for d in diagnoses if d.get("level") == "medium")
        missing_penalty = sum(len(m.get("data_quality", {}).get("warnings", [])) for m in module_sets)
        score = max(45, min(98, 88 - high * 8 - medium * 4 - missing_penalty * 2))

        top3 = sorted(diagnoses, key=lambda d: {"high": 0, "medium": 1, "low": 2}.get(d.get("level"), 3))[:3]
        warnings = []
        missing = []
        for m in module_sets:
            q = m.get("data_quality", {})
            warnings.extend(q.get("warnings", []))
            missing.extend(q.get("missing_fields", []))

        if not top3 and (warnings or missing):
            data_diag = self._diag(
                "overview",
                "high",
                "核心经营数据未形成完整诊断底座",
                "销售、商品、库存、财务或人效存在汇总缺失，当前最大风险不是经营动作本身，而是管理层无法基于完整口径判断。",
                [f"缺失字段：{len(set(missing))}项", f"数据质量提示：{len(warnings)}条", f"诊断日期：{dt}"],
                "百胜同步、ETL汇总或财务/人事补录未完成，导致AI只能输出预警，不能输出完整经营结论。",
                "技术负责人先复核数据同步日志和ETL任务；业务负责人确认销售、库存、财务补录是否到位。",
                "技术负责人 / 数据负责人",
                "今日18:00前",
                "dws/dm核心表是否有当日记录、销售净额是否大于0、库存快照是否更新、财务费用是否补齐",
                "data_quality checks",
            )
            diagnoses.insert(0, data_diag)
            top3 = [data_diag]

        summary_text = (
            f"{dt} 综合健康分 {score} 分。系统已从销售、商品、库存、财务、人效和异常稽核中识别 "
            f"{len(diagnoses)} 条经营诊断，其中高风险 {sum(1 for d in diagnoses if d.get('level') == 'high')} 条、"
            f"中风险 {sum(1 for d in diagnoses if d.get('level') == 'medium')} 条。"
        )
        if top3:
            summary_text += " 今日优先抓：" + "；".join([d["title"] for d in top3]) + "。"
        if warnings or missing:
            summary_text += " 当前部分结论受数据完整性影响，已在数据质量区域单独标注。"

        risks = [
            {"name": "销售风险门店数", "value": sales["summary"].get("risk_store_count", 0), "level": "high" if sales["summary"].get("risk_store_count", 0) else "low"},
            {"name": "滞销商品数", "value": products["summary"].get("slow_product_count", 0), "level": "medium" if products["summary"].get("slow_product_count", 0) else "low"},
            {"name": "爆款断码数", "value": products["summary"].get("hot_low_stock_count", 0), "level": "high" if products["summary"].get("hot_low_stock_count", 0) else "low"},
            {"name": "高库龄SKU数", "value": inventory["summary"].get("age_90_sku_count", 0), "level": "high" if inventory["summary"].get("age_90_sku_count", 0) else "low"},
            {"name": "负库存SKU数", "value": inventory["summary"].get("negative_sku_count", 0), "level": "high" if inventory["summary"].get("negative_sku_count", 0) else "low"},
            {"name": "人效异常门店数", "value": hr["summary"].get("low_efficiency_store_count", 0), "level": "medium" if hr["summary"].get("low_efficiency_store_count", 0) else "low"},
            {"name": "财务风险项数", "value": finance["summary"].get("finance_risk_count", 0), "level": "medium" if finance["summary"].get("finance_risk_count", 0) else "low"},
            {"name": "异常折扣/退款数", "value": audit["summary"].get("audit_count", 0), "level": "high" if audit["summary"].get("audit_count", 0) else "low"},
            {"name": "逾期任务数", "value": await self._overdue_task_count(dt), "level": "high" if await self._overdue_task_count(dt) else "low"},
        ]

        return {
            "summary": {
                "stat_date": dt,
                "health_score": score,
                "sales_health": self._risk_label(sales),
                "product_health": self._risk_label(products),
                "inventory_health": self._risk_label(inventory),
                "hr_health": self._risk_label(hr),
                "finance_health": self._risk_label(finance),
                "net_sales": _num(company.get("net_sales_amount") or company.get("net_sales")),
                "order_count": _int(company.get("total_order_count") or company.get("order_count")),
                "gross_margin": _num(company.get("gross_margin")),
                "ai_summary": summary_text,
            },
            "risks": risks,
            "diagnoses": top3,
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(top3)],
            "data_quality": self._quality(warnings, sorted(set(missing)), ["dws_company_daily", "dws_store_daily", "dws_inventory_daily", "dm_*"]),
        }

    def _risk_label(self, payload: dict) -> str:
        ds = payload.get("diagnoses", [])
        if any(d.get("level") == "high" for d in ds):
            return "高风险"
        if any(d.get("level") == "medium" for d in ds):
            return "中风险"
        return "低风险"

    async def _overdue_task_count(self, dt: str) -> int:
        row = await self._one(
            """
            select count(*) as c
            from app.app_action_task
            where is_deleted=false and due_date <= :dt and status not in ('review_passed','closed','cancelled')
            """,
            {"dt": dt},
        )
        return _int(row.get("c"))

    async def sales(self, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        dt = stat_date or await self._latest_date()
        params = {"dt": dt, "store_code": store_code}
        store_filter = "and s.store_code=:store_code" if store_code else ""
        summary = await self._one(
            f"""
            select
              coalesce(sum(s.net_sales_amount),0) net_sales,
              coalesce(sum(s.order_count),0) order_count,
              coalesce(sum(s.net_item_count),0) item_count,
              case when sum(s.order_count)>0 then sum(s.net_sales_amount)/sum(s.order_count) end avg_order_value,
              case when sum(s.order_count)>0 then sum(s.net_item_count)::numeric/sum(s.order_count) end items_per_order,
              case when sum(s.net_sales_amount)>0 then sum(s.gross_profit)/sum(s.net_sales_amount) end gross_margin,
              case when sum(s.sales_amount)>0 then sum(s.return_amount)/sum(s.sales_amount) end return_rate,
              count(*) filter (where s.net_sales_amount<=0 or s.order_count<=0) risk_store_count
            from dws.dws_store_daily s
            where s.stat_date=:dt {store_filter}
            """,
            params,
        )
        stores = await self._rows(
            f"""
            with today as (
              select s.*, ds.store_name
              from dws.dws_store_daily s
              left join dim.dim_store ds on ds.store_code=s.store_code and ds.source_system='baison'
              where s.stat_date=:dt {store_filter}
            ),
            avg7 as (
              select store_code, avg(net_sales_amount) avg_sales7, avg(order_count) avg_orders7,
                     avg(avg_order_value) avg_aov7, avg(items_per_order) avg_items7
              from dws.dws_store_daily
              where stat_date < :dt::date and stat_date >= :dt::date - interval '7 day'
              group by store_code
            )
            select t.store_code, coalesce(t.store_name,t.store_code) store_name, t.net_sales_amount,
                   t.order_count, t.net_item_count, t.avg_order_value, t.items_per_order,
                   t.member_ratio, t.gross_margin, t.return_amount, a.avg_sales7, a.avg_orders7, a.avg_aov7, a.avg_items7
            from today t left join avg7 a on a.store_code=t.store_code
            order by t.net_sales_amount desc nulls last
            limit 80
            """,
            params,
        )
        diagnoses = []
        for s in stores:
            sales_now = _num(s.get("net_sales_amount"))
            avg7 = _num(s.get("avg_sales7"))
            orders = _num(s.get("order_count"))
            avg_orders = _num(s.get("avg_orders7"))
            aov = _num(s.get("avg_order_value"))
            avg_aov = _num(s.get("avg_aov7"))
            items = _num(s.get("items_per_order"))
            avg_items = _num(s.get("avg_items7"))
            name = s.get("store_name") or s.get("store_code")
            if avg7 > 0 and sales_now < avg7 * 0.75:
                if orders < avg_orders * 0.8:
                    ptype = "流量/成交问题"
                    reason = "订单数低于近7日均值，客单价不是主要矛盾。"
                    action = "督导复盘进店转化、店长组织会员邀约和陈列检查。"
                    review = "明日订单数、会员成交金额、进店转化复盘记录"
                elif avg_aov > 0 and aov < avg_aov * 0.8:
                    ptype = "客单/搭配问题"
                    reason = "订单数相对稳定，但客单价明显低于近7日均值。"
                    action = "店长复盘搭配话术，导购执行成套推荐和高毛利款引导。"
                    review = "明日客单价、连带率、高毛利款成交占比"
                else:
                    ptype = "综合销售下滑"
                    reason = "销售额低于近7日均值，需结合客流、会员和商品结构复盘。"
                    action = "督导今日到店检查陈列、会员邀约和爆款库存。"
                    review = "明日净销售额、订单数、会员销售占比"
                diagnoses.append(self._diag("sales", "high", f"{name}{ptype}", f"{name} 当日净销售 {_money(sales_now)}，低于近7日均值 {_money(avg7)}。", [f"净销售：{_money(sales_now)}", f"近7日均值：{_money(avg7)}", f"订单数：{_int(orders)}"], reason, action, "督导 / 店长", "今日21:30前", review, "dws.dws_store_daily"))
            elif avg_items > 0 and items < avg_items * 0.85:
                diagnoses.append(self._diag("sales", "medium", f"{name}连带率偏低", f"{name} 连带率 {items:.2f}，低于近7日均值 {avg_items:.2f}。", [f"连带率：{items:.2f}", f"近7日均值：{avg_items:.2f}"], "搭配销售执行弱，导购可能只完成单件成交。", "店长组织班前搭配训练，设置当日连带率改善目标。", "店长 / 导购", "今日闭店前", "明日连带率、成套成交笔数", "dws.dws_store_daily"))
        warnings = [] if stores else ["销售诊断暂无门店日汇总数据，可能是当日 ETL 未完成或百胜销售未同步。"]
        return {
            "summary": {
                "stat_date": dt,
                "net_sales": _num(summary.get("net_sales")),
                "order_count": _int(summary.get("order_count")),
                "item_count": _int(summary.get("item_count")),
                "avg_order_value": _num(summary.get("avg_order_value")),
                "items_per_order": _num(summary.get("items_per_order")),
                "gross_margin": _num(summary.get("gross_margin")),
                "return_rate": _num(summary.get("return_rate")),
                "risk_store_count": _int(summary.get("risk_store_count")),
            },
            "risks": self._store_rank_risks(stores),
            "diagnoses": diagnoses[:30],
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(diagnoses[:8])],
            "data_quality": self._quality(warnings, ["销售目标/同比数据"] if stores else ["门店销售汇总"], ["dws_store_daily", "dim_store"]),
        }

    def _store_rank_risks(self, stores: list[dict]) -> list[dict]:
        if not stores:
            return []
        bottom = sorted(stores, key=lambda x: _num(x.get("net_sales_amount")))[:3]
        top = stores[:3]
        risks = [{"name": "销售前三", "value": " / ".join([x.get("store_name") or x.get("store_code") for x in top]), "level": "low"}]
        risks.append({"name": "销售后三", "value": " / ".join([x.get("store_name") or x.get("store_code") for x in bottom]), "level": "medium"})
        return risks

    async def products(self, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        dt = stat_date or await self._latest_date()
        products = await self._rows(
            """
            with sales30 as (
              select product_code, sum(net_quantity) qty30, sum(net_sales_amount) sales30, avg(gross_margin) gm
              from dws.dws_product_daily
              where stat_date >= :dt::date - interval '30 day' and stat_date <= :dt::date
              group by product_code
            ),
            sales7 as (
              select product_code, sum(net_quantity) qty7
              from dws.dws_product_daily
              where stat_date >= :dt::date - interval '7 day' and stat_date <= :dt::date
              group by product_code
            ),
            inv as (
              select product_code, sum(quantity) qty, sum(cost_amount) amount,
                     max(age_days) age_days, count(*) filter(where quantity<=0) zero_sku
              from dwd.dwd_inventory_snapshot
              where snapshot_date=(select max(snapshot_date) from dwd.dwd_inventory_snapshot where snapshot_date<=:dt::date)
              group by product_code
            )
            select p.product_code, max(p.product_name) product_name, coalesce(s7.qty7,0) qty7,
                   coalesce(s30.qty30,0) qty30, coalesce(inv.qty,0) inventory_qty,
                   coalesce(inv.amount,0) inventory_amount, inv.age_days, inv.zero_sku,
                   s30.gm
            from dim.dim_product p
            left join sales30 s30 on s30.product_code=p.product_code
            left join sales7 s7 on s7.product_code=p.product_code
            left join inv on inv.product_code=p.product_code
            group by p.product_code, s7.qty7, s30.qty30, s30.sales30, s30.gm, inv.qty, inv.amount, inv.age_days, inv.zero_sku
            order by coalesce(s7.qty7,0) desc, coalesce(inv.amount,0) desc
            limit 120
            """,
            {"dt": dt},
        )
        diagnoses = []
        hot_low = 0
        slow = 0
        for p in products:
            code = p.get("product_code")
            name = p.get("product_name") or code
            qty7 = _num(p.get("qty7"))
            qty30 = _num(p.get("qty30"))
            inv = _num(p.get("inventory_qty"))
            age = _int(p.get("age_days"))
            if qty7 >= 5 and inv <= max(3, qty7 * 0.5):
                hot_low += 1
                diagnoses.append(self._diag("product", "high", f"{name}爆款缺货风险", f"{code} 近7日销量 {qty7:.0f} 件，当前库存 {inv:.0f} 件，可售天数偏低。", [f"近7日销量：{qty7:.0f}", f"库存：{inv:.0f}", f"毛利率：{_pct(p.get('gm'))}"], "多店动销较快但库存承接不足，可能影响今日成交。", "商品部优先查尺码颜色，仓库配合跨店调拨；如供应链可承接，评估返单。", "商品经理 / 仓库主管", "今日18:00前", "明日缺货SKU数、爆款销售损失、调拨完成率", "dws_product_daily + dwd_inventory_snapshot"))
            elif inv > 20 and qty30 <= 1 and age >= 90:
                slow += 1
                diagnoses.append(self._diag("product", "medium" if age < 180 else "high", f"{name}滞销库存风险", f"{code} 库龄 {age} 天，近30日销量 {qty30:.0f} 件，库存 {inv:.0f} 件。", [f"库龄：{age}天", f"近30日销量：{qty30:.0f}", f"库存金额：{_money(p.get('inventory_amount'))}"], "商品生命周期进入清仓/死库存阶段，占用库存资金。", "商品部制定清仓或组合销售方案，弱店调出，高库龄池专项复盘。", "商品经理 / 店长", "本周内", "7日动销件数、清仓回款、库存金额下降幅度", "dim_product + dwd_inventory_snapshot"))
        warnings = [] if products else ["商品诊断暂无商品销售/库存快照数据，已降级为空诊断。"]
        return {
            "summary": {
                "stat_date": dt,
                "product_count": len(products),
                "active_product_count": sum(1 for p in products if _num(p.get("qty30")) > 0),
                "sales_qty_7d": sum(_num(p.get("qty7")) for p in products),
                "sales_qty_30d": sum(_num(p.get("qty30")) for p in products),
                "hot_low_stock_count": hot_low,
                "slow_product_count": slow,
                "stockout_product_count": sum(1 for p in products if _int(p.get("zero_sku")) > 0),
            },
            "risks": [{"name": "爆款缺货", "value": hot_low, "level": "high"}, {"name": "慢款/滞销", "value": slow, "level": "medium"}],
            "diagnoses": diagnoses[:30],
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(diagnoses[:8])],
            "data_quality": self._quality(warnings, ["售罄率/完整生命周期字段"] if products else ["商品销售或库存"], ["dim_product", "dws_product_daily", "dwd_inventory_snapshot"]),
        }

    async def inventory(self, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        dt = stat_date or await self._latest_date()
        params = {"dt": dt, "store_code": store_code}
        store_filter = "and store_code=:store_code" if store_code else ""
        summary = await self._one(
            f"""
            select coalesce(sum(total_quantity),0) total_quantity, coalesce(sum(total_cost_amount),0) total_amount,
                   coalesce(sum(age_91_180_amount),0)+coalesce(sum(age_180_plus_amount),0) age_90_amount,
                   coalesce(sum(age_180_plus_amount),0) age_180_amount,
                   coalesce(sum(negative_sku_count),0) negative_sku_count,
                   coalesce(sum(sku_count),0) sku_count
            from dws.dws_inventory_daily
            where stat_date=(select max(stat_date) from dws.dws_inventory_daily where stat_date<=:dt::date) {store_filter}
            """,
            params,
        )
        warnings_rows = await self._rows(
            f"""
            select warning_type, warning_level, store_code, product_code, sku_code,
                   current_quantity, current_cost_amount, age_days, description
            from dm.dm_inventory_warning
            where warning_date=(select max(warning_date) from dm.dm_inventory_warning where warning_date<=:dt::date)
            {store_filter}
            order by case warning_level when 'critical' then 1 when 'warning' then 2 else 3 end, current_cost_amount desc nulls last
            limit 80
            """,
            params,
        )
        diagnoses = []
        for w in warnings_rows:
            level = "high" if w.get("warning_level") == "critical" else "medium"
            wtype = w.get("warning_type") or "inventory"
            diagnoses.append(self._diag("inventory", level, f"{wtype}库存预警", w.get("description") or f"{w.get('sku_code') or w.get('product_code')} 触发库存异常。", [f"门店：{w.get('store_code') or 'ALL'}", f"SKU：{w.get('sku_code') or '-'}", f"库存：{_int(w.get('current_quantity'))}", f"金额：{_money(w.get('current_cost_amount'))}"], "库存结构与销售节奏不匹配，可能存在老库存、负库存、断码或门店压货。", "仓库与商品部复核库存，优先处理负库存和爆款断货，再处理高库龄清仓。", "仓库主管 / 商品经理", "今日18:30前", "负库存SKU数、90天以上库存金额、调拨完成率", "dm_inventory_warning"))
        if _num(summary.get("age_90_amount")) > 0:
            diagnoses.append(self._diag("inventory", "high", "90天以上库存占用资金", f"90天以上库存金额 {_money(summary.get('age_90_amount'))}，需要进入清仓池管理。", [f"总库存金额：{_money(summary.get('total_amount'))}", f"90天以上：{_money(summary.get('age_90_amount'))}", f"180天以上：{_money(summary.get('age_180_amount'))}"], "老库存持续占用现金，若不处理会影响新品采购和经营利润。", "商品部输出清仓池，财务跟踪回款，门店按清仓策略执行。", "商品经理 / 财务经理", "本周五前", "90天以上库存金额下降幅度、清仓销售额", "dws_inventory_daily"))
        warnings = [] if summary else ["库存诊断暂无库存日汇总，可能库存同步或 ETL 未完成。"]
        return {
            "summary": {
                "stat_date": dt,
                "total_inventory_qty": _int(summary.get("total_quantity")),
                "inventory_amount": _num(summary.get("total_amount")),
                "age_90_amount": _num(summary.get("age_90_amount")),
                "age_180_amount": _num(summary.get("age_180_amount")),
                "negative_sku_count": _int(summary.get("negative_sku_count")),
                "sku_count": _int(summary.get("sku_count")),
                "age_90_sku_count": sum(1 for w in warnings_rows if w.get("warning_type") in ("age_90", "age_180")),
            },
            "risks": [{"name": r.get("warning_type"), "value": r.get("sku_code") or r.get("product_code"), "level": "high" if r.get("warning_level") == "critical" else "medium"} for r in warnings_rows[:12]],
            "diagnoses": diagnoses[:40],
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(diagnoses[:10])],
            "data_quality": self._quality(warnings, ["库龄估算字段"] if not warnings_rows else [], ["dws_inventory_daily", "dm_inventory_warning"]),
        }

    async def finance(self, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        dt = stat_date or await self._latest_date()
        row = await self._one(
            """
            select coalesce(sum(net_sales),0) net_sales, coalesce(sum(cost_of_goods),0) cost_of_goods,
                   coalesce(sum(gross_profit),0) gross_profit, avg(gross_margin) gross_margin,
                   coalesce(sum(total_expense),0) total_expense, coalesce(sum(operating_profit),0) operating_profit,
                   bool_and(is_cost_complete) is_cost_complete, bool_and(is_expense_complete) is_expense_complete
            from dm.dm_finance_profit_daily
            where stat_date=:dt and (:store_code is null or store_code=:store_code or store_code='ALL')
            """,
            {"dt": dt, "store_code": store_code},
        )
        if not row or _num(row.get("net_sales")) == 0:
            row = await self._one("select * from dws.dws_finance_daily where stat_date=:dt and store_code='ALL'", {"dt": dt})
        diagnoses = []
        missing = []
        if not row:
            missing.append("财务利润日报")
        if row and not row.get("is_expense_complete"):
            missing.append("费用/固定成本")
            diagnoses.append(self._diag("finance", "medium", "利润仍为预估口径", "当前费用、房租水电或人员工资未完整接入，不能把预估利润当最终财报。", [f"净销售：{_money(row.get('net_sales') or row.get('net_sales_amount'))}", f"毛利率：{_pct(row.get('gross_margin'))}"], "成本或费用口径未完全归集，利润结论需要财务复核。", "财务补齐固定成本和费用归集，系统保留预估标识。", "财务经理", "本周内", "费用接入率、预估与核准利润差异", "dm_finance_profit_daily / dws_finance_daily"))
        if row and _num(row.get("gross_margin")) > 0 and _num(row.get("gross_margin")) < 0.45:
            diagnoses.append(self._diag("finance", "high", "毛利率偏低风险", f"当前毛利率 {_pct(row.get('gross_margin'))}，低于男装经营预警线。", [f"毛利：{_money(row.get('gross_profit'))}", f"销售成本：{_money(row.get('cost_of_goods') or row.get('cost_amount'))}"], "折扣、商品结构或成本归集可能拉低利润。", "商品与财务复核高折扣订单、低毛利款和成本完整性。", "财务经理 / 商品经理", "今日下班前", "毛利率、异常折扣订单数、低毛利款销售占比", "dm_finance_profit_daily"))
        return {
            "summary": {
                "stat_date": dt,
                "net_sales": _num(row.get("net_sales") or row.get("net_sales_amount")),
                "cost_of_goods": _num(row.get("cost_of_goods") or row.get("cost_amount")),
                "gross_profit": _num(row.get("gross_profit")),
                "gross_margin": _num(row.get("gross_margin")),
                "total_expense": _num(row.get("total_expense")),
                "operating_profit": _num(row.get("operating_profit") or row.get("operating_profit_estimate")),
                "finance_risk_count": len(diagnoses),
            },
            "risks": [{"name": d["title"], "value": d["level_label"], "level": d["level"]} for d in diagnoses],
            "diagnoses": diagnoses,
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(diagnoses)],
            "data_quality": self._quality(["财务诊断为预估口径，需财务核准后作为最终结论。"] if missing else [], missing, ["dm_finance_profit_daily", "dws_finance_daily"]),
        }

    async def hr(self, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        dt = stat_date or await self._latest_date()
        stores = await self._rows(
            """
            select s.store_code, coalesce(ds.store_name,s.store_code) store_name, s.net_sales_amount,
                   nullif(count(e.id),0) employee_count,
                   case when count(e.id)>0 then s.net_sales_amount/count(e.id) end sales_per_employee
            from dws.dws_store_daily s
            left join dim.dim_store ds on ds.store_code=s.store_code
            left join dim.dim_employee e on e.store_code=s.store_code and e.status='active'
            where s.stat_date=:dt and (:store_code is null or s.store_code=:store_code)
            group by s.store_code, ds.store_name, s.net_sales_amount
            order by sales_per_employee nulls last
            limit 80
            """,
            {"dt": dt, "store_code": store_code},
        )
        valid = [s for s in stores if s.get("sales_per_employee") is not None]
        avg = sum(_num(s.get("sales_per_employee")) for s in valid) / len(valid) if valid else 0
        diagnoses = []
        for s in valid[:20]:
            spe = _num(s.get("sales_per_employee"))
            if avg > 0 and spe < avg * 0.75:
                name = s.get("store_name") or s.get("store_code")
                diagnoses.append(self._diag("hr", "medium", f"{name}人效偏低", f"{name} 人均销售 {_money(spe)}，低于公司均值 {_money(avg)}。", [f"门店销售：{_money(s.get('net_sales_amount'))}", f"在岗人数：{_int(s.get('employee_count'))}", f"人均销售：{_money(spe)}"], "可能是人员排班与销售节奏不匹配，或导购执行、会员回访不足。", "运营经理复盘排班、会员回访和导购成交动作；若任务完成率低，纳入干部执行力复盘。", "运营经理 / 店长", "今日21:00前", "明日人均销售、订单数、会员回访完成率", "dws_store_daily + dim_employee"))
        return {
            "summary": {
                "stat_date": dt,
                "employee_count": sum(_int(s.get("employee_count")) for s in valid),
                "avg_sales_per_employee": avg,
                "low_efficiency_store_count": len(diagnoses),
                "task_completion_rate": None,
            },
            "risks": [{"name": d["title"], "value": d["level_label"], "level": d["level"]} for d in diagnoses[:8]],
            "diagnoses": diagnoses,
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(diagnoses[:8])],
            "data_quality": self._quality(["当前人力诊断主要基于销售、人均产出和员工档案；考勤、排班、工资数据暂未完整接入。"], ["考勤/排班/工资"], ["dws_store_daily", "dim_employee"]),
        }

    async def members(self, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        dt = stat_date or await self._latest_date()
        row = await self._one(
            """
            select count(*) as visit_count,
                   count(*) filter(where visit_status='pending') pending_count,
                   count(*) filter(where is_converted=true) converted_count,
                   coalesce(sum(conversion_amount),0) conversion_amount
            from dm.dm_member_visit_list
            where visit_date=:dt and (:store_code is null or store_code=:store_code)
            """,
            {"dt": dt, "store_code": store_code},
        )
        diagnoses = []
        if _int(row.get("pending_count")) > 0:
            diagnoses.append(self._diag("member", "medium", "会员回访待执行", f"今日仍有 {_int(row.get('pending_count'))} 条会员回访建议待处理。", [f"今日回访名单：{_int(row.get('visit_count'))}", f"待处理：{_int(row.get('pending_count'))}", f"已成交金额：{_money(row.get('conversion_amount'))}"], "会员复购机会需要导购跟进，否则销售机会会自然流失。", "店长分配导购回访，优先处理高价值/沉睡/生日会员。", "店长 / 导购", "今日20:30前", "回访完成率、回访成交金额、会员复购率", "dm_member_visit_list"))
        return {
            "summary": {"stat_date": dt, "visit_count": _int(row.get("visit_count")), "pending_visit_count": _int(row.get("pending_count")), "converted_count": _int(row.get("converted_count")), "conversion_amount": _num(row.get("conversion_amount"))},
            "risks": [{"name": "待回访会员", "value": _int(row.get("pending_count")), "level": "medium"}],
            "diagnoses": diagnoses,
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(diagnoses)],
            "data_quality": self._quality(["会员诊断依赖会员档案、消费偏好和回访明细；若百胜会员数据未同步，结论会偏保守。"], ["会员偏好/手机号按权限脱敏"], ["dm_member_visit_list", "dim_member"]),
        }

    async def audit(self, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        dt = stat_date or await self._latest_date()
        rows = await self._rows(
            """
            select exception_type, severity, store_code, product_code, sku_code, order_no, description, data_snapshot
            from dm.dm_exception_audit
            where audit_date=:dt and (:store_code is null or store_code=:store_code)
            order by case severity when 'critical' then 1 when 'warning' then 2 else 3 end
            limit 80
            """,
            {"dt": dt, "store_code": store_code},
        )
        diagnoses = []
        for r in rows:
            level = "high" if r.get("severity") == "critical" else "medium"
            obj = r.get("order_no") or r.get("sku_code") or r.get("product_code") or r.get("store_code") or "经营对象"
            diagnoses.append(self._diag("audit", level, f"{r.get('exception_type')}异常", r.get("description") or f"{obj} 触发异常稽核。", [f"对象：{obj}", f"门店：{r.get('store_code') or '-'}"], "可能存在折扣、退款、负库存、低毛利或数据同步异常，需要人工复核。", "责任部门复核单据与审批记录，必要时补充说明并转行动任务。", "财务经理 / 仓库主管 / 运营经理", "今日18:00前", "异常是否关闭、复核记录、同类异常是否复发", "dm_exception_audit"))
        return {
            "summary": {"stat_date": dt, "audit_count": len(rows), "high_count": sum(1 for d in diagnoses if d["level"] == "high")},
            "risks": [{"name": d["title"], "value": d["level_label"], "level": d["level"]} for d in diagnoses[:12]],
            "diagnoses": diagnoses,
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(diagnoses[:10])],
            "data_quality": self._quality([] if rows else ["异常稽核暂无记录；如销售/库存已有同步但这里为空，需要确认稽核规则任务是否运行。"], [], ["dm_exception_audit"]),
        }

    async def action_tasks(self, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        dt = stat_date or await self._latest_date()
        overview = await self.overview(dt, store_code)
        tasks = overview.get("action_suggestions", [])
        existing = await self._rows(
            """
            select task_no, source_type task_source, title problem_type, description, assignee_name owner,
                   due_date::text deadline, risk_level priority, status, feedback_requirement
            from app.app_action_task
            where is_deleted=false and related_date=:dt
            order by priority desc, due_date asc nulls last
            limit 50
            """,
            {"dt": dt},
        )
        return {
            "summary": {"stat_date": dt, "suggestion_count": len(tasks), "existing_task_count": len(existing), "overdue_count": await self._overdue_task_count(dt)},
            "risks": [{"name": "建议任务", "value": len(tasks), "level": "medium"}, {"name": "正式任务", "value": len(existing), "level": "low"}],
            "diagnoses": overview.get("diagnoses", []),
            "action_suggestions": existing + tasks,
            "data_quality": self._quality(["第一阶段仅生成建议任务，不自动派发；正式派发需人工确认。"], [], ["app_action_task", "AI diagnosis rules"]),
        }

    async def module(self, module: str, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        mapping = {
            "overview": self.overview,
            "sales": self.sales,
            "products": self.products,
            "inventory": self.inventory,
            "hr": self.hr,
            "finance": self.finance,
            "members": self.members,
            "audit": self.audit,
            "action-tasks": self.action_tasks,
            "actions": self.action_tasks,
        }
        fn = mapping.get(module, self.overview)
        return await fn(stat_date, store_code)
