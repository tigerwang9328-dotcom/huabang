"""规则引擎：确定性业务规则，结构化输出，不修改数据。"""
import json
import hashlib
from datetime import date, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


RULE_DEFS = [
    ("R001", "门店日销售预警", "sales", "warning"),
    ("R002", "门店毛利率预警", "sales", "warning"),
    ("R003", "全公司日销售骤降", "sales", "risk"),
    ("R004", "退货率异常", "sales", "warning"),
    ("R005", "高折扣预警", "sales", "info"),
    ("R006", "负库存预警", "inventory", "critical"),
    ("R007", "90天滞销库存占比", "inventory", "warning"),
    ("R008", "180天以上滞销金额", "inventory", "risk"),
    ("R009", "SKU断码预警", "inventory", "warning"),
    ("R010", "库存周转天数异常", "inventory", "warning"),
    ("R011", "现金安全天数预警", "finance", "critical"),
    ("R012", "预估与核准利润差异", "finance", "warning"),
    ("R013", "待处理任务积压", "task", "warning"),
    ("R014", "任务逾期预警", "task", "risk"),
    ("R015", "数据完整性检查", "data", "info"),
    ("R022", "高销售低利润预警", "finance", "warning"),
    ("R023", "VIP折扣过高预警", "member", "warning"),
]


