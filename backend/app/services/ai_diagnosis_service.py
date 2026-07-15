from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
import logging
import json
import hashlib
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.store_whitelist import ALLOWED_STORE_CODES
from app.services.ai_engine import build_template_command_conclusion, sanitize_command_context


logger = logging.getLogger(__name__)

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


def _can_assert_operating_profit(row: dict[str, Any] | None) -> bool:
    """Only approved, fully covered profit data may support a profit/loss claim."""
    if not row or row.get("operating_profit") is None:
        return False
    return all(bool(row.get(key)) for key in (
        "is_cost_complete", "is_expense_complete", "finance_approved",
    ))


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(_num(value, default))
    except Exception:
        return default




def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        return date.fromisoformat(str(value)[:10])
    return date.today() - timedelta(days=1)

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


def _is_expense_sync_covered(last_sync_at: Any, dt: date, now: Optional[datetime] = None) -> bool:
    if not last_sync_at:
        return False
    sync_at = last_sync_at if isinstance(last_sync_at, datetime) else datetime.fromisoformat(str(last_sync_at))
    if sync_at.tzinfo is None:
        sync_at = sync_at.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return current - sync_at <= timedelta(hours=36) and sync_at.date() - dt <= timedelta(days=30) and dt <= sync_at.date()


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
            await self.db.rollback()
            logger.exception("AI diagnosis query failed")
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
        return _as_date(row.get("dt") or (date.today() - timedelta(days=1)))

    async def _common_metrics(self, dt: date, store_code: Optional[str] = None) -> dict:
        params = {"dt": dt, "store_code": store_code or ""}
        sales = await self._one(
            """
            select coalesce(sum(net_sales_amount),0) net_sales,
                   coalesce(sum(gross_profit),0) gross_profit,
                   case when sum(net_sales_amount)<>0 then sum(gross_profit)/sum(net_sales_amount) end gross_margin,
                   count(*) source_row_count,
                   bool_and(coalesce(is_cost_complete,false)) is_cost_complete
            from dws.dws_store_daily
            where stat_date=:dt and (:store_code='' or store_code=:store_code)
            """, params)
        orders = await self._one(
            """
            select count(distinct ticket_no) order_count, count(*) source_row_count
            from dwd.dwd_pos_ticket
            where biz_date=:dt and (:store_code='' or store_code=:store_code)
              and coalesce(is_void,false)=false and coalesce(is_pending,false)=false
            """, params)
        source_ready = _int(sales.get("source_row_count")) > 0
        order_ready = _int(orders.get("source_row_count")) > 0
        gross_profit_status = (
            "ready" if bool(sales.get("is_cost_complete")) else "estimated"
        ) if source_ready else "pending_data"
        gross_margin_status = (
            gross_profit_status if sales.get("gross_margin") is not None else "pending_data"
        )
        return {
            "net_sales": _num(sales.get("net_sales")),
            "order_count": _int(orders.get("order_count")),
            "gross_profit": _num(sales.get("gross_profit")),
            "gross_margin": sales.get("gross_margin"),
            "_metric_status": {
                "net_sales": "ready" if source_ready else "pending_data",
                "order_count": "ready" if order_ready else "pending_data",
                "gross_profit": gross_profit_status,
                "gross_margin": gross_margin_status,
            },
        }

    def _quality(
        self,
        warnings: list[str],
        missing: list[str],
        source_tables: list[str],
        metric_status: Optional[dict[str, str]] = None,
    ) -> dict:
        return {
            "is_complete": len(warnings) == 0 and len(missing) == 0,
            "missing_fields": missing,
            "warnings": warnings,
            "source_tables": source_tables,
            "metric_status": metric_status or {},
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def command_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        summary = payload.get("summary") or {}
        quality = payload.get("data_quality") or {}
        sources = quality.get("source_tables") or ["diagnosis_service"]
        source = " / ".join(str(item) for item in sources)
        metric_map = {
            "sales_amount": "net_sales",
            "order_count": "order_count",
            "item_count": "item_count",
            "avg_order_value": "avg_order_value",
            "items_per_order": "items_per_order",
            "gross_profit": "gross_profit",
            "gross_margin": "gross_margin",
            "inventory_amount": "inventory_amount",
            "age_90_plus_amount": "age_90_amount",
            "vip_sales": "member_sales_amount",
            "operating_profit": "operating_profit",
        }
        metrics = {}
        missing = set(quality.get("missing_fields") or [])
        warnings = quality.get("warnings") or []
        metric_status = {
            **(summary.get("_metric_status", {}) or {}),
            **(quality.get("metric_status") or {}),
        }
        for command_key, summary_key in metric_map.items():
            if summary_key not in summary:
                continue
            status = metric_status.get(summary_key) or metric_status.get(command_key)
            if not status:
                status = "pending_data" if summary_key in missing or not quality.get("is_complete", True) else "ready"
            metrics[command_key] = {
                "value": summary.get(summary_key),
                "status": status,
                "source": source,
                "as_of": summary.get("stat_date") or summary.get("inventory_stat_date"),
            }
        rules = [{
            "id": item.get("id"),
            "title": item.get("title"),
            "level": item.get("level"),
            "evidence": item.get("evidence") or [],
            "source": item.get("data_source") or "diagnosis_rules",
        } for item in payload.get("diagnoses") or []]
        finance_complete = bool(summary.get("finance_complete"))
        return sanitize_command_context({
            "metrics": metrics,
            "rules": rules,
            "tasks": payload.get("action_suggestions") or [],
            "finance_complete": finance_complete,
        })

    def _attach_command_conclusion(self, payload: dict[str, Any]) -> dict[str, Any]:
        safe_context = self.command_context(payload)
        payload["command_conclusion"] = {
            **build_template_command_conclusion(safe_context),
            "mode": "template",
            "model_used": "deterministic_rules",
        }
        return payload

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
        identity = hashlib.sha256(f"{module}|{title}|{description}".encode("utf-8")).hexdigest()[:16]
        return {
            "id": f"{module}-{identity}",
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
            "diagnosis_id": diag.get("id"),
            "module": diag.get("module"),
            "task_no": f"AI-{datetime.now():%Y%m%d}-{idx:03d}",
            "task_source": "AI经营诊断",
            "problem_type": diag.get("title"),
            "description": diag.get("description"),
            "evidence": diag.get("evidence") or [],
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
        dt = _as_date(stat_date or await self._latest_date())
        company = await self._one("select * from dws.dws_company_daily where stat_date=:dt", {"dt": dt})
        if not company:
            company = await self._one("select * from dm.dm_boss_daily_report where report_date=:dt", {"dt": dt})

        sales = await self.sales(dt, store_code)
        products = await self.products(dt, store_code)
        inventory = await self.inventory(dt, store_code)
        hr = await self.hr(dt, store_code)
        finance = await self.finance(dt, store_code)
        audit = await self.audit(dt, store_code)
        overview_metrics = sales.get("summary", {}) if store_code else company

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

        payload = {
            "summary": {
                "stat_date": dt,
                "health_score": score,
                "sales_health": self._risk_label(sales),
                "product_health": self._risk_label(products),
                "inventory_health": self._risk_label(inventory),
                "hr_health": self._risk_label(hr),
                "finance_health": self._risk_label(finance),
                "net_sales": _num(overview_metrics.get("net_sales_amount") or overview_metrics.get("net_sales")),
                "order_count": _int(overview_metrics.get("total_order_count") or overview_metrics.get("order_count")),
                "gross_margin": _num(overview_metrics.get("gross_margin")),
                "ai_summary": summary_text,
            },
            "risks": risks,
            "diagnoses": top3,
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(top3)],
            "data_quality": self._quality(
                warnings,
                sorted(set(missing)),
                ["dws_company_daily", "dws_store_daily", "dws_inventory_daily", "dm_*"],
                metric_status={
                    "net_sales": sales.get("data_quality", {}).get("metric_status", {}).get("net_sales", "pending_data"),
                    "order_count": sales.get("data_quality", {}).get("metric_status", {}).get("order_count", "pending_data"),
                    "gross_margin": sales.get("data_quality", {}).get("metric_status", {}).get("gross_margin", "pending_data"),
                },
            ),
        }
        return self._attach_command_conclusion(payload)

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
        dt = _as_date(stat_date or await self._latest_date())
        params = {"dt": dt, "store_code": store_code or ""}
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
              bool_and(coalesce(s.is_cost_complete,false)) is_cost_complete,
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
              where stat_date < CAST(:dt AS date) and stat_date >= CAST(:dt AS date) - interval '7 day'
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
        ticket_source = await self._one(
            """
            select count(*) source_row_count
            from dwd.dwd_pos_ticket
            where biz_date=:dt and (:store_code='' or store_code=:store_code)
              and coalesce(is_void,false)=false and coalesce(is_pending,false)=false
            """,
            params,
        )
        target = await self._one(
            """
            select coalesce(sum(target_amount),0) target_amount,
                   coalesce(sum(actual_amount),0) actual_amount,
                   case when sum(target_amount)>0 then sum(actual_amount)/sum(target_amount) else 0 end achievement_rate
            from (
              select distinct on (store_code) store_code,target_amount,actual_amount
              from dws.dws_store_target_monthly
              where month_date=date_trunc('month',CAST(:dt AS date))::date
                and snapshot_date<=CAST(:dt AS date)
                and (:store_code='' or store_code=:store_code)
              order by store_code,snapshot_date desc
            ) target_snapshot
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
        sales_source_ready = bool(stores)
        order_source_ready = _int(ticket_source.get("source_row_count")) > 0
        gross_status = (
            "ready" if bool(summary.get("is_cost_complete")) else "estimated"
        ) if sales_source_ready and summary.get("gross_margin") is not None else "pending_data"
        target_rate = _num(target.get("achievement_rate"))
        health_score = max(0, 100 - len([d for d in diagnoses if d.get("level")=="high"])*12 - len([d for d in diagnoses if d.get("level")=="medium"])*6)
        return {
            "summary": {
                "stat_date": dt,
                "health_score": health_score,
                "net_sales": _num(summary.get("net_sales")),
                "order_count": _int(summary.get("order_count")),
                "item_count": _int(summary.get("item_count")),
                "avg_order_value": _num(summary.get("avg_order_value")),
                "items_per_order": _num(summary.get("items_per_order")),
                "gross_margin": _num(summary.get("gross_margin")),
                "return_rate": _num(summary.get("return_rate")),
                "risk_store_count": _int(summary.get("risk_store_count")),
                "monthly_target_amount": _num(target.get("target_amount")),
                "monthly_actual_amount": _num(target.get("actual_amount")),
                "monthly_achievement_rate": target_rate,
            },
            "risks": self._store_rank_risks(stores),
            "diagnoses": diagnoses[:30],
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(diagnoses[:8])],
            "data_quality": self._quality(
                warnings,
                ["同比数据"] if stores else ["门店销售汇总"],
                ["dws_store_daily", "dim_store", "dws_store_target_monthly"],
                metric_status={
                    "net_sales": "ready" if sales_source_ready else "pending_data",
                    "order_count": "ready" if order_source_ready else "pending_data",
                    "item_count": "ready" if sales_source_ready else "pending_data",
                    "avg_order_value": "ready" if sales_source_ready else "pending_data",
                    "items_per_order": "ready" if sales_source_ready else "pending_data",
                    "gross_margin": gross_status,
                },
            ),
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
        dt = _as_date(stat_date or await self._latest_date())
        products = await self._rows(
            """
            with sales30 as (
              select product_code, sum(net_quantity) qty30, sum(net_sales_amount) sales30, avg(gross_margin) gm
              from dws.dws_product_daily
              where stat_date >= CAST(:dt AS date) - interval '30 day' and stat_date <= CAST(:dt AS date)
              group by product_code
            ),
            sales7 as (
              select product_code, sum(net_quantity) qty7
              from dws.dws_product_daily
              where stat_date >= CAST(:dt AS date) - interval '7 day' and stat_date <= CAST(:dt AS date)
              group by product_code
            ),
            standard_price as (
              select product_code, color_code, size_code,
                     max(standard_purchase_price) standard_purchase_price
              from dim.v_baison_sku_standard_purchase_price
              group by product_code, color_code, size_code
            ),
            inv as (
              select i.product_code, sum(i.qty) qty,
                     coalesce(sum(i.qty * sp.standard_purchase_price)
                              filter(where sp.standard_purchase_price is not null),0) amount,
                     count(*) filter(where i.qty<=0) zero_sku
              from dwd.v_apparel_inventory_balance i
              left join standard_price sp
                on sp.product_code=i.product_code
               and trim(leading '-' from sp.color_code)=trim(leading '-' from coalesce(i.color_code,''))
               and sp.size_code=coalesce(i.size_code,'')
              group by i.product_code
            ),
            inbound30 as (
              select product_code, sum(quantity) inbound_quantity_30d
              from dwd.dwd_baison_purchase_inbound
              where record_date >= CAST(:dt AS date) - interval '29 day' and record_date <= CAST(:dt AS date)
              group by product_code
            )
            select p.product_code, max(p.product_name) product_name, coalesce(s7.qty7,0) qty7,
                   coalesce(s30.qty30,0) qty30, coalesce(inv.qty,0) inventory_qty,
                   coalesce(inv.amount,0) inventory_amount,
                   greatest(coalesce(CAST(:dt AS date) - p.launch_date,0),
                            coalesce(CAST(:dt AS date) - inbound.first_inbound_date,0)) age_days,
                   inv.zero_sku, s30.gm, inbound.first_inbound_date, inbound.last_inbound_date,
                   coalesce(inbound.total_inbound_quantity,0) total_inbound_quantity,
                   coalesce(in30.inbound_quantity_30d,0) inbound_quantity_30d,
                   coalesce(inbound.last_purchase_price,0) last_purchase_price,
                   coalesce(inbound.receipt_count,0) receipt_count
            from dim.dim_product p
            left join sales30 s30 on s30.product_code=p.product_code
            left join sales7 s7 on s7.product_code=p.product_code
            left join inv on inv.product_code=p.product_code
            left join dws.dws_product_inbound_summary inbound on inbound.product_code=p.product_code
            left join inbound30 in30 on in30.product_code=p.product_code
            group by p.product_code, s7.qty7, s30.qty30, s30.sales30, s30.gm, inv.qty, inv.amount,
                     p.launch_date, inv.zero_sku, inbound.first_inbound_date, inbound.last_inbound_date,
                     inbound.total_inbound_quantity, in30.inbound_quantity_30d,
                     inbound.last_purchase_price, inbound.receipt_count
            order by coalesce(s7.qty7,0) desc, coalesce(inv.amount,0) desc
            limit 120
            """,
            {"dt": dt},
        )
        product_summary = await self._one(
            """
            with company as (
              select coalesce(sum(net_sales_amount),0) net_sales,
                     coalesce(sum(total_order_count),0) order_count,
                     case when sum(net_sales_amount)>0 then sum(gross_profit)/sum(net_sales_amount) end gross_margin,
                     count(*) sales_source_row_count,
                     bool_and(coalesce(is_cost_complete,false)) is_cost_complete
              from dws.dws_company_daily where stat_date=CAST(:dt AS date)
            ), sales30 as (
              select product_code, sum(net_quantity) qty30
              from dws.dws_product_daily
              where stat_date between CAST(:dt AS date)-interval '29 day' and CAST(:dt AS date)
              group by product_code
            ), sales7 as (
              select product_code, sum(net_quantity) qty7
              from dws.dws_product_daily
              where stat_date between CAST(:dt AS date)-interval '6 day' and CAST(:dt AS date)
              group by product_code
            ), inv as (
              select product_code, sum(qty) inventory_qty,
                     count(*) filter(where qty<=0) zero_sku
              from dwd.v_apparel_inventory_balance group by product_code
            ), inbound as (
              select product_code, first_inbound_date from dws.dws_product_inbound_summary
            ), inbound30 as (
              select product_code, sum(quantity) inbound_qty30
              from dwd.dwd_baison_purchase_inbound
              where record_date between CAST(:dt AS date)-interval '29 day' and CAST(:dt AS date)
              group by product_code
            ), participating as (
              select product_code from sales30 union select product_code from inv union select product_code from inbound
            ), base as (
              select x.product_code, coalesce(s30.qty30,0) qty30, coalesce(s7.qty7,0) qty7,
                     coalesce(inv.inventory_qty,0) inventory_qty, coalesce(inv.zero_sku,0) zero_sku,
                     coalesce(i30.inbound_qty30,0) inbound_qty30, inbound.first_inbound_date,
                     greatest(coalesce(CAST(:dt AS date)-p.launch_date,0),
                              coalesce(CAST(:dt AS date)-inbound.first_inbound_date,0)) age_days
              from participating x
              left join dim.dim_product p on p.product_code=x.product_code
              left join sales30 s30 on s30.product_code=x.product_code
              left join sales7 s7 on s7.product_code=x.product_code
              left join inv on inv.product_code=x.product_code
              left join inbound on inbound.product_code=x.product_code
              left join inbound30 i30 on i30.product_code=x.product_code
            ), metrics as (
              select count(*) product_count,
                     count(*) filter(where qty30>0) active_product_count,
                     coalesce(sum(qty7),0) sales_qty_7d, coalesce(sum(qty30),0) sales_qty_30d,
                     coalesce(sum(inbound_qty30),0) inbound_qty_30d,
                     count(*) filter(where first_inbound_date is not null) inbound_product_count,
                     count(*) filter(where inventory_qty>0 and age_days>=90) aged_inventory_product_count,
                     count(*) filter(where qty7>=5 and inventory_qty<=greatest(3,qty7*0.5)) hot_low_stock_count,
                     count(*) filter(where inventory_qty>20 and qty30<=1 and age_days>=90) slow_product_count,
                     count(*) filter(where qty30>0 and inventory_qty<=0) stockout_product_count
              from base
            )
            select company.*, metrics.* from company cross join metrics
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
                diagnoses.append(self._diag("product", "high", f"{name}爆款缺货风险", f"{code} 近7日销量 {qty7:.0f} 件，当前库存 {inv:.0f} 件，可售天数偏低。", [f"近7日销量：{qty7:.0f}", f"库存：{inv:.0f}", f"毛利率：{_pct(p.get('gm'))}"], "多店动销较快但库存承接不足，可能影响今日成交。", "商品部优先查尺码颜色，仓库配合跨店调拨；如供应链可承接，评估返单。", "商品经理 / 仓库主管", "今日18:00前", "明日缺货SKU数、爆款销售损失、调拨完成率", "dws_product_daily + dwd_inventory_balance"))
            elif inv > 20 and qty30 <= 1 and age >= 90:
                slow += 1
                first_inbound = p.get("first_inbound_date") or "未覆盖"
                last_inbound = p.get("last_inbound_date") or "未覆盖"
                diagnoses.append(self._diag("product", "medium" if age < 180 else "high", f"{name}滞销库存风险", f"{code} 库龄 {age} 天，近30日销量 {qty30:.0f} 件，库存 {inv:.0f} 件。", [f"首次入库：{first_inbound}", f"最近入库：{last_inbound}", f"库龄：{age}天", f"近30日销量：{qty30:.0f}", f"库存金额：{_money(p.get('inventory_amount'))}", f"最近采购价：{_money(p.get('last_purchase_price'))}"], "商品生命周期进入清仓/死库存阶段，占用库存资金。", "商品部制定清仓或组合销售方案，弱店调出，高库龄池专项复盘。", "商品经理 / 店长", "本周内", "7日动销件数、清仓回款、库存金额下降幅度", "dim_product + dwd_inventory_balance + dws_product_inbound_summary"))
        warnings = [] if products else ["商品诊断暂无商品销售/库存快照数据，已降级为空诊断。"]
        summary_hot_low = _int(product_summary.get("hot_low_stock_count"))
        summary_slow = _int(product_summary.get("slow_product_count"))
        summary_stockout = _int(product_summary.get("stockout_product_count"))
        health_score = product_summary.get("health_score")
        if health_score is None:
            product_count = max(_int(product_summary.get("product_count")), 1)
            active_count = max(_int(product_summary.get("active_product_count")), 1)
            hot_penalty = min(30, summary_hot_low * 2)
            slow_penalty = min(25, summary_slow / product_count * 500)
            stockout_penalty = min(35, summary_stockout / active_count * 100)
            health_score = round(max(0, 100 - hot_penalty - slow_penalty - stockout_penalty))
        return {
            "summary": {
                "stat_date": dt,
                "health_score": _int(health_score),
                "net_sales": _num(product_summary.get("net_sales")),
                "order_count": _int(product_summary.get("order_count")),
                "gross_margin": _num(product_summary.get("gross_margin")),
                "product_count": _int(product_summary.get("product_count")),
                "active_product_count": _int(product_summary.get("active_product_count")),
                "sales_qty_7d": _num(product_summary.get("sales_qty_7d")),
                "sales_qty_30d": _num(product_summary.get("sales_qty_30d")),
                "inbound_qty_30d": _num(product_summary.get("inbound_qty_30d")),
                "inbound_product_count": _int(product_summary.get("inbound_product_count")),
                "aged_inventory_product_count": _int(product_summary.get("aged_inventory_product_count")),
                "hot_low_stock_count": summary_hot_low,
                "slow_product_count": summary_slow,
                "stockout_product_count": summary_stockout,
            },
            "risks": [{"name": "爆款缺货", "value": summary_hot_low, "level": "high"}, {"name": "慢款/滞销", "value": summary_slow, "level": "medium"}],
            "diagnoses": diagnoses[:30],
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(diagnoses[:8])],
            "data_quality": self._quality(
                warnings,
                ["百胜入库历史当前回溯730天"] if products else ["商品销售、库存或进货"],
                ["dim_product", "dws_product_daily", "dwd_inventory_balance", "dwd_baison_purchase_inbound", "dws_product_inbound_summary"],
                metric_status={
                    "net_sales": "ready" if _int(product_summary.get("sales_source_row_count")) > 0 else "pending_data",
                    "order_count": "ready" if _int(product_summary.get("sales_source_row_count")) > 0 else "pending_data",
                    "gross_margin": (
                        "ready" if bool(product_summary.get("is_cost_complete")) else "estimated"
                    ) if _int(product_summary.get("sales_source_row_count")) > 0 and product_summary.get("gross_margin") is not None else "pending_data",
                },
            ),
        }

    async def inventory(self, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        dt = _as_date(stat_date or await self._latest_date())
        params = {"dt": dt, "store_code": store_code or ""}
        store_filter = "and store_code=:store_code" if store_code else ""
        balance_store_filter = "and i.warehouse_code=:store_code" if store_code else ""
        summary = await self._one(
            f"""
            with company as (
              select coalesce(sum(net_sales_amount),0) net_sales,
                     coalesce(sum(order_count),0) order_count,
                     case when sum(net_sales_amount)>0 then sum(gross_profit)/sum(net_sales_amount) end gross_margin,
                     count(*) sales_source_row_count,
                     bool_and(coalesce(is_cost_complete,false)) is_cost_complete
              from dws.dws_store_daily
              where stat_date=CAST(:dt AS date) and (:store_code='' or store_code=:store_code)
            ), standard_price as (
              select product_code, color_code, size_code,
                     max(standard_purchase_price) standard_purchase_price
              from dim.v_baison_sku_standard_purchase_price
              group by product_code, color_code, size_code
            ), lines as (
              select i.warehouse_code store_code, i.product_code,
                     coalesce(nullif(i.sku_code,''),concat(i.product_code,trim(leading '-' from coalesce(i.color_code,'')),coalesce(i.size_code,''))) sku_code,
                     i.qty,
                     sp.standard_purchase_price,
                     greatest(coalesce(CAST(:dt AS date)-p.launch_date,0),
                              coalesce(CAST(:dt AS date)-inbound.first_inbound_date,0)) age_days,
                     i.synced_at
              from dwd.v_apparel_inventory_balance i
              left join standard_price sp
                on sp.product_code=i.product_code
               and trim(leading '-' from sp.color_code)=trim(leading '-' from coalesce(i.color_code,''))
               and sp.size_code=coalesce(i.size_code,'')
              left join dim.dim_product p on p.product_code=i.product_code
              left join dws.dws_product_inbound_summary inbound on inbound.product_code=i.product_code
              where true {balance_store_filter}
            )
            select max((lines.synced_at at time zone 'Asia/Shanghai')::date) inventory_stat_date,
                   coalesce(sum(greatest(lines.qty,0)),0) total_quantity,
                   coalesce(sum(greatest(lines.qty,0)*lines.standard_purchase_price)
                            filter(where lines.standard_purchase_price is not null),0) total_amount,
                   coalesce(sum(greatest(lines.qty,0))
                            filter(where lines.standard_purchase_price is null),0)
                     missing_standard_purchase_price_qty,
                   coalesce(sum(greatest(lines.qty,0))
                            filter(where lines.standard_purchase_price is not null),0)
                     priced_standard_purchase_price_qty,
                   coalesce(sum(greatest(lines.qty,0)*lines.standard_purchase_price)
                            filter(where age_days>=90 and lines.standard_purchase_price is not null),0) age_90_amount,
                   coalesce(sum(greatest(lines.qty,0)*lines.standard_purchase_price)
                            filter(where age_days>=180 and lines.standard_purchase_price is not null),0) age_180_amount,
                   count(distinct (store_code,sku_code)) filter(where qty<0) negative_sku_count,
                   count(distinct (store_code,sku_code)) filter(where qty<>0) sku_count,
                   count(distinct (store_code,sku_code)) filter(where qty>0 and age_days>=90) age_90_sku_count,
                   company.net_sales, company.order_count, company.gross_margin,
                   company.sales_source_row_count, company.is_cost_complete
            from lines cross join company
            group by company.net_sales,company.order_count,company.gross_margin,company.sales_source_row_count,company.is_cost_complete
            """,
            params,
        )
        warnings_rows = await self._rows(
            f"""
            with standard_price as (
              select product_code, color_code, size_code,
                     max(standard_purchase_price) standard_purchase_price
              from dim.v_baison_sku_standard_purchase_price
              group by product_code, color_code, size_code
            ), lines as (
              select i.warehouse_code store_code, i.product_code,
                     coalesce(nullif(i.sku_code,''),concat(i.product_code,trim(leading '-' from coalesce(i.color_code,'')),coalesce(i.size_code,''))) sku_code,
                     i.qty,
                     sp.standard_purchase_price,
                     greatest(coalesce(CAST(:dt AS date)-p.launch_date,0),
                              coalesce(CAST(:dt AS date)-inbound.first_inbound_date,0)) age_days
              from dwd.v_apparel_inventory_balance i
              left join standard_price sp
                on sp.product_code=i.product_code
               and trim(leading '-' from sp.color_code)=trim(leading '-' from coalesce(i.color_code,''))
               and sp.size_code=coalesce(i.size_code,'')
              left join dim.dim_product p on p.product_code=i.product_code
              left join dws.dws_product_inbound_summary inbound on inbound.product_code=i.product_code
              where true {balance_store_filter}
            ), sku_inventory as (
              select store_code,product_code,sku_code,sum(qty) current_quantity,
                     sum(qty*standard_purchase_price)
                       filter(where standard_purchase_price is not null) current_cost_amount,
                     max(age_days) age_days
              from lines group by store_code,product_code,sku_code
            ), realtime_warning as (
              select 'negative' warning_type,'critical' warning_level,store_code,product_code,sku_code,
                     current_quantity,current_cost_amount,age_days,
                     case when current_cost_amount is null
                          then concat('当前库存 ',current_quantity,' 件，标准进价缺失；请先补价并复核同步、调拨或销售出库。')
                          else concat('当前库存 ',current_quantity,' 件，请复核同步、调拨或销售出库。') end description
              from sku_inventory where current_quantity<0
              union all
              select case when age_days>=180 then 'age_180' else 'age_90' end,
                     case when age_days>=180 then 'critical' else 'warning' end,
                     store_code,product_code,sku_code,current_quantity,current_cost_amount,age_days,
                     case when current_cost_amount is null
                          then concat('库龄 ',age_days,' 天，库存 ',current_quantity,' 件，金额待补标准进价。')
                          else concat('库龄 ',age_days,' 天，库存 ',current_quantity,' 件，金额 ',round(current_cost_amount,2),' 元。') end
              from sku_inventory where current_quantity>0 and age_days>=90
            )
            select * from realtime_warning
            order by case warning_level when 'critical' then 1 when 'warning' then 2 else 3 end,
                     current_cost_amount desc nulls last
            limit 80
            """,
            params,
        )
        diagnoses = []
        for w in warnings_rows:
            level = "high" if w.get("warning_level") == "critical" else "medium"
            wtype = w.get("warning_type") or "inventory"
            warning_name = {"negative": "负库存", "age_90": "90天以上老库存", "age_180": "180天以上老库存"}.get(wtype, "库存异常")
            amount_evidence = (
                f"金额：{_money(w.get('current_cost_amount'))}"
                if w.get("current_cost_amount") is not None
                else "金额：待补标准进价"
            )
            diagnoses.append(self._diag("inventory", level, warning_name, w.get("description") or f"{w.get('sku_code') or w.get('product_code')} 触发库存异常。", [f"门店：{w.get('store_code') or 'ALL'}", f"SKU：{w.get('sku_code') or '-'}", f"库存：{_int(w.get('current_quantity'))}", amount_evidence], "库存结构与销售节奏不匹配，可能存在老库存、负库存、断码或门店压货。", "仓库与商品部复核库存，优先处理负库存和爆款断货，再处理高库龄清仓。", "仓库主管 / 商品经理", "今日18:30前", "负库存SKU数、90天以上库存金额、调拨完成率", "dwd_inventory_balance + dim_product + dws_product_inbound_summary"))
        if _num(summary.get("age_90_amount")) > 0:
            diagnoses.append(self._diag("inventory", "high", "90天以上库存占用资金", f"90天以上库存金额 {_money(summary.get('age_90_amount'))}，需要进入清仓池管理。", [f"总库存金额：{_money(summary.get('total_amount'))}", f"90天以上：{_money(summary.get('age_90_amount'))}", f"180天以上：{_money(summary.get('age_180_amount'))}"], "老库存持续占用现金，若不处理会影响新品采购和经营利润。", "商品部输出清仓池，财务跟踪回款，门店按清仓策略执行。", "商品经理 / 财务经理", "本周五前", "90天以上库存金额下降幅度、清仓销售额", "dws_inventory_daily"))
        warnings = [] if summary else ["库存诊断暂无当前库存余额，可能库存同步未完成。"]
        negative_count = _int(summary.get("negative_sku_count"))
        sku_count = max(_int(summary.get("sku_count")), 1)
        age_ratio = _num(summary.get("age_90_amount")) / max(_num(summary.get("total_amount")), 1)
        health_score = round(max(0, 100 - min(30, negative_count*3) - min(40, age_ratio*100)))
        missing_standard_purchase_price_qty = _num(
            summary.get("missing_standard_purchase_price_qty")
        )
        total_inventory_qty = _num(summary.get("total_quantity"))
        standard_purchase_price_coverage_rate = (
            max(0.0, min(1.0, 1 - missing_standard_purchase_price_qty / total_inventory_qty))
            if total_inventory_qty > 0
            else 0.0
        )
        inventory_amount_status = (
            "estimated"
            if summary.get("inventory_stat_date") and missing_standard_purchase_price_qty > 0
            else "ready"
            if summary.get("inventory_stat_date")
            else "pending_data"
        )
        return {
            "summary": {
                "stat_date": dt,
                "health_score": health_score,
                "net_sales": _num(summary.get("net_sales")),
                "order_count": _int(summary.get("order_count")),
                "gross_margin": _num(summary.get("gross_margin")),
                "inventory_stat_date": _date_str(summary.get("inventory_stat_date")),
                "total_inventory_qty": _int(summary.get("total_quantity")),
                "inventory_amount": _num(summary.get("total_amount")),
                "missing_standard_purchase_price_qty": missing_standard_purchase_price_qty,
                "standard_purchase_price_coverage_rate": standard_purchase_price_coverage_rate,
                "age_90_amount": _num(summary.get("age_90_amount")),
                "age_180_amount": _num(summary.get("age_180_amount")),
                "negative_sku_count": _int(summary.get("negative_sku_count")),
                "sku_count": _int(summary.get("sku_count")),
                "age_90_sku_count": _int(summary.get("age_90_sku_count")),
            },
            "risks": [{"name": r.get("warning_type"), "value": r.get("sku_code") or r.get("product_code"), "level": "high" if r.get("warning_level") == "critical" else "medium"} for r in warnings_rows[:12]],
            "diagnoses": diagnoses[:40],
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(diagnoses[:10])],
            "data_quality": self._quality(
                warnings,
                [],
                ["dwd_inventory_balance", "dim_sku", "dim_product", "dws_product_inbound_summary", "dws_store_daily"],
                metric_status={
                    "net_sales": "ready" if _int(summary.get("sales_source_row_count")) > 0 else "pending_data",
                    "order_count": "ready" if _int(summary.get("sales_source_row_count")) > 0 else "pending_data",
                    "gross_margin": (
                        "ready" if bool(summary.get("is_cost_complete")) else "estimated"
                    ) if _int(summary.get("sales_source_row_count")) > 0 and summary.get("gross_margin") is not None else "pending_data",
                    "inventory_amount": inventory_amount_status,
                    "age_90_amount": inventory_amount_status,
                },
            ),
        }


    async def finance(self, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        dt = _as_date(stat_date or await self._latest_date())
        params = {"dt": dt, "store_code": store_code or "", "allowed_store_codes": sorted(ALLOWED_STORE_CODES)}
        row = await self._one(
            """
            select coalesce(sum(net_sales),0) net_sales, coalesce(sum(cost_of_goods),0) cost_of_goods,
                   coalesce(sum(gross_profit),0) gross_profit, avg(gross_margin) gross_margin,
                   coalesce(sum(total_expense),0) total_expense, coalesce(sum(operating_profit),0) operating_profit,
                   bool_and(is_cost_complete) is_cost_complete, bool_and(is_expense_complete) is_expense_complete,
                   bool_and(coalesce(finance_approved,false)) finance_approved,
                   count(*) source_row_count,
                   'dm_finance_profit_daily' as source_table
            from dm.dm_finance_profit_daily
            where stat_date=:dt
              and ((:store_code = '' and store_code='ALL') or (:store_code <> '' and store_code=:store_code))
            """,
            params,
        )
        if not row or _int(row.get("source_row_count")) == 0:
            row = await self._one(
                """
                select coalesce(sum(net_sales_amount),0) net_sales,
                       coalesce(sum(cost_amount),0) cost_of_goods,
                       coalesce(sum(gross_profit),0) gross_profit,
                       case when sum(net_sales_amount)>0 then sum(gross_profit)/sum(net_sales_amount) end gross_margin,
                       coalesce(sum(total_expense),0) total_expense,
                       coalesce(sum(operating_profit_estimate),0) operating_profit,
                       bool_and(is_profit_complete) is_cost_complete,
                       false as is_expense_complete, false as finance_approved,
                       count(*) source_row_count,
                       'dws_finance_daily' as source_table
                from dws.dws_finance_daily
                where stat_date=:dt
                  and ((:store_code = '' and store_code='ALL') or (:store_code <> '' and store_code=:store_code))
                """,
                params,
            )
        sales_metrics = await self._one(
            """
            select count(distinct ticket_no) order_count, count(*) source_row_count
            from dwd.dwd_pos_ticket
            where biz_date=:dt
              and store_code=ANY(:allowed_store_codes)
              and (:store_code='' or store_code=:store_code)
              and coalesce(is_void,false)=false
              and coalesce(is_pending,false)=false
            """,
            params,
        )
        expense_source = await self._one(
            """select last_sync_at from sys.sys_integration_config where system_code='dingtalk' and status='api'"""
        )
        cost_source = await self._one(
            """select bool_and(is_cost_complete) is_cost_complete from dws.dws_product_daily
               where stat_date=:dt and (:store_code='' or store_code=:store_code)""", params
        )
        if not row or _int(row.get("source_row_count")) == 0:
            row = await self._one(
                """
                with sales as (
                  select coalesce(sum(net_sales_amount),0) net_sales,
                         coalesce(sum(total_cost_amount),0) company_cost,
                         coalesce(sum(gross_profit),0) company_gross_profit,
                         avg(gross_margin) company_gross_margin,
                         count(*) company_source_row_count
                  from dws.dws_company_daily
                  where stat_date=:dt and :store_code = ''
                ), store_sales as (
                  select coalesce(sum(net_sales_amount),0) net_sales,
                         coalesce(sum(cost_amount),0) store_cost,
                         coalesce(sum(gross_profit),0) store_gross_profit,
                         case when sum(net_sales_amount)>0 then sum(gross_profit)/sum(net_sales_amount) end store_gross_margin,
                         count(*) store_source_row_count
                  from dws.dws_store_daily
                  where stat_date=:dt and (:store_code = '' or store_code=:store_code)
                ), product_cost as (
                  select coalesce(sum(cost_amount),0) cost_amount,
                         coalesce(sum(gross_profit),0) gross_profit,
                         bool_and(is_cost_complete) is_cost_complete
                  from dws.dws_product_daily
                  where stat_date=:dt and (:store_code = '' or store_code=:store_code)
                ), expense_dwd as (
                  select coalesce(sum(expense_amount),0) total_expense
                  from dwd.dwd_finance_expense
                  where expense_date=:dt and (:store_code = '' or store_code=:store_code or store_code='ALL')
                ), expense_dingtalk as (
                  select coalesce(sum(amount),0) total_expense
                  from finance_expense_records
                  where expense_date=:dt
                    and :store_code = ''
                    and upper(coalesce(approval_status,'')) in ('COMPLETED','APPROVED','FINISHED')
                ), expense as (
                  select coalesce(nullif(expense_dwd.total_expense,0), expense_dingtalk.total_expense, 0) total_expense
                  from expense_dwd cross join expense_dingtalk
                )
                select coalesce(nullif(store_sales.net_sales,0), sales.net_sales, 0) net_sales,
                       coalesce(nullif(store_sales.store_cost,0), nullif(sales.company_cost,0), nullif(product_cost.cost_amount,0), 0) cost_of_goods,
                       coalesce(nullif(store_sales.store_gross_profit,0), nullif(sales.company_gross_profit,0), nullif(product_cost.gross_profit,0), 0) gross_profit,
                       coalesce(store_sales.store_gross_margin, sales.company_gross_margin) gross_margin,
                       expense.total_expense,
                       coalesce(nullif(store_sales.store_gross_profit,0), nullif(sales.company_gross_profit,0), nullif(product_cost.gross_profit,0), 0) - expense.total_expense operating_profit,
                       coalesce(product_cost.is_cost_complete,false) is_cost_complete,
                       false is_expense_complete, false as finance_approved,
                       greatest(sales.company_source_row_count, store_sales.store_source_row_count) source_row_count,
                       'dws_company_daily/dws_store_daily/dws_product_daily' as source_table
                from sales cross join store_sales cross join product_cost cross join expense
                """,
                params,
            )
        diagnoses = []
        warnings = []
        missing = []
        if not row or _int(row.get("source_row_count")) == 0:
            missing.append("销售/财务基础数据")
        cost_complete = bool(row.get("is_cost_complete")) and bool(cost_source.get("is_cost_complete"))
        expense_complete = bool(row.get("is_expense_complete"))
        finance_approved = bool(row.get("finance_approved"))
        if row and _num(row.get("net_sales")) > 0 and not cost_complete:
            warnings.append("标准进价未完整接入，毛利和经营利润按已覆盖商品估算。")
            diagnoses.append(self._diag("finance", "medium", "标准进价口径未完整", "当前销售已接入，但部分商品缺标准进价，毛利和利润只能作为预估参考。", [f"净销售：{_money(row.get('net_sales'))}", f"销售成本：{_money(row.get('cost_of_goods'))}", "标准进价来源：baison_sku.marketPrice"], "缺标准进价商品未计入销售成本。", "财务与商品部核对标准进价、销售成本汇总和缺标准进价商品。", "财务经理 / 商品经理", "本周内", "标准进价覆盖率、毛利率可用性", row.get("source_table") or "baison_sku.marketPrice"))
        elif row and _num(row.get("cost_of_goods")) > 0:
            warnings.append("销售成本已按百胜标准进价 baison_sku.marketPrice 接入，毛利仍属经营估算口径，最终以财务核准为准。")
        if row and _num(row.get("net_sales")) > 0 and not expense_complete:
            warnings.append("费用明细未接入，经营利润暂未扣除完整费用。")
            diagnoses.append(self._diag("finance", "medium", "费用口径未完整", "当前费用明细为空或不完整，经营利润不能作为最终财报。", [f"净销售：{_money(row.get('net_sales'))}", f"已接费用：{_money(row.get('total_expense'))}"], "报销、房租、水电、工资或其他费用未进入日汇总。", "财务补录费用或启用钉钉/金蝶费用同步，页面继续保留预估标识。", "财务经理", "本周内", "费用接入率、预估利润与核准利润差异", "dwd_finance_expense"))
        gm = _num(row.get("gross_margin"))
        if gm == 0 and _num(row.get("net_sales")) > 0 and _num(row.get("gross_profit")) > 0:
            gm = _num(row.get("gross_profit")) / _num(row.get("net_sales"))
        if gm > 0 and gm < 0.45:
            diagnoses.append(self._diag("finance", "high", "毛利率偏低风险", f"当前毛利率 {_pct(gm)}，低于经营预警线。", [f"毛利：{_money(row.get('gross_profit'))}", f"销售成本：{_money(row.get('cost_of_goods'))}"], "折扣、商品结构或成本归集可能拉低利润。", "商品与财务复核高折扣订单、低毛利款和成本完整性。", "财务经理 / 商品经理", "今日下班前", "毛利率、异常折扣订单数、低毛利款销售占比", row.get("source_table") or "finance"))
        can_assert_operating_profit = _can_assert_operating_profit({
            **row,
            "is_cost_complete": cost_complete,
            "is_expense_complete": expense_complete,
            "finance_approved": finance_approved,
        })
        if can_assert_operating_profit and _num(row.get("operating_profit")) < 0:
            diagnoses.append(self._diag("finance", "high", "经营利润为负", f"当前预估经营利润 {_money(row.get('operating_profit'))}。", [f"净销售：{_money(row.get('net_sales'))}", f"费用：{_money(row.get('total_expense'))}"], "销售毛利无法覆盖费用，或费用一次性集中入账。", "财务拆解费用结构，运营复盘低效门店和低毛利商品。", "财务经理 / 运营经理", "今日18:00前", "经营利润、费用率、毛利率", row.get("source_table") or "finance"))
        high_risks = sum(1 for d in diagnoses if d.get("level") == "high")
        medium_risks = sum(1 for d in diagnoses if d.get("level") == "medium")
        health_score = max(0, 100 - high_risks*20 - medium_risks*10)
        sales_ready = _int(row.get("source_row_count")) > 0
        order_ready = _int(sales_metrics.get("source_row_count")) > 0
        return {
            "summary": {
                "stat_date": dt,
                "health_score": health_score,
                "net_sales": _num(row.get("net_sales")),
                "order_count": _int(sales_metrics.get("order_count")),
                "cost_of_goods": _num(row.get("cost_of_goods")),
                "gross_profit": _num(row.get("gross_profit")),
                "gross_margin": gm,
                "total_expense": _num(row.get("total_expense")),
                "operating_profit": _num(row.get("operating_profit")) if can_assert_operating_profit else None,
                "operating_profit_status": "ready" if can_assert_operating_profit else "pending_data",
                "expense_last_synced_at": str(expense_source.get("last_sync_at") or ""),
                "expense_complete": expense_complete,
                "finance_complete": can_assert_operating_profit,
                "finance_risk_count": len(diagnoses),
            },
            "risks": [{"name": d["title"], "value": d["level_label"], "level": d["level"]} for d in diagnoses],
            "diagnoses": diagnoses,
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(diagnoses)],
            "data_quality": self._quality(
                warnings,
                missing,
                ["dm_finance_profit_daily", "dws_finance_daily", "dws_company_daily", "dws_store_daily", "dws_product_daily", "dwd_pos_ticket", "dwd_finance_expense", "finance_expense_records"],
                metric_status={
                    "net_sales": "ready" if sales_ready else "pending_data",
                    "order_count": "ready" if order_ready else "pending_data",
                    "gross_profit": ("ready" if cost_complete else "estimated") if sales_ready else "pending_data",
                    "gross_margin": (
                        "ready" if cost_complete else "estimated"
                    ) if sales_ready and _num(row.get("net_sales")) > 0 and row.get("gross_margin") is not None else "pending_data",
                    "operating_profit": "ready" if can_assert_operating_profit else "pending_data",
                },
            ),
        }

    async def hr(self, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        dt = _as_date(stat_date or await self._latest_date())
        params = {"dt": dt, "store_code": store_code or ""}
        stores = await self._rows(
            """
            with emp as (
              select substring(d.name from '([0-9]{6})') store_code, count(distinct e.dingtalk_user_id) employee_count
              from dingtalk_employees e
              cross join lateral jsonb_array_elements_text(e.department_ids) dept_id
              join dingtalk_departments d on d.dingtalk_dept_id=dept_id
              where e.active=true and substring(d.name from '([0-9]{6})') = any(:store_codes)
              group by substring(d.name from '([0-9]{6})')
            ), tasks as (
              select related_store_code store_code,
                     count(*) task_count,
                     count(*) filter(where status in ('done','completed','review_passed','closed')) done_count,
                     count(*) filter(where due_date < :dt and status not in ('done','completed','review_passed','closed','cancelled')) overdue_count
              from app.app_action_task
              where is_deleted=false and related_date <= :dt
              group by related_store_code
            )
            select s.store_code, coalesce(ds.store_name,s.store_code) store_name, s.net_sales_amount,
                   s.order_count, s.net_item_count,
                   coalesce(emp.employee_count,0) employee_count,
                   case when coalesce(emp.employee_count,0)>0 then s.net_sales_amount/emp.employee_count end sales_per_employee,
                   coalesce(tasks.task_count,0) task_count,
                   coalesce(tasks.done_count,0) done_count,
                   coalesce(tasks.overdue_count,0) overdue_count
            from dws.dws_store_daily s
            left join dim.dim_store ds on ds.store_code=s.store_code
            left join emp on emp.store_code=s.store_code
            left join tasks on tasks.store_code=s.store_code
            where s.stat_date=:dt and (:store_code = '' or s.store_code=:store_code)
            order by s.net_sales_amount desc nulls last
            limit 80
            """,
            {**params, "store_codes": list(ALLOWED_STORE_CODES)},
        )
        attendance_date_filter = "work_date<=CAST(:dt AS date)" if stat_date else "true"
        hr_actual = await self._one(
            f"""
            select (select count(*) from dingtalk_employees where active=true) employee_count,
                   max(work_date) attendance_stat_date,
                   count(*) attendance_employee_count,
                   count(*) filter(where attendance_status='abnormal') attendance_abnormal_count,
                   coalesce(sum(late_count),0) late_count,
                   coalesce(sum(early_leave_count),0) early_leave_count,
                   coalesce(sum(missing_check_count),0) missing_check_count,
                   coalesce(sum(leave_count),0) leave_count
            from hr_attendance_daily
            where work_date=(select max(work_date) from hr_attendance_daily where {attendance_date_filter})
            """,
            params,
        )
        approvals = await self._one(
            """
            select count(*) filter(where category='leave') leave_approval_count,
                   count(*) filter(where category='business_trip') outing_approval_count,
                   count(*) filter(where category='attendance') attendance_approval_count
            from dingtalk_approval_instances
            where coalesce(result,'agree')='agree'
              and coalesce(finish_time,create_time)::date between CAST(:dt AS date)-interval '30 day' and CAST(:dt AS date)
            """, params)
        common = await self._common_metrics(dt, store_code)
        mapped_emp = sum(_int(s.get("employee_count")) for s in stores)
        actual_emp = _int(hr_actual.get("employee_count"))
        active_store_count = len([s for s in stores if _num(s.get("net_sales_amount")) > 0])
        use_store_proxy = mapped_emp == 0
        valid = [s for s in stores if (_num(s.get("sales_per_employee")) > 0 or use_store_proxy)]
        if use_store_proxy:
            store_eff_avg = sum(_num(s.get("net_sales_amount")) for s in stores) / active_store_count if active_store_count else 0
        else:
            store_eff_avg = sum(_num(s.get("sales_per_employee")) for s in valid) / len(valid) if valid else 0
        total_sales = sum(_num(s.get("net_sales_amount")) for s in stores)
        avg_eff = total_sales / actual_emp if actual_emp else store_eff_avg
        total_tasks = sum(_int(s.get("task_count")) for s in stores)
        done_tasks = sum(_int(s.get("done_count")) for s in stores)
        diagnoses = []
        for s in stores:
            name = s.get("store_name") or s.get("store_code")
            eff = _num(s.get("net_sales_amount")) if use_store_proxy else _num(s.get("sales_per_employee"))
            if store_eff_avg > 0 and eff < store_eff_avg * 0.75:
                label = "门店销售效率偏低" if use_store_proxy else "人效偏低"
                metric_name = "门店销售" if use_store_proxy else "人均销售"
                diagnoses.append(self._diag("hr", "medium", f"{name}{label}", f"{name} {metric_name} {_money(eff)}，低于公司均值 {_money(store_eff_avg)}。", [f"门店销售：{_money(s.get('net_sales_amount'))}", f"员工数：{_int(s.get('employee_count'))}", f"逾期任务：{_int(s.get('overdue_count'))}"], "人员档案、排班或执行动作与销售节奏不匹配；若员工档案为空，当前按门店经营单元做兜底判断。", "运营经理复盘排班、导购成交动作和会员回访；补齐员工档案后切换为真实人效。", "运营经理 / 店长", "今日21:00前", "人均销售、订单数、任务完成率", "dws_store_daily + dim_employee + app_action_task"))
            if _int(s.get("overdue_count")) > 0:
                diagnoses.append(self._diag("hr", "medium", f"{name}执行任务逾期", f"{name} 存在 {_int(s.get('overdue_count'))} 个逾期行动任务。", [f"任务数：{_int(s.get('task_count'))}", f"已完成：{_int(s.get('done_count'))}", f"逾期：{_int(s.get('overdue_count'))}"], "行动闭环执行不到位，会影响诊断问题复盘。", "店长清理逾期任务，运营跟进反馈证据。", "店长 / 运营经理", "今日闭店前", "逾期任务清零、反馈提交率", "app_action_task"))
        attendance_abnormal = _int(hr_actual.get("attendance_abnormal_count"))
        if attendance_abnormal > 0:
            diagnoses.append(self._diag("hr", "medium", "考勤异常待处理", f"最新考勤日有 {attendance_abnormal} 人异常。", [f"考勤人数：{_int(hr_actual.get('attendance_employee_count'))}", f"缺卡：{_int(hr_actual.get('missing_check_count'))}", f"迟到：{_int(hr_actual.get('late_count'))}", f"早退：{_int(hr_actual.get('early_leave_count'))}"], "缺卡、迟到或早退记录需要主管确认，避免影响排班和出勤统计。", "人事当天核对异常记录，通知员工补卡或提交说明。", "人事 / 部门主管", "今日18:00前", "考勤异常关闭率、缺卡数", "hr_attendance_daily"))
        warnings = []
        missing = []
        if actual_emp > 0:
            if use_store_proxy:
                warnings.append("钉钉员工已接入，但当前筛选范围没有可识别的门店部门；门店人效暂按经营单元兜底。")
            missing.append("排班/工资")
        elif use_store_proxy:
            warnings.append("员工档案为空，当前人事诊断按门店经营效率和任务闭环做兜底。")
            missing.append("员工档案/排班/考勤")
        else:
            warnings.append("考勤、排班、工资暂未完整接入；当前以员工档案、销售和任务闭环诊断。")
            missing.append("考勤/排班/工资")
        return {
            "summary": {
                **common,
                "health_score": max(0, 100 - attendance_abnormal * 4 - len(diagnoses) * 3),
                "stat_date": dt,
                "attendance_stat_date": _date_str(hr_actual.get("attendance_stat_date")),
                "employee_count": actual_emp or mapped_emp or active_store_count,
                "attendance_employee_count": _int(hr_actual.get("attendance_employee_count")),
                "attendance_abnormal_count": attendance_abnormal,
                "missing_check_count": _int(hr_actual.get("missing_check_count")),
                "leave_approval_count_30d": _int(approvals.get("leave_approval_count")),
                "outing_approval_count_30d": _int(approvals.get("outing_approval_count")),
                "attendance_approval_count_30d": _int(approvals.get("attendance_approval_count")),
                "mapped_store_employee_count": mapped_emp,
                "avg_sales_per_employee": avg_eff,
                "low_efficiency_store_count": len([d for d in diagnoses if "效率" in d.get("title", "") or "人效" in d.get("title", "")]),
                "task_completion_rate": round(done_tasks / total_tasks, 4) if total_tasks else None,
            },
            "risks": [{"name": d["title"], "value": d["level_label"], "level": d["level"]} for d in diagnoses[:8]],
            "diagnoses": diagnoses[:30],
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(diagnoses[:8])],
            "data_quality": self._quality(warnings, missing, ["dws_store_daily", "dwd_pos_ticket", "dingtalk_employees", "dingtalk_departments", "hr_attendance_daily", "dingtalk_approval_instances", "app_action_task"]),
        }

    async def members(self, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        dt = _as_date(stat_date or await self._latest_date())
        params = {"dt": dt, "store_code": store_code or ""}
        common = await self._common_metrics(dt, store_code)
        visit_date_filter = "visit_date<=CAST(:dt AS date)" if stat_date else "true"
        visit = await self._one(
            f"""
            select max(visit_date) visit_stat_date,
                   count(*) as visit_count,
                   count(*) filter(where visit_status='pending') pending_count,
                   count(*) filter(where is_converted=true) converted_count,
                   coalesce(sum(conversion_amount),0) conversion_amount
            from dm.dm_member_visit_list
            where visit_date=(select max(visit_date) from dm.dm_member_visit_list where {visit_date_filter})
              and (:store_code = '' or store_code=:store_code)
            """,
            params,
        )
        ticket = await self._one(
            """
            select count(*) total_orders,
                   count(*) filter(where nullif(coalesce(vip_code, customer_code), '') is not null) member_orders,
                   count(distinct nullif(coalesce(vip_code, customer_code), '')) active_members,
                   coalesce(sum(sales_amount),0) total_sales,
                   coalesce(sum(sales_amount) filter(where nullif(coalesce(vip_code, customer_code), '') is not null),0) member_sales
            from dwd.dwd_pos_ticket
            where biz_date=:dt and (:store_code = '' or store_code=:store_code)
              and coalesce(is_void,false)=false and coalesce(is_pending,false)=false
            """,
            params,
        )
        member_dim = await self._one(
            """
            select count(*) total_members,
                   count(*) filter(where last_consume_date >= CAST(:dt AS date) - interval '30 day') active_30d,
                   count(*) filter(where last_consume_date < CAST(:dt AS date) - interval '90 day' or last_consume_date is null) sleep_90d
            from dim.dim_member
            where (:store_code = '' or register_store=:store_code or last_consume_store=:store_code)
            """,
            params,
        )
        deposit = await self._one(
            """
            with daily as (
              select max(biz_date) deposit_stat_date,
                     coalesce(sum(recharge_count),0) recharge_count,
                     coalesce(sum(recharge_amount),0) recharge_amount,
                     case when sum(recharge_count)>0 then sum(recharge_amount)/sum(recharge_count) else 0 end avg_recharge_amount,
                     coalesce(sum(consume_amount),0) consume_amount
              from dws.dws_member_deposit_daily
              where biz_date=:dt and (:store_code = '' or store_code=:store_code)
            ), daily_member as (
              select count(DISTINCT member_no) recharge_member_count
              from dwd.dwd_baison_member_deposit_log
              where change_type='0' and biz_date=:dt
                and (:store_code = '' or store_code=:store_code)
            ), member30 as (
              select count(*) recharge_member_count_30d,
                     count(*) filter(where recharge_times>=2) repeat_recharge_member_count
              from (
                select member_no, count(*) recharge_times
                from dwd.dwd_baison_member_deposit_log
                where change_type='0' and biz_date between CAST(:dt AS date)-interval '29 day' and CAST(:dt AS date)
                  and (:store_code = '' or store_code=:store_code)
                group by member_no
              ) x
            ), large_recharge as (
              select count(*) large_recharge_count
              from dwd.dwd_baison_member_deposit_log
              where change_type='0' and biz_date=:dt and money_change>=5000
                and (:store_code = '' or store_code=:store_code)
            )
            select daily.*, daily_member.recharge_member_count, member30.recharge_member_count_30d,
                   member30.repeat_recharge_member_count, large_recharge.large_recharge_count
            from daily cross join daily_member cross join member30 cross join large_recharge
            """,
            params,
        )
        diagnoses = []
        total_orders = _num(ticket.get("total_orders"))
        member_orders = _num(ticket.get("member_orders"))
        member_sales = _num(ticket.get("member_sales"))
        total_sales = _num(ticket.get("total_sales"))
        member_order_ratio = member_orders / total_orders if total_orders else 0
        member_sales_ratio = member_sales / total_sales if total_sales else 0
        if _int(visit.get("pending_count")) > 0:
            diagnoses.append(self._diag("member", "medium", "会员回访待执行", f"今日仍有 {_int(visit.get('pending_count'))} 条会员回访建议待处理。", [f"今日回访名单：{_int(visit.get('visit_count'))}", f"待处理：{_int(visit.get('pending_count'))}", f"已成交金额：{_money(visit.get('conversion_amount'))}"], "会员复购机会需要导购跟进，否则销售机会会自然流失。", "店长分配导购回访，优先处理高价值/沉睡/生日会员。", "店长 / 导购", "今日20:30前", "回访完成率、回访成交金额、会员复购率", "dm_member_visit_list"))
        if total_orders > 0 and member_order_ratio < 0.35:
            diagnoses.append(self._diag("member", "medium", "会员成交占比偏低", f"今日会员订单占比 {member_order_ratio*100:.1f}%，会员销售占比 {member_sales_ratio*100:.1f}%。", [f"总订单：{_int(total_orders)}", f"会员订单：{_int(member_orders)}", f"会员销售：{_money(member_sales)}"], "导购识别会员、老客邀约或会员权益触达不足。", "门店复盘会员识别动作，优先对昨日/近30日消费会员做二次邀约。", "运营经理 / 店长", "今日闭店前", "会员订单占比、会员销售占比、回访成交金额", "dwd_pos_ticket.vip_code"))
        if _int(member_dim.get("sleep_90d")) > 0:
            diagnoses.append(self._diag("member", "low", "沉睡会员池待激活", f"会员档案中90天以上未消费会员 {_int(member_dim.get('sleep_90d'))} 人。", [f"会员总数：{_int(member_dim.get('total_members'))}", f"近30日活跃：{_int(member_dim.get('active_30d'))}"], "老会员复购触达不足，存在可唤醒销售机会。", "按门店导出沉睡会员池，结合新品/生日/储值权益做分层触达。", "会员运营 / 店长", "本周内", "沉睡会员回访完成率、复购金额", "dim_member"))
        recharge_30d = _int(deposit.get("recharge_member_count_30d"))
        repeat_recharge = _int(deposit.get("repeat_recharge_member_count"))
        repeat_rate = repeat_recharge / recharge_30d if recharge_30d else 0
        if _int(deposit.get("large_recharge_count")) > 0:
            diagnoses.append(self._diag("member", "medium", "大额充值待复核", f"当日有 {_int(deposit.get('large_recharge_count'))} 笔5000元及以上会员充值。", [f"充值金额：{_money(deposit.get('recharge_amount'))}", f"充值人数：{_int(deposit.get('recharge_member_count'))}", f"充值客单：{_money(deposit.get('avg_recharge_amount'))}"], "大额充值可能是重点会员经营成果，也需要复核门店、会员和收款记录。", "会员运营与财务核对充值会员、支付凭证和门店归属。", "会员运营 / 财务", "今日18:00前", "大额充值复核完成率、充值到账一致性", "dwd_baison_member_deposit_log"))
        if recharge_30d >= 5 and repeat_rate < 0.20:
            diagnoses.append(self._diag("member", "medium", "会员复充率偏低", f"近30日充值会员 {recharge_30d} 人，复充会员 {repeat_recharge} 人，复充率 {repeat_rate*100:.1f}%。", [f"充值会员：{recharge_30d}", f"复充会员：{repeat_recharge}", f"复充率：{repeat_rate*100:.1f}%"], "首次充值后的权益触达和二次消费承接不足。", "按首次充值日期分层回访，优先跟进已消费但未复充会员。", "会员运营 / 店长", "本周内", "30日复充率、复充金额、储值消费率", "dwd_baison_member_deposit_log"))
        warnings = []
        missing = []
        if _int(member_dim.get("total_members")) == 0:
            warnings.append("会员档案为空，当前会员诊断按小票vip_code/customer_code交易字段兜底。")
            missing.append("会员档案/RFM明细")
        if _int(visit.get("visit_count")) == 0:
            warnings.append("会员回访清单为空，当前只做会员成交占比诊断。")
        if not deposit.get("deposit_stat_date"):
            warnings.append("百胜储值明细未同步到当前诊断日期，充值与复充指标暂为0。")
            missing.append("会员储值明细")
        return {
            "summary": {
                **common,
                "health_score": max(0, 100 - len(diagnoses) * 8),
                "stat_date": dt,
                "visit_stat_date": _date_str(visit.get("visit_stat_date")),
                "visit_count": _int(visit.get("visit_count")),
                "pending_visit_count": _int(visit.get("pending_count")),
                "converted_count": _int(visit.get("converted_count")),
                "conversion_amount": _num(visit.get("conversion_amount")),
                "total_member_count": _int(member_dim.get("total_members")),
                "active_member_count_30d": _int(member_dim.get("active_30d")),
                "sleeping_member_count_90d": _int(member_dim.get("sleep_90d")),
                "active_member_count": _int(ticket.get("active_members")),
                "member_order_count": _int(member_orders),
                "member_sales_amount": member_sales,
                "member_order_ratio": member_order_ratio,
                "member_sales_ratio": member_sales_ratio,
                "deposit_stat_date": _date_str(deposit.get("deposit_stat_date")),
                "recharge_count": _int(deposit.get("recharge_count")),
                "recharge_member_count": _int(deposit.get("recharge_member_count")),
                "recharge_amount": _num(deposit.get("recharge_amount")),
                "avg_recharge_amount": _num(deposit.get("avg_recharge_amount")),
                "stored_value_consume_amount": _num(deposit.get("consume_amount")),
                "repeat_recharge_member_count": repeat_recharge,
                "repeat_recharge_rate": repeat_rate,
            },
            "risks": [
                {"name": "会员订单占比", "value": f"{member_order_ratio*100:.1f}%", "level": "medium" if member_order_ratio < 0.35 and total_orders > 0 else "low"},
                {"name": "待回访会员", "value": _int(visit.get("pending_count")), "level": "medium"},
            ],
            "diagnoses": diagnoses,
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(diagnoses[:8])],
            "data_quality": self._quality(warnings, missing, ["dm_member_visit_list", "dim_member", "dwd_pos_ticket", "dwd_baison_member_deposit_log", "dws_member_deposit_daily"]),
        }

    async def audit(self, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        dt = _as_date(stat_date or await self._latest_date())
        params = {"dt": dt, "store_code": store_code or ""}
        rows = await self._rows(
            """
            select exception_type, severity, store_code, product_code, sku_code, order_no, description, data_snapshot
            from dm.dm_exception_audit
            where audit_date=:dt and (:store_code = '' or store_code=:store_code)
            order by case severity when 'critical' then 1 when 'warning' then 2 else 3 end
            limit 80
            """,
            params,
        )
        generated = []
        if not rows:
            generated = await self._rows(
                """
                with low_discount as (
                  select '低折扣小票' exception_type,
                         case when discount_rate < 0.45 then 'critical' else 'warning' end severity,
                         store_code, null::varchar product_code, null::varchar sku_code, ticket_no order_no,
                         concat('小票折扣率 ', round(discount_rate::numeric*100,1), '%，销售额 ', sales_amount) description,
                         json_build_object('sales_amount', sales_amount, 'standard_amount', standard_amount, 'discount_rate', discount_rate) data_snapshot
                  from dwd.dwd_pos_ticket
                  where biz_date=:dt and (:store_code = '' or store_code=:store_code)
                    and coalesce(is_void,false)=false and coalesce(is_pending,false)=false
                    and sales_amount > 0 and standard_amount > 0 and discount_rate is not null and discount_rate < 0.60
                  order by discount_rate asc
                  limit 20
                ), negative_inventory as (
                  select '负库存' exception_type, 'critical' severity, warehouse_code store_code, product_code, sku_code, null::varchar order_no,
                         concat('SKU负库存：', sku_code, '，数量 ', qty) description,
                         json_build_object('current_quantity', qty, 'synced_at', synced_at) data_snapshot
                  from dwd.v_apparel_inventory_balance
                  where (:store_code = '' or warehouse_code=:store_code) and qty < 0
                  limit 20
                ), low_margin as (
                  select '低毛利商品' exception_type, 'warning' severity, store_code, product_code, null::varchar sku_code, null::varchar order_no,
                         concat('商品毛利率 ', round(gross_margin::numeric*100,1), '%，销售额 ', net_sales_amount) description,
                         json_build_object('gross_margin', gross_margin, 'net_sales_amount', net_sales_amount, 'cost_amount', cost_amount) data_snapshot
                  from dws.dws_product_daily
                  where stat_date=:dt and (:store_code = '' or store_code=:store_code)
                    and net_sales_amount > 0 and gross_margin is not null and gross_margin < 0.35
                  order by gross_margin asc, net_sales_amount desc
                  limit 20
                ), abnormal_store as (
                  select '门店经营异常' exception_type, 'warning' severity, s.store_code, null::varchar product_code, null::varchar sku_code, null::varchar order_no,
                         concat('门店销售 ', s.net_sales_amount, '，订单 ', s.order_count, '，连带率 ', coalesce(s.items_per_order,0)) description,
                         json_build_object('net_sales_amount', s.net_sales_amount, 'order_count', s.order_count, 'items_per_order', s.items_per_order) data_snapshot
                  from dws.dws_store_daily s
                  where s.stat_date=:dt and (:store_code = '' or s.store_code=:store_code)
                    and (coalesce(s.order_count,0)=0 or coalesce(s.net_sales_amount,0)<=0 or coalesce(s.items_per_order,0)<1)
                  limit 20
                )
                select * from low_discount
                union all select * from negative_inventory
                union all select * from low_margin
                union all select * from abnormal_store
                limit 80
                """,
                params,
            )
        source_rows = rows or generated
        diagnoses = []
        for r in source_rows:
            level = "high" if r.get("severity") in ("critical", "high") else "medium"
            obj = r.get("order_no") or r.get("sku_code") or r.get("product_code") or r.get("store_code") or "经营对象"
            diagnoses.append(self._diag("audit", level, f"{r.get('exception_type')}异常", r.get("description") or f"{obj} 触发异常稽核。", [f"对象：{obj}", f"门店：{r.get('store_code') or '-'}"], "可能存在折扣、退款、负库存、低毛利或数据同步异常，需要人工复核。", "责任部门复核单据与审批记录，必要时补充说明并转行动任务。", "财务经理 / 仓库主管 / 运营经理", "今日18:00前", "异常是否关闭、复核记录、同类异常是否复发", "dm_exception_audit / realtime rules"))
        common = await self._common_metrics(dt, store_code)
        warnings = [] if rows else ["异常稽核按小票折扣、实时库存余额、低毛利和门店经营规则实时生成。"]
        return {
            "summary": {**common, "stat_date": dt, "health_score": max(0, 100-len(source_rows)*3), "audit_count": len(source_rows), "high_count": sum(1 for d in diagnoses if d["level"] == "high")},
            "risks": [{"name": d["title"], "value": d["level_label"], "level": d["level"]} for d in diagnoses[:12]],
            "diagnoses": diagnoses,
            "action_suggestions": [self._task_from_diag(d, i + 1) for i, d in enumerate(diagnoses[:10])],
            "data_quality": self._quality([], [], ["dm_exception_audit", "dwd_pos_ticket", "dwd_inventory_balance", "dws_product_daily", "dws_store_daily"]),
        }

    async def action_tasks(self, stat_date: Optional[str] = None, store_code: Optional[str] = None) -> dict:
        dt = _as_date(stat_date or await self._latest_date())
        common = await self._common_metrics(dt, store_code)
        module_payloads = []
        for module_name, fn in [
            ("sales", self.sales),
            ("products", self.products),
            ("inventory", self.inventory),
            ("finance", self.finance),
            ("hr", self.hr),
            ("members", self.members),
            ("audit", self.audit),
        ]:
            module_date = None if stat_date is None and module_name in ("inventory", "hr", "members") else dt
            payload = await fn(module_date, store_code)
            module_payloads.append((module_name, payload))
        diagnoses = []
        suggestions = []
        for module_name, payload in module_payloads:
            diagnoses.extend(payload.get("diagnoses", []))
            for task in payload.get("action_suggestions", []):
                task = dict(task)
                task["module"] = module_name
                suggestions.append(task)
        priority_rank = {"高": 0, "中": 1, "低": 2, "high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda x: priority_rank.get(x.get("priority"), 3))
        existing = await self._rows(
            """
            select task_no, source_type task_source, title problem_type, description, assignee_name owner,
                   due_date::text deadline, risk_level priority, status, feedback_requirement
            from app.app_action_task
            where is_deleted=false and related_date=:dt
              and (:store_code = '' or related_store_code=:store_code)
            order by priority desc, due_date asc nulls last
            limit 80
            """,
            {"dt": dt, "store_code": store_code or ""},
        )
        warnings = []
        missing = []
        for _, payload in module_payloads:
            q = payload.get("data_quality", {})
            warnings.extend(q.get("warnings", []))
            missing.extend(q.get("missing_fields", []))
        return {
            "summary": {
                **common,
                "health_score": max(0, 100 - len([d for d in diagnoses if d.get("level") == "high"]) * 6 - await self._overdue_task_count(dt) * 4),
                "stat_date": dt,
                "suggestion_count": len(suggestions),
                "existing_task_count": len(existing),
                "overdue_count": await self._overdue_task_count(dt),
            },
            "risks": [
                {"name": "建议任务", "value": len(suggestions), "level": "medium" if suggestions else "low"},
                {"name": "正式任务", "value": len(existing), "level": "low"},
            ],
            "diagnoses": diagnoses[:80],
            "action_suggestions": existing + suggestions[:50],
            "data_quality": self._quality(warnings[:6], sorted(set(missing)), ["app_action_task", "AI diagnosis rules", "dws/dwd/dm"]),
        }

    async def confirm_action_tasks(
        self,
        module: str,
        diagnosis_ids: list[str],
        stat_date: Optional[str],
        store_code: Optional[str],
        user: Any,
        *,
        suggestion_key: Optional[str] = None,
        assignee_id: int,
        due_date: date,
    ) -> dict:
        from app.services.task_workflow_service import normalize_assignee_roles

        actionable_roles = {
            "area_supervisor", "finance_manager", "guide", "operation_manager",
            "product_manager", "store_manager", "warehouse_manager",
        }
        dt = _as_date(stat_date or await self._latest_date())
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        if due_date < today:
            raise ValueError("截止日期不能早于今天")
        assignee_row = (await self.db.execute(text("""
            select id, coalesce(real_name, username) as display_name, store_code
            from sys.sys_user
            where id=:id and status=1 and is_deleted=false
        """), {"id": assignee_id})).mappings().first()
        if not assignee_row:
            raise ValueError("负责人不存在或账号未启用")
        if store_code:
            mapped = (await self.db.execute(text("""
                select 1
                from sys.sys_user_store
                where user_id=:user_id and store_code=:store_code
                union all
                select 1
                from sys.sys_user
                where id=:user_id and store_code=:store_code
                limit 1
            """), {"user_id": assignee_id, "store_code": store_code})).scalar_one_or_none()
            if not mapped:
                raise ValueError("负责人尚未绑定该门店，请先完成人员门店映射")

        payload = await self.module(module, dt, store_code)
        diagnoses = {d.get("id"): d for d in payload.get("diagnoses", [])}
        missing_ids = [diagnosis_id for diagnosis_id in diagnosis_ids if diagnosis_id not in diagnoses]
        if missing_ids:
            raise ValueError(f"诊断不存在或已失效: {', '.join(missing_ids[:3])}")
        candidates: list[tuple[str, dict[str, Any]]] = []
        if suggestion_key:
            from app.services.ai_business_advice_service import business_advice_input_hash

            current_context = self.command_context(payload)
            current_input_hash = business_advice_input_hash(current_context)
            row = (await self.db.execute(text("""
                select conclusion,input_hash,data_status,status
                from ai.ai_business_advice_snapshot
                where stat_date=:dt and module=:module
                  and scope_type=:scope_type and target_code=:target_code
            """), {
                "dt": dt,
                "module": module,
                "scope_type": "store" if store_code else "company",
                "target_code": store_code or "company",
            })).mappings().first()
            if not row or row.get("input_hash") != current_input_hash:
                raise ValueError("AI建议证据已变化，请先刷新建议")
            if row.get("data_status") in {"stale", "pending_data"}:
                raise ValueError("AI建议证据未就绪，请先刷新或核验数据")
            actions = ((row or {}).get("conclusion") or {}).get("actions") or []
            action = next((item for item in actions if item.get("suggestion_key") == suggestion_key), None)
            if (
                not action
                or action.get("status") != "draft"
                or action.get("requires_human_confirm") is not True
            ):
                raise ValueError("AI建议不存在、已失效或证据已变化")
            candidates.append((suggestion_key, {
                "problem_type": action.get("title") or "AI经营建议",
                "description": action.get("reason") or "",
                "today_action": action.get("title") or "",
                "evidence": action.get("evidence_refs") or action.get("evidence") or [],
                "review_metric": action.get("review_metric") or "建议复查指标",
                "owner": action.get("responsible_role") or "operation_manager",
                "priority": action.get("priority") or "medium",
            }))
        for diagnosis_id in dict.fromkeys(diagnosis_ids[:50]):
            candidates.append((diagnosis_id, self._task_from_diag(diagnoses[diagnosis_id], 1)))
        if not candidates:
            raise ValueError("没有可确认的经营建议")
        created = 0
        skipped = 0
        for idx, (source_key, task) in enumerate(candidates[:50], 1):
            source_text = f"{dt}|{store_code or ''}|{source_key}"
            source_id = int(hashlib.sha256(source_text.encode("utf-8")).hexdigest()[:15], 16)
            level = str(task.get("priority") or "中")
            priority = 3 if level in ("高", "high") else 2 if level in ("中", "medium") else 1
            task_no = f"AI{dt:%Y%m%d}{source_id:015x}"
            owner = task.get("owner") or "运营经理"
            owner_roles = normalize_assignee_roles(owner) & actionable_roles
            assignee_role = " / ".join(sorted(owner_roles or {"operation_manager"}))
            result = await self.db.execute(text("""
                insert into app.app_action_task
                  (task_no,title,description,data_evidence,data_evidence_text,suggested_actions,review_metrics,
                   feedback_requirement,source_type,source_id,related_store_code,related_date,assignee_name,
                    assignee_id,assignee_role,creator_id,confirmed_by,confirmed_at,due_date,status,priority,risk_level,requires_human_confirm,is_deleted)
                values
                  (:task_no,:title,:description,cast(:evidence as jsonb),:evidence_text,cast(:actions as jsonb),cast(:metrics as jsonb),
                   :feedback,'ai_diagnosis',:source_id,:store_code,:related_date,:assignee_name,
                    :assignee_id,:assignee_role,:creator_id,:confirmed_by,now(),:due_date,'pending',:priority,:risk_level,true,false)
                on conflict (source_type,source_id) where is_deleted=false and source_id is not null do nothing
                returning id
            """), {
                "task_no": task_no, "title": task.get("problem_type") or "AI经营诊断任务",
                "description": task.get("description") or task.get("today_action") or "",
                "evidence": json.dumps(task.get("evidence") or [], ensure_ascii=False),
                "evidence_text": "；".join(task.get("evidence") or []),
                "actions": json.dumps([task.get("today_action")] if task.get("today_action") else [], ensure_ascii=False),
                "metrics": json.dumps([task.get("review_metric")] if task.get("review_metric") else [], ensure_ascii=False),
                "feedback": task.get("feedback_requirement") or "提交处理过程和结果证据。",
                "source_id": source_id, "store_code": store_code or None, "related_date": dt,
                "assignee_name": assignee_row["display_name"], "assignee_id": assignee_id,
                "assignee_role": assignee_role,
                "creator_id": getattr(user, "id", None), "confirmed_by": getattr(user, "id", None),
                "due_date": due_date,
                "priority": priority, "risk_level": "high" if priority == 3 else "medium" if priority == 2 else "low",
            })
            if result.scalar_one_or_none() is None:
                skipped += 1
            else:
                created += 1
        await self.db.commit()
        return {"created_count": created, "skipped_count": skipped}

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
        payload = await fn(stat_date, store_code)
        return payload if "command_conclusion" in payload else self._attach_command_conclusion(payload)