class RuleEngine:
    def __init__(self):
        self.config: dict[str, dict] = {}

    async def _load_config(self, db: AsyncSession) -> None:
        rows = (await db.execute(text("""
            SELECT rule_id, enabled, thresholds
            FROM app.app_business_rule_config
        """))).mappings().all()
        self.config = {
            row["rule_id"]: {
                "enabled": bool(row["enabled"]),
                "thresholds": row["thresholds"] or {},
            }
            for row in rows
        }

    def _threshold(self, rule_id: str, key: str, default):
        return self.config.get(rule_id, {}).get("thresholds", {}).get(key, default)

    @staticmethod
    def _task_source_id(rule_id: str, stat_date: str, store_code: str | None) -> int:
        raw = f"{rule_id}|{stat_date}|{store_code or 'ALL'}".encode("utf-8")
        return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big") & ((1 << 63) - 1)

    async def run_all(self, stat_date: str, db: AsyncSession, store_code: Optional[str] = None) -> dict:
        d = date.fromisoformat(stat_date)
        results = []
        await self._load_config(db)
        enabled_rule_count = 0

        triggered = 0
        for rule_id, rule_name, category, default_severity in RULE_DEFS:
            if not self.config.get(rule_id, {}).get("enabled", True):
                continue
            enabled_rule_count += 1
            method = getattr(self, f"_rule_{rule_id.lower()}", None)
            if method:
                findings = await method(stat_date, d, db, store_code)
                if findings:
                    for finding in findings:
                        results.append({
                            "rule_id": rule_id,
                            "rule_name": rule_name,
                            "category": category,
                            "severity": finding.get("severity", default_severity),
                            "triggered": True,
                            "store_code": finding.get("store_code"),
                            "title": finding["title"],
                            "evidence": finding.get("evidence", {}),
                            "suggestion": finding.get("suggestion", ""),
                        })
                        triggered += 1
                else:
                    results.append({
                        "rule_id": rule_id, "rule_name": rule_name,
                        "category": category, "severity": "ok",
                        "triggered": False, "store_code": store_code,
                        "title": f"{rule_name}：正常", "evidence": {}, "suggestion": "",
                    })

        return {
            "stat_date": stat_date,
            "total_rules": enabled_rule_count,
            "triggered_count": triggered,
            "results": results,
        }

    async def _rule_r001(self, stat_date, d, db, store_code):
        warning = float(self._threshold("R001", "warning", 3000))
        risk = float(self._threshold("R001", "risk", 1000))
        r = await db.execute(text("""
            SELECT store_code, net_sales_amount FROM dws.dws_store_daily
            WHERE stat_date = :d AND net_sales_amount < :warning
            AND channel = 'offline'
            ORDER BY net_sales_amount
        """), {"d": d, "warning": warning})
        rows = r.fetchall()
        return [{"store_code": row[0],
                 "title": f"门店{row[0]}日销售额{float(row[1] or 0):.0f}元，低于预警阈值{warning:.0f}元",
                 "evidence": {"sales": float(row[1] or 0), "threshold": warning},
                 "suggestion": "建议检查门店营业状态，联系店长了解情况",
                 "severity": "risk" if float(row[1] or 0) < risk else "warning"} for row in rows]

    async def _rule_r002(self, stat_date, d, db, store_code):
        minimum = float(self._threshold("R002", "min_margin", 0.2))
        r = await db.execute(text("""
            SELECT store_code, gross_margin, gross_profit, sales_amount
            FROM dws.dws_store_daily
            WHERE stat_date = :d AND gross_margin IS NOT NULL AND gross_margin < :minimum
            AND is_cost_complete = TRUE AND channel = 'offline'
        """), {"d": d, "minimum": minimum})
        rows = r.fetchall()
        return [{"store_code": row[0],
                 "title": f"门店{row[0]}毛利率{float(row[1] or 0)*100:.1f}%，低于{minimum*100:.0f}%预警线",
                 "evidence": {"gross_margin": float(row[1] or 0), "threshold": minimum,
                              "gross_profit": float(row[2] or 0)},
                 "suggestion": "检查该门店是否有大折扣销售或成本录入错误"} for row in rows]

    async def _rule_r003(self, stat_date, d, db, store_code):
        warning_drop = float(self._threshold("R003", "warning_drop", 0.3))
        risk_drop = float(self._threshold("R003", "risk_drop", 0.5))
        prev = (d - timedelta(days=7)).isoformat()
        r = await db.execute(text("""
            SELECT t.total_sales, p.prev_sales,
                   CASE WHEN p.prev_sales = 0 THEN NULL
                        ELSE (t.total_sales - p.prev_sales) / p.prev_sales END AS growth
            FROM (
                SELECT SUM(sales_amount) AS total_sales FROM dws.dws_store_daily WHERE stat_date = :d
            ) t,
            (
                SELECT SUM(sales_amount) AS prev_sales FROM dws.dws_store_daily WHERE stat_date = :prev
            ) p
        """), {"d": d, "prev": date.fromisoformat(prev)})
        row = r.fetchone()
        if not row or row[2] is None:
            return []
        growth = float(row[2])
        if growth < -warning_drop:
            return [{"title": f"全公司日销售较上周同期下降{abs(growth)*100:.1f}%",
                     "evidence": {"today": float(row[0] or 0), "prev_week": float(row[1] or 0), "growth": growth},
                     "suggestion": "立即排查：是否节假日影响、是否系统数据延迟、是否有重大客诉事件",
                     "severity": "risk" if growth < -risk_drop else "warning"}]
        return []

    async def _rule_r004(self, stat_date, d, db, store_code):
        max_rate = float(self._threshold("R004", "max_rate", 0.15))
        r = await db.execute(text("""
            SELECT store_code, return_amount, sales_amount,
                   return_amount / NULLIF(sales_amount, 0) AS return_rate
            FROM dws.dws_store_daily
            WHERE stat_date = :d AND return_amount / NULLIF(sales_amount, 0) > :max_rate
        """), {"d": d, "max_rate": max_rate})
        rows = r.fetchall()
        return [{"store_code": row[0],
                 "title": f"门店{row[0]}退货率{float(row[3] or 0)*100:.1f}%，超过{max_rate*100:.0f}%预警线",
                 "evidence": {"return_rate": float(row[3] or 0), "return_amount": float(row[1] or 0)},
                 "suggestion": "分析退货原因：质量问题/尺码问题/客户不满意"} for row in rows]

    async def _rule_r005(self, stat_date, d, db, store_code):
        max_discount = float(self._threshold("R005", "max_discount_rate", 0.4))
        r = await db.execute(text("""
            SELECT store_code, avg_discount_rate
            FROM dws.dws_store_daily
            WHERE stat_date = :d AND avg_discount_rate > :max_discount
        """), {"d": d, "max_discount": max_discount})
        rows = r.fetchall()
        return [{"store_code": row[0],
                 "title": f"门店{row[0]}平均折扣率{float(row[1] or 0)*100:.1f}%，折扣力度偏高",
                 "evidence": {"avg_discount_rate": float(row[1] or 0)},
                 "suggestion": "确认是否为促销活动，评估折扣对利润的影响",
                 "severity": "info"} for row in rows]

    async def _rule_r006(self, stat_date, d, db, store_code):
        r = await db.execute(text("""
            SELECT store_code, SUM(negative_sku_count) AS cnt
            FROM dws.dws_inventory_daily WHERE stat_date = :d
            GROUP BY store_code HAVING SUM(negative_sku_count) > 0
        """), {"d": d})
        rows = r.fetchall()
        return [{"store_code": row[0],
                 "title": f"门店{row[0]}存在{row[1]}个负库存SKU，数据异常",
                 "evidence": {"negative_sku_count": int(row[1])},
                 "suggestion": "立即检查ERP库存记录，可能有漏录入库/错误出库",
                 "severity": "critical"} for row in rows]

    async def _rule_r007(self, stat_date, d, db, store_code):
        max_ratio = float(self._threshold("R007", "max_ratio", 0.3))
        r = await db.execute(text("""
            SELECT store_code,
                   (age_91_180_amount + age_180_plus_amount) / NULLIF(total_cost_amount, 0) AS rate,
                   age_91_180_amount + age_180_plus_amount AS amount
            FROM dws.dws_inventory_daily
            WHERE stat_date = :d
              AND (age_91_180_amount + age_180_plus_amount) / NULLIF(total_cost_amount, 0) > :max_ratio
        """), {"d": d, "max_ratio": max_ratio})
        rows = r.fetchall()
        return [{"store_code": row[0],
                 "title": f"门店{row[0]}90天以上库存占比{float(row[1] or 0)*100:.1f}%，滞销风险高",
                 "evidence": {"age_90_plus_rate": float(row[1] or 0), "amount": float(row[2] or 0)},
                 "suggestion": "建议制定清仓促销方案，防止库存继续积压"} for row in rows]

    async def _rule_r008(self, stat_date, d, db, store_code):
        max_amount = float(self._threshold("R008", "max_amount", 30000))
        r = await db.execute(text("""
            SELECT store_code, age_180_plus_amount
            FROM dws.dws_inventory_daily
            WHERE stat_date = :d AND age_180_plus_amount > :max_amount
        """), {"d": d, "max_amount": max_amount})
        rows = r.fetchall()
        return [{"store_code": row[0],
                 "title": f"门店{row[0]}180天以上滞销库存{float(row[1] or 0):.0f}元，资金沉淀严重",
                 "evidence": {"age_180_plus": float(row[1] or 0), "threshold": max_amount},
                 "suggestion": "建议进行内部调拨或大幅打折清货，减少资金占用",
                 "severity": "risk"} for row in rows]

    async def _rule_r009(self, stat_date, d, db, store_code):
        min_count = int(self._threshold("R009", "min_count", 10))
        r = await db.execute(text("""
            SELECT COUNT(DISTINCT sku_code) FROM dwd.v_apparel_inventory_snapshot
            WHERE snapshot_date = :d AND quantity <= 0
        """), {"d": d})
        count = r.scalar() or 0
        if count > min_count:
            return [{"title": f"全渠道存在{count}个SKU零库存/缺货，可能影响销售",
                     "evidence": {"zero_stock_sku_count": int(count)},
                     "suggestion": "检查缺货SKU，优先安排补货"}]
        return []

    async def _rule_r010(self, stat_date, d, db, store_code):
        max_days = float(self._threshold("R010", "max_days", 120))
        r = await db.execute(text("""
            SELECT id.store_code,
                   id.total_cost_amount / NULLIF(sd.net_sales_amount * 0.6, 0) AS sell_through_days,
                   id.total_cost_amount, sd.net_sales_amount
            FROM dws.dws_inventory_daily id
            JOIN dws.dws_store_daily sd ON id.store_code = sd.store_code AND sd.stat_date = id.stat_date
            WHERE id.stat_date = :d
              AND id.total_cost_amount / NULLIF(sd.net_sales_amount * 0.6, 0) > :max_days
        """), {"d": d, "max_days": max_days})
        rows = r.fetchall()
        return [{"store_code": row[0],
                 "title": f"门店{row[0]}库存周转天数约{int(row[1])}天，偏高",
                 "evidence": {"sell_through_days": int(row[1] or 0), "threshold": max_days,
                              "inventory": float(row[2] or 0)},
                 "suggestion": "库存周转偏慢，建议加大销售力度或优化商品结构"} for row in rows]

    async def _rule_r011(self, stat_date, d, db, store_code):
        warning_days = int(self._threshold("R011", "warning_days", 30))
        critical_days = int(self._threshold("R011", "critical_days", 15))
        r = await db.execute(text("""
            SELECT cash_safety_days, cash_balance FROM dm.dm_boss_daily_report WHERE report_date = :d
        """), {"d": d})
        row = r.fetchone()
        if not row:
            return []
        days = int(row[0] or 9999)
        if days < warning_days:
            return [{"title": f"现金安全天数{days}天，资金链紧张",
                     "evidence": {"cash_safety_days": days, "cash_balance": float(row[1] or 0)},
                     "suggestion": "立即评估应收应付，必要时联系财务筹资",
                     "severity": "critical" if days < critical_days else "warning"}]
        return []

    async def _rule_r012(self, stat_date, d, db, store_code):
        max_rate = float(self._threshold("R012", "max_rate", 0.2))
        r = await db.execute(text("""
            SELECT operating_profit, actual_profit,
                   ABS(operating_profit - COALESCE(actual_profit, operating_profit))
                   / NULLIF(ABS(operating_profit), 0) AS diff_rate
            FROM dm.dm_finance_profit_daily
            WHERE stat_date = :d AND store_code = 'ALL'
              AND actual_profit IS NOT NULL
        """), {"d": d})
        row = r.fetchone()
        if not row or row[2] is None:
            return []
        diff = float(row[2])
        if diff > max_rate:
            return [{"title": f"预估利润与核准利润差异{diff*100:.1f}%，超过20%预警线",
                     "evidence": {"estimated": float(row[0] or 0), "actual": float(row[1] or 0),
                                  "diff_rate": diff},
                     "suggestion": "核查费用录入是否准确，避免预估偏差影响决策"}]
        return []

    async def _rule_r013(self, stat_date, d, db, store_code):
        max_count = int(self._threshold("R013", "max_count", 20))
        r = await db.execute(text("""
            SELECT COUNT(*) FROM app.app_action_task WHERE status = 'pending' AND is_deleted = FALSE
        """))
        count = r.scalar() or 0
        if count > max_count:
            return [{"title": f"当前{count}个待处理任务积压，超过预警阈值20",
                     "evidence": {"pending_count": int(count)},
                     "suggestion": "建议管理层优先处理逾期任务，避免积压影响运营"}]
        return []

    async def _rule_r014(self, stat_date, d, db, store_code):
        risk_count = int(self._threshold("R014", "risk_count", 5))
        r = await db.execute(text("""
            SELECT COUNT(*) FROM app.app_action_task
            WHERE status = 'overdue' AND is_deleted = FALSE
        """))
        count = r.scalar() or 0
        if count > 0:
            return [{"title": f"当前{count}个任务已逾期未处理",
                     "evidence": {"overdue_count": int(count)},
                     "suggestion": "立即处理逾期任务，并分析逾期原因避免重复发生",
                     "severity": "risk" if count > risk_count else "warning"}]
        return []

    async def _rule_r015(self, stat_date, d, db, store_code):
        r = await db.execute(text("""
            SELECT is_cost_complete FROM dm.dm_boss_daily_report WHERE report_date = :d
        """), {"d": d})
        row = r.fetchone()
        if row and not row[0]:
            return [{"title": "当日成本数据不完整，毛利率为预估值",
                     "evidence": {"is_cost_complete": False},
                     "suggestion": "请确认ERP系统成本数据是否已导入",
                     "severity": "info"}]
        return []

    async def _rule_r022(self, stat_date, d, db, store_code):
        min_sales = float(self._threshold("R022", "min_sales", 5000))
        max_margin = float(self._threshold("R022", "max_operating_margin", 0.05))
        rows = (await db.execute(text("""
            SELECT store_code, net_sales, operating_profit, operating_margin
            FROM dm.dm_finance_profit_daily
            WHERE stat_date=:d AND store_code='ALL'
              AND operating_profit_status='ready' AND finance_approved=true
              AND net_sales>=:min_sales AND operating_margin<:max_margin
        """), {"d": d, "min_sales": min_sales, "max_margin": max_margin})).fetchall()
        return [{
            "title": f"公司销售额{float(row[1]):.0f}元但经营利润率仅{float(row[3])*100:.1f}%",
            "evidence": {"net_sales": float(row[1]), "operating_profit": float(row[2]),
                         "operating_margin": float(row[3]), "finance_approved": True},
            "suggestion": "复核折扣、商品毛利和费用结构，制定提升利润方案",
        } for row in rows]

    async def _rule_r023(self, stat_date, d, db, store_code):
        min_vip_sales = float(self._threshold("R023", "min_vip_sales", 1000))
        min_discount_rate = float(self._threshold("R023", "min_discount_rate", 0.4))
        rows = (await db.execute(text("""
            WITH vip_sales AS (
                SELECT UPPER(store_code) store_code,
                       COALESCE(NULLIF(BTRIM(vip_code::text),''),
                                NULLIF(BTRIM(customer_code::text),'')) member_no,
                       SUM(sales_amount) vip_sales,
                       SUM(standard_amount) vip_standard
                FROM dwd.dwd_pos_ticket
                WHERE biz_date=:d
                  AND COALESCE(is_void,false)=false AND COALESCE(is_pending,false)=false
                  AND sales_amount>0 AND standard_amount>0
                  AND COALESCE(NULLIF(BTRIM(vip_code::text),''),
                               NULLIF(BTRIM(customer_code::text),'')) IS NOT NULL
                  AND (:store_code IS NULL OR UPPER(store_code)=UPPER(:store_code))
                GROUP BY UPPER(store_code),
                         COALESCE(NULLIF(BTRIM(vip_code::text),''),
                                  NULLIF(BTRIM(customer_code::text),''))
            ), scored AS (
                SELECT store_code, member_no, vip_sales, vip_standard,
                       vip_sales/NULLIF(vip_standard,0) discount_rate
                FROM vip_sales
            )
            SELECT store_code, member_no, vip_sales, vip_standard, discount_rate
            FROM scored
            WHERE vip_sales>=:min_vip_sales AND discount_rate<:min_discount_rate
            ORDER BY discount_rate, vip_sales DESC
        """), {
            "d": d,
            "store_code": store_code,
            "min_vip_sales": min_vip_sales,
            "min_discount_rate": min_discount_rate,
        })).fetchall()
        return [{
            "store_code": row[0],
            "member_no": row[1],
            "title": f"会员{row[1]}当日消费折扣率仅{float(row[4])*100:.1f}%",
            "evidence": {"vip_sales": float(row[2]), "vip_standard": float(row[3]),
                         "discount_rate": float(row[4]), "threshold": min_discount_rate},
            "suggestion": "复核会员折扣授权、促销依据及对应商品毛利",
        } for row in rows]

    async def create_task_drafts(self, rule_results: list[dict], stat_date: str, db,
                                 creator_id: int = 1, commit: bool = True) -> list[dict]:
        """将规则命中结果转为任务草稿（需人工确认后才可派发）"""
        import uuid
        from datetime import timedelta

        SEVERITY_DAYS = {"critical": 1, "risk": 3, "warning": 7, "info": 14}
        SEVERITY_ROLE = {"critical": "store_manager", "risk": "store_manager",
                         "warning": "operation", "info": "operation"}
        created = []
        for result in rule_results:
            if not result.get("triggered"):
                continue
            severity = result.get("severity", "warning")
            source_id = self._task_source_id(
                result["rule_id"], stat_date, result.get("store_code")
            )

            existing = await db.execute(text("""
                SELECT id FROM app.app_action_task
                WHERE source_type = 'rule'
                  AND related_date = :rd AND status IN ('draft','pending','processing')
                  AND related_store_code IS NOT DISTINCT FROM :store
                  AND task_no LIKE :task_prefix
                  AND is_deleted = FALSE
            """), {
                "rd": date.fromisoformat(stat_date),
                "store": result.get("store_code"),
                "task_prefix": f"DRAFT-{result['rule_id']}-%",
            })
            if existing.fetchone():
                continue

            deadline = date.fromisoformat(stat_date) + timedelta(days=SEVERITY_DAYS.get(severity, 7))
            task_no = f"DRAFT-{result['rule_id']}-{stat_date.replace('-','')}-{uuid.uuid4().hex[:4].upper()}"

            await db.execute(text("""
                INSERT INTO app.app_action_task
                    (task_no, title, description, data_evidence_text, suggested_actions,
                     review_metrics, feedback_requirement, source_type, source_id,
                     related_store_code, related_date, assignee_role, creator_id, status,
                     due_date, priority, risk_level, requires_human_confirm, is_deleted)
                VALUES
                    (:no, :title, :desc, :evidence, CAST(:actions AS json), CAST(:review AS json), :feedback,
                     'rule', :sid, :store, :rd, :role, :creator, 'draft',
                     :due_date, :priority, :risk_level, TRUE, FALSE)
            """), {
                "no": task_no,
                "title": f"【草稿】{result['title']}",
                "desc": f"{result['rule_id']} 规则触发，需人工确认后派发",
                "evidence": str(result.get("evidence", {})),
                "actions": json.dumps([result.get("suggestion", "")], ensure_ascii=False),
                "review": json.dumps([f"复查指标：{result['rule_id']} 相关数据"], ensure_ascii=False),
                "feedback": "需提交处理结果和改进措施",
                "sid": source_id,
                "store": result.get("store_code"),
                "rd": date.fromisoformat(stat_date),
                "role": SEVERITY_ROLE.get(severity, "operation"),
                "creator": creator_id,
                "due_date": deadline,
                "priority": 10 if severity == "critical" else 8 if severity == "risk" else 5,
                "risk_level": severity if severity in {"critical", "risk"} else "medium",
            })
            created.append({"task_no": task_no, "rule_id": result["rule_id"], "title": result["title"]})

        if created and commit:
            await db.commit()
        return created
