"""AI诊断引擎（规则优先 + AI摘要 + 权限过滤 + 格式固定）"""
import logging
import httpx
import json
import hashlib
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.log import LogAiCall
from app.models.sys import SysUser

logger = logging.getLogger(__name__)

# AI禁止输出的敏感结论模式（后处理检查）
FORBIDDEN_CONCLUSIONS = [
    "已下单", "已采购", "已改价", "已调库存", "已扣款", "已罚款",
    "自动完成", "已执行", "已生成凭证", "已经下单", "已经采购",
    "已经改价", "已经调拨", "已经执行", "任务已完成", "任务已经完成",
    "处理完成", "自动派发", "自动创建任务", "已联系会员", "已经联系会员",
    "已经结束", "已结束", "工作完成",
]

# 字段权限敏感字段
SENSITIVE_FIELDS_BY_PERMISSION = {
    "profit": ["gross_profit", "gross_margin", "operating_profit", "net_profit"],
    "cost": ["standard_purchase_price", "cost_amount"],
    "cash": ["cash_balance", "cash_safety_days", "total_cash"],
    "member_phone": ["phone", "member_phone"],
}

COMMAND_METRIC_LABELS = {
    "sales_amount": "销售额",
    "actual_pay_amount": "实收金额",
    "online_sales": "线上销售",
    "offline_sales": "线下销售",
    "return_amount": "退货金额",
    "return_rate": "退货率",
    "order_count": "订单数",
    "item_count": "销售件数",
    "avg_order_value": "客单价",
    "items_per_order": "连带率",
    "gross_profit": "毛利额",
    "gross_margin": "毛利率",
    "inventory_amount": "库存金额",
    "age_90_plus_amount": "90天以上库存",
    "vip_balance": "VIP余额",
    "vip_sales": "VIP销售",
    "expense_amount": "费用",
    "operating_profit": "经营利润",
}
COMMAND_STATUSES = {"ready", "estimated", "pending_data", "stale"}
COMMAND_OUTPUT_KEYS = ("facts", "risks", "recommendations", "actions", "limitations")
MODEL_OUTPUT_KEYS = ("executive_summary", "key_findings", "recommendations", "limitations")
ALLOWED_ACTION_TYPES = {
    "verify_data", "refresh_data", "review_inventory", "adjust_merchandising",
    "coach_store", "member_followup", "investigate_exception", "review_expense",
}
ALLOWED_RESPONSIBLE_ROLES = {
    "operation_manager", "area_supervisor", "store_manager", "product_manager",
    "warehouse_manager", "finance_manager", "hr_manager", "member_manager", "audit_manager",
}
ALLOWED_PRIORITIES = {"high", "medium", "low"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}
PROMPT_VERSION = "business-advice-v3"
FORBIDDEN_INCOMPLETE_FINANCE_CLAIMS = (
    "公司盈利", "公司亏损", "最终盈利", "最终亏损", "实现盈利", "实现亏损",
    "利润为正", "利润为负", "经营利润为", "净利润为",
)
SENSITIVE_TEXT_KEYWORDS = (
    "手机号", "会员号", "员工姓名", "导购姓名", "员工：", "导购：", "负责人：",
    "审批", "备注", "原始JSON", "raw_json", "cookie", "token", "secret",
)
FINANCE_CLAIM_TERMS = ("盈利", "亏损", "净利润", "经营利润", "赚钱", "赔钱", "净赚", "净亏", "盈亏")
FINANCE_LIMITATION_TERMS = (
    "不能判断", "无法判断", "不可判断", "不判断", "尚不能判断",
    "无法评估", "不能评估", "不可评估", "无法计算", "不能计算",
    "无法核实", "难以判断", "暂不能判断", "无法推断", "难以评估",
)
# 财务中性描述:不构成确定性盈亏结论,如"盈利能力较强"是描述商品毛利水平,不是判断公司盈亏
# 校验时先剔除这些短语,避免被 FINANCE_CLAIM_TERMS 中的"盈利/亏损"误判
FINANCE_NEUTRAL_PHRASES = (
    "盈利能力", "盈利水平", "盈利状况", "盈利趋势", "盈利空间", "盈利质量",
    "亏损风险", "亏损可能", "亏损概率", "亏损空间",
    "毛利水平", "毛利率水平", "毛利率能力",
)
FORBIDDEN_POSITIVE_FINANCE_CLAIMS = (
    "赚钱", "赔钱", "净赚", "净亏", "已盈利", "已亏损", "实现盈利", "实现亏损",
    "盈利为", "亏损为", "利润为正", "利润为负",
)


# 业务中性词：常见业务短语中包含姓氏字符，避免被姓名模式误判为个人信息
# 覆盖"任务执行/任务待执行/任务需执行"等多种组合
_BUSINESS_NEUTRAL_TOKENS = (
    "任务执行", "任务跟进", "任务处理", "任务复核", "任务确认", "任务联系", "任务负责",
    "任务待执行", "任务待跟进", "任务待处理", "任务待复核", "任务待确认", "任务待联系", "任务待负责",
    "任务需执行", "任务需跟进", "任务需处理", "任务需复核", "任务需确认", "任务需联系", "任务需负责",
    "任务将执行", "任务将跟进", "任务将处理", "任务将复核", "任务将确认", "任务将联系", "任务将负责",
    "工作执行", "工作跟进", "工作处理", "工作复核", "工作确认", "工作联系", "工作负责",
    "工作待执行", "工作待跟进", "工作待处理", "工作待复核", "工作待确认", "工作待联系", "工作待负责",
    "工作需执行", "工作需跟进", "工作需处理", "工作需复核", "工作需确认", "工作需联系", "工作需负责",
    "事项执行", "事项跟进", "事项处理", "事项复核", "事项确认", "事项联系", "事项负责",
    "事项待执行", "事项待跟进", "事项待处理", "事项待复核", "事项待确认", "事项待联系", "事项待负责",
    "事项需执行", "事项需跟进", "事项需处理", "事项需复核", "事项需确认", "事项需联系", "事项需负责",
)


def _contains_name_action_pattern(value: str) -> bool:
    """姓名+动作模式匹配,先剔除业务中性词避免误伤(如"任务执行"被识别为"任+务+执行")。"""
    scrubbed = value
    for token in _BUSINESS_NEUTRAL_TOKENS:
        scrubbed = scrubbed.replace(token, "〇〇〇〇")
    return bool(
        re.search(
            r"(?:赵|钱|孙|李|周|吴|郑|王|冯|陈|褚|卫|蒋|沈|韩|杨|朱|秦|尤|许|何|吕|施|张|孔|曹|严|华|金|魏|陶|姜|谢|邹|喻|柏|水|窦|章|云|苏|潘|葛|奚|范|彭|郎|鲁|韦|昌|马|苗|凤|花|方|俞|任|袁|柳|唐|罗|薛|雷|贺|倪|汤|滕|殷|段|郝|邬|安|常|乐|于|时|傅|皮|卞|齐|康|伍|余|元|卜|顾|孟|平|黄|和|穆|萧|尹)[\u4e00-\u9fff]{1,2}(?:负责|复核|处理|跟进|确认|执行|联系)",
            scrubbed,
        )
    )


def contains_sensitive_text(value: str) -> bool:
    lowered = value.lower()
    return bool(
        re.search(r"1[3-9]\d{9}", value)
        or re.search(r"(?<!\d)\d{8,}(?!\d)", value)
        or re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", value)
        or re.search(r"[\{\}]|\"[^\"]+\"\s*:", value)
        or re.search(r"(?:员工|导购|负责人|会员)(?:姓名)?[：:为是]\s*[\u4e00-\u9fff]{2,4}", value)
        or re.search(r"请[\u4e00-\u9fff]{2,4}(?:复核|处理|跟进|确认|执行|联系)", value)
        or _contains_name_action_pattern(value)
        or any(keyword.lower() in lowered for keyword in SENSITIVE_TEXT_KEYWORDS)
    )


def sanitize_command_context(context: dict[str, Any]) -> dict[str, Any]:
    """Keep only sourced command-center fields that AI is allowed to see."""
    finance_complete = bool(context.get("finance_complete"))
    metrics: dict[str, dict[str, Any]] = {}
    for key, raw in (context.get("metrics") or {}).items():
        if key not in COMMAND_METRIC_LABELS or not isinstance(raw, dict):
            continue
        status = str(raw.get("status") or "pending_data")
        source = str(raw.get("source") or "").strip()
        if status not in COMMAND_STATUSES or not source:
            continue
        value = raw.get("value")
        if isinstance(value, Decimal):
            value = float(value)
        reason = raw.get("reason")
        if status in {"pending_data", "stale"}:
            value = None
        if key == "operating_profit" and not finance_complete:
            continue
        metrics[key] = {
            "fact_id": f"fact:{key}",
            "label": COMMAND_METRIC_LABELS[key],
            "value": value,
            "status": status,
            "source": source,
            "as_of": str(raw.get("as_of")) if raw.get("as_of") is not None else None,
            "reason": reason,
        }

    rules = []
    for raw in (context.get("rules") or [])[:50]:
        if not isinstance(raw, dict) or not raw.get("id") or not raw.get("title"):
            continue
        title = str(raw["title"])
        if contains_sensitive_text(title):
            continue
        evidence = []
        for value in (raw.get("evidence") or [])[:10]:
            text_value = str(value)
            if contains_sensitive_text(text_value):
                continue
            evidence.append(text_value[:160])
        rules.append({
            "rule_id": f"rule:{raw['id']}",
            "id": str(raw["id"]),
            "title": title,
            "level": str(raw.get("level") or "warning"),
            "evidence": evidence,
            "source": str(raw.get("source") or "rule_engine"),
        })

    return {
        "metrics": metrics,
        "rules": rules,
        "tasks": [],
        "finance_complete": finance_complete,
    }


def build_template_command_conclusion(context: dict[str, Any]) -> dict[str, Any]:
    """Deterministic fallback; it never turns missing data into zero."""
    facts = []
    limitations = []
    for key, metric in context.get("metrics", {}).items():
        status = metric.get("status")
        if status in {"ready", "estimated"} and metric.get("value") is not None:
            facts.append({
                "fact_id": metric.get("fact_id") or f"fact:{key}",
                "key": key,
                "label": metric["label"],
                "value": metric["value"],
                "status": status,
                "source": metric["source"],
                "as_of": metric.get("as_of"),
                "note": "预估" if status == "estimated" else "已就绪",
            })
        if status == "estimated":
            limitations.append(f"{metric['label']}为预估值，来源：{metric['source']}")
        elif status == "pending_data":
            limitations.append(metric.get("reason") or f"{metric['label']}待接入")
        elif status == "stale":
            limitations.append(f"{metric['label']}数据已过期，最近日期：{metric.get('as_of') or '未知'}")
    if not context.get("finance_complete"):
        limitations.append("费用未完整接入，只能判断毛利，不能判断最终盈亏")

    risks = [{
        "rule_id": rule.get("rule_id") or f"rule:{rule['id']}",
        "id": rule["id"],
        "title": rule["title"],
        "level": rule["level"],
        "evidence": rule["evidence"],
        "source": rule["source"],
    } for rule in context.get("rules", [])]
    recommendations = [{
        "action_type": "verify_data",
        "title": f"复核{risk['title']}",
        "reason": "依据确定性规则和原始证据处理，执行前由负责人确认。",
        "priority": "high" if risk["level"] in {"critical", "high"} else "medium",
        "evidence_refs": [risk["rule_id"]],
        "responsible_role": "operation_manager",
        "due_in_days": 1,
        "review_metric": "规则复核状态",
    } for risk in risks[:5]]
    actions = [{
        "suggestion_key": hashlib.sha256(risk["rule_id"].encode("utf-8")).hexdigest()[:24],
        "action_type": "verify_data",
        "title": f"处理{risk['title']}",
        "owner": "operation_manager",
        "responsible_role": "operation_manager",
        "due_in_days": 1,
        "review_metric": "规则复核状态",
        "status": "draft",
        "requires_human_confirm": True,
        "evidence": [risk["id"], *risk.get("evidence", [])[:3]],
    } for risk in risks[:5]]
    return {
        "executive_summary": "基于确定性指标与规则生成，未调用大模型。",
        "key_findings": [],
        "facts": facts,
        "risks": risks,
        "recommendations": recommendations,
        "actions": actions,
        "limitations": list(dict.fromkeys(str(item) for item in limitations if item)),
    }


def validate_command_conclusion(payload: dict[str, Any], *, finance_complete: bool) -> dict[str, Any]:
    if not isinstance(payload, dict) or any(not isinstance(payload.get(key), list) for key in COMMAND_OUTPUT_KEYS):
        raise ValueError("AI经营结论结构不合法")
    rendered = json.dumps(payload, ensure_ascii=False)
    if not finance_complete and any(pattern in rendered for pattern in FORBIDDEN_INCOMPLETE_FINANCE_CLAIMS):
        raise ValueError("费用不完整时禁止输出确定性盈亏结论")

    for key in ("facts", "risks", "recommendations"):
        if any(not isinstance(item, dict) or not item.get("title", item.get("label")) for item in payload[key]):
            raise ValueError(f"AI经营结论的{key}结构不合法")
    if any(not isinstance(item, str) for item in payload["limitations"]):
        raise ValueError("AI经营结论的数据限制结构不合法")
    for action in payload["actions"]:
        if not isinstance(action, dict) or not action.get("title"):
            raise ValueError("AI行动结构不合法")
        if not isinstance(action.get("evidence", []), list):
            raise ValueError("AI行动证据结构不合法")
        action["status"] = "draft"
        action["requires_human_confirm"] = True
    payload["facts"] = payload["facts"][:50]
    payload["risks"] = payload["risks"][:50]
    payload["recommendations"] = payload["recommendations"][:10]
    payload["actions"] = payload["actions"][:10]
    payload["limitations"] = payload["limitations"][:20]
    return payload


def _validate_narrative(text: Any, *, finance_complete: bool) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("AI经营建议文本为空")
    value = text.strip()
    if (
        re.search(r"\d", value)
        or re.search(r"[%％]", value)
        or any(term in value for term in ("翻倍", "倍增", "成倍"))
        or re.search(r"百分之[零〇一二三四五六七八九十百千万亿两]+", value)
        or re.search(
            r"[零〇一二三四五六七八九十百千万亿两]+(?:元|万元|件|单|笔|人|天|日|家|款|个)",
            value,
        )
    ):
        raise ValueError("AI经营建议不得自行书写指标数值")
    if any(pattern in value for pattern in FORBIDDEN_CONCLUSIONS):
        raise ValueError("AI经营建议不得声称已执行")
    action_terms = r"(?:采购|下单|改价|调拨|调库存|联系|派发|建单|创建|处理|执行|复核|任务|工作)"
    completion_terms = r"(?:已经|已)(?:完成|结束|执行|处理|联系|派发)"
    if (
        re.search(action_terms + r".{0,12}" + completion_terms, value)
        or re.search(completion_terms + r".{0,8}" + action_terms, value)
    ):
        raise ValueError("AI经营建议不得声称已执行")
    if contains_sensitive_text(value):
        raise ValueError("AI经营建议不得包含个人信息或原始数据")
    if not finance_complete:
        if any(term in value for term in FORBIDDEN_POSITIVE_FINANCE_CLAIMS):
            raise ValueError("费用不完整时禁止输出确定性盈亏结论")
        # 剔除中性财务描述(如"盈利能力较强"),避免被"盈利/亏损"误判为确定性盈亏结论
        scrubbed = value
        for phrase in FINANCE_NEUTRAL_PHRASES:
            scrubbed = scrubbed.replace(phrase, "中性描述")
        clauses = re.split(r"[。！？；;!?，,]|但(?:是)?|然而|不过|却", scrubbed)
        for clause in clauses:
            has_finance_claim = any(term in clause for term in FINANCE_CLAIM_TERMS)
            is_limitation = any(term in clause for term in FINANCE_LIMITATION_TERMS)
            if (
                any(pattern in clause for pattern in FORBIDDEN_INCOMPLETE_FINANCE_CLAIMS)
                or (has_finance_claim and not is_limitation)
            ):
                raise ValueError("费用不完整时禁止输出确定性盈亏结论")
    return value


def validate_model_business_advice(
    payload: dict[str, Any], *, safe_context: dict[str, Any]
) -> dict[str, Any]:
    """Validate only model-owned narrative. Facts and risks are never accepted from the model."""
    if not isinstance(payload, dict) or set(payload) != set(MODEL_OUTPUT_KEYS):
        raise ValueError("AI经营建议 JSON 结构不合法")
    if not all(isinstance(payload.get(key), list) for key in ("key_findings", "recommendations", "limitations")):
        raise ValueError("AI经营建议 JSON 数组结构不合法")
    finance_complete = bool(safe_context.get("finance_complete"))
    valid_refs = {
        metric.get("fact_id") for metric in (safe_context.get("metrics") or {}).values()
    } | {
        rule.get("rule_id") for rule in (safe_context.get("rules") or [])
    }
    valid_refs.discard(None)
    metric_status = {
        metric.get("fact_id"): metric.get("status")
        for metric in (safe_context.get("metrics") or {}).values()
    }

    result = {
        "executive_summary": _validate_narrative(payload.get("executive_summary"), finance_complete=finance_complete),
        "key_findings": [],
        "recommendations": [],
        "limitations": [],
    }
    for item in payload["key_findings"][:10]:
        if not isinstance(item, dict) or set(item) != {"title", "explanation", "confidence", "evidence_refs"}:
            raise ValueError("AI关键发现结构不合法")
        refs = item.get("evidence_refs")
        if not isinstance(refs, list) or not refs or any(ref not in valid_refs for ref in refs):
            raise ValueError("AI关键发现引用了不存在的证据")
        confidence = item.get("confidence")
        if confidence not in ALLOWED_CONFIDENCE:
            raise ValueError("AI关键发现置信度非法")
        if confidence == "high" and any(metric_status.get(ref) == "estimated" for ref in refs):
            raise ValueError("预估事实最高只能给中等置信度")
        result["key_findings"].append({
            "title": _validate_narrative(item.get("title"), finance_complete=finance_complete),
            "explanation": _validate_narrative(item.get("explanation"), finance_complete=finance_complete),
            "confidence": confidence,
            "evidence_refs": refs,
        })
    for item in payload["recommendations"][:10]:
        expected = {
            "action_type", "title", "reason", "priority", "evidence_refs",
            "responsible_role", "due_in_days", "review_metric",
        }
        if not isinstance(item, dict) or set(item) != expected:
            raise ValueError("AI行动建议结构不合法")
        refs = item.get("evidence_refs")
        if not isinstance(refs, list) or not refs or any(ref not in valid_refs for ref in refs):
            raise ValueError("AI行动建议引用了不存在的证据")
        if item.get("action_type") not in ALLOWED_ACTION_TYPES:
            raise ValueError("AI行动类型非法")
        if item.get("responsible_role") not in ALLOWED_RESPONSIBLE_ROLES:
            raise ValueError("AI责任角色非法")
        if item.get("priority") not in ALLOWED_PRIORITIES:
            raise ValueError("AI优先级非法")
        due_in_days = item.get("due_in_days")
        if not isinstance(due_in_days, int) or not 1 <= due_in_days <= 30:
            raise ValueError("AI建议期限非法")
        result["recommendations"].append({
            "action_type": item["action_type"],
            "title": _validate_narrative(item.get("title"), finance_complete=finance_complete),
            "reason": _validate_narrative(item.get("reason"), finance_complete=finance_complete),
            "priority": item["priority"],
            "evidence_refs": refs,
            "responsible_role": item["responsible_role"],
            "due_in_days": due_in_days,
            "review_metric": _validate_narrative(item.get("review_metric"), finance_complete=finance_complete),
        })
    result["limitations"] = [
        _validate_narrative(item, finance_complete=finance_complete)
        for item in payload["limitations"][:20]
    ]
    return result


def _candidate_actions(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = []
    for item in recommendations:
        suggestion_source = json.dumps(item, ensure_ascii=False, sort_keys=True)
        actions.append({
            **item,
            "suggestion_key": hashlib.sha256(suggestion_source.encode("utf-8")).hexdigest()[:24],
            "owner": item["responsible_role"],
            "status": "draft",
            "requires_human_confirm": True,
            "evidence": item["evidence_refs"],
        })
    return actions


class AIEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_command_conclusion(
        self, context_data: dict[str, Any], *, allow_model: Optional[bool] = None
    ) -> dict[str, Any]:
        """Keep facts immutable while letting DeepSeek explain and propose candidate actions."""
        safe_context = sanitize_command_context(context_data)
        template = build_template_command_conclusion(safe_context)
        template.update({
            "mode": "template",
            "model_used": "deterministic_rules",
            "fallback_reason": "AI经营建议功能未开启",
        })
        usable = any(
            metric.get("status") in {"ready", "estimated"} and metric.get("value") is not None
            for metric in safe_context.get("metrics", {}).values()
        ) or bool(safe_context.get("rules"))
        if not usable:
            template["fallback_reason"] = "没有可供模型解释的就绪事实"
            return template
        model_enabled = settings.AI_BUSINESS_ADVICE_ENABLED if allow_model is None else allow_model
        if not model_enabled:
            return template

        system_prompt = """你是华邦经营顾问。只输出 json，不得输出 Markdown。
模型只能解释服务端事实引用和提出候选行动；不得输出、改写或猜测任何金额、比例、件数、单数。
除 due_in_days 外，所有叙述字段都不得出现阿拉伯数字、中文数字、日期、金额、比例、件数或数量单位；涉及指标时只写“见证据引用”。
禁止使用“今天、昨天、本周、本月、近七天、近30天、X天前、X日后、180天、90天”等具体时间表述；改用“近期、最近、当期、上期、历史均值”等相对描述。
禁止使用“翻番、翻倍、增长X成、提升X成”等带数字的修辞；改用“明显提升、有所改善、有所下滑”。
叙述字段包括 executive_summary、key_findings 的 title/explanation、recommendations 的 title/reason/review_metric，以及 limitations。
不得声称行动已经执行。费用不完整时不得判断盈利、亏损、经营利润或净利润。
若输入 finance_complete=false，只能在 limitations 使用固定句“费用数据待接入，无法判断盈亏”；其他叙述字段禁止出现盈利、亏损、利润、赚钱、赔钱或盈亏，可使用“无法评估盈亏”等表述。
引用 estimated 状态事实时 confidence 只能为 medium 或 low，禁止 high。
所有 evidence_refs 必须逐字来自输入（必须从 metrics.fact_id 或 rules.rule_id 列表中复制粘贴，禁止缩写或编造），责任角色和行动类型必须使用给定枚举。"""
        user_content = """请按以下 json 格式返回：
{"executive_summary":"不含数字的简短结论","key_findings":[{"title":"标题","explanation":"解释","confidence":"high|medium|low","evidence_refs":["fact:或rule:引用"]}],"recommendations":[{"action_type":"受控类型","title":"行动","reason":"原因","priority":"high|medium|low","evidence_refs":["引用"],"responsible_role":"受控角色","due_in_days":1,"review_metric":"复查指标名"}],"limitations":["限制"]}
受控行动类型：%s
受控责任角色：%s
服务端脱敏事实上下文：%s""" % (
            ",".join(sorted(ALLOWED_ACTION_TYPES)),
            ",".join(sorted(ALLOWED_RESPONSIBLE_ROLES)),
            json.dumps(safe_context, ensure_ascii=False, sort_keys=True, default=str),
        )
        last_error: Exception | None = None
        attempt_user_content = user_content
        for _attempt in range(2):
            started = datetime.now(timezone.utc)
            try:
                response = await self._call_business_advice(
                    system_prompt,
                    attempt_user_content,
                )
                content = (response.get("content") or "").strip()
                if not content:
                    raise ValueError("AI返回空内容")
                if response.get("model") != settings.AI_BUSINESS_ADVICE_MODEL:
                    raise ValueError("经营建议模型与配置不一致")
                model_payload = validate_model_business_advice(json.loads(content), safe_context=safe_context)
                latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
                return {
                    **template,
                    **model_payload,
                    "recommendations": model_payload["recommendations"],
                    "actions": _candidate_actions(model_payload["recommendations"]),
                    "limitations": list(dict.fromkeys([
                        *template["limitations"], *model_payload["limitations"],
                    ])),
                    "mode": "model",
                    "model_used": response["model"],
                    "fallback_reason": None,
                    "prompt_version": PROMPT_VERSION,
                    "prompt_tokens": response.get("prompt_tokens"),
                    "completion_tokens": response.get("completion_tokens"),
                    "total_tokens": response.get("total_tokens"),
                    "latency_ms": latency_ms,
                }
            except Exception as exc:
                last_error = exc
                logger.warning("AI经营建议校验/调用失败，第%s次: %s", _attempt + 1, type(exc).__name__)
                if _attempt == 0:
                    if isinstance(exc, ValueError):
                        retry_reason = str(exc)[:160]
                    else:
                        retry_reason = type(exc).__name__
                    attempt_user_content = (
                        f"{user_content}\n\n上次输出未通过校验：{retry_reason}。"
                        "请重新生成完整 json，并只修正该错误；不得放宽任何事实、数字、隐私或执行边界。"
                    )
        template["fallback_reason"] = f"模型结果未通过校验：{type(last_error).__name__ if last_error else 'unknown'}"
        template["error_code"] = type(last_error).__name__ if last_error else "unknown"
        return template

    async def ask(
        self,
        question: str,
        current_user: SysUser,
        user_roles: list[str],
        context_data: Optional[dict] = None,
    ) -> dict:
        """AI问答（继承用户权限过滤）"""
        # 权限过滤：确定允许的数据范围
        allowed_fields = self._get_allowed_fields(user_roles)
        permission_blocked = False
        block_reason = ""

        # 检查问题是否触及无权限字段
        blocked_fields = self._check_sensitive_query(question, allowed_fields)
        if blocked_fields:
            permission_blocked = True
        block_reason = "您无权查询以下信息: " + ", ".join(blocked_fields)

        # 过滤上下文数据中的敏感字段
        safe_context = self._filter_context_data(context_data or {}, allowed_fields)

        call_log = LogAiCall(
            user_id=current_user.id,
            user_role=", ".join(user_roles),
            call_type="ask",
            user_question=question[:1000],
            data_scope=str(allowed_fields),
            permission_blocked=permission_blocked,
            permission_block_reason=block_reason if permission_blocked else None,
        )

        if permission_blocked:
            call_log.status = "blocked"
            self.db.add(call_log)
            return {
                "answer": f"抱歉，您的权限不足以查询该信息。{block_reason}",
                "permission_blocked": True,
                "block_reason": block_reason,
            }

        # 构建 prompt
        system_prompt = self._build_system_prompt(user_roles, allowed_fields)
        user_content = question
        if safe_context:
            user_content += f"\n\n相关数据：\n{json.dumps(safe_context, ensure_ascii=False, indent=2)}"

        try:
            start_time = datetime.now(timezone.utc)
            response = await self._call_ai(system_prompt, user_content)
            elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            answer = response.get("content", "")

            # 后处理：检查AI是否输出了禁止结论
            self._validate_ai_output(answer)

            call_log.model_name = response.get("model", "")
            call_log.ai_provider = settings.AI_PROVIDER
            call_log.prompt_tokens = response.get("prompt_tokens")
            call_log.completion_tokens = response.get("completion_tokens")
            call_log.total_tokens = response.get("total_tokens")
            call_log.response_summary = answer[:500]
            call_log.latency_ms = elapsed_ms
            call_log.status = "success"
            self.db.add(call_log)

            return {
                "answer": answer,
                "model_used": response.get("model"),
                "permission_blocked": False,
                "data_tip": "以上分析基于系统内现有数据，数据不完整时结论仅供参考",
            }

        except Exception as e:
            call_log.status = "failed"
            call_log.error_message = str(e)
            self.db.add(call_log)
            logger.error(f"AI调用失败: {e}")
            return {
                "answer": "AI服务暂时不可用，请稍后重试或联系管理员。",
                "error": str(e),
                "permission_blocked": False,
            }

    async def _call_ai(
        self,
        system_prompt: str,
        user_content: str,
        *,
        json_mode: bool = False,
        model_override: str | None = None,
    ) -> dict:
        """调用AI API（支持百炼/DeepSeek/OpenAI兼容）"""
        provider = settings.AI_PROVIDER

        if provider == "dashscope" and settings.DASHSCOPE_API_KEY:
            return await self._call_openai_compatible(
                base_url=settings.DASHSCOPE_BASE_URL,
                api_key=settings.DASHSCOPE_API_KEY,
                model=model_override or settings.DASHSCOPE_MODEL,
                system_prompt=system_prompt,
                user_content=user_content,
                json_mode=json_mode,
            )
        elif provider == "deepseek" and settings.DEEPSEEK_API_KEY:
            return await self._call_openai_compatible(
                base_url=settings.DEEPSEEK_BASE_URL,
                api_key=settings.DEEPSEEK_API_KEY,
                model=model_override or settings.DEEPSEEK_MODEL,
                system_prompt=system_prompt,
                user_content=user_content,
                json_mode=json_mode,
            )
        else:
            raise ValueError(f"AI提供商未配置或API Key为空: provider={provider}")

    async def _call_business_advice(self, system_prompt: str, user_content: str) -> dict:
        """经营建议固定走 DeepSeek 专用配置，不继承通用问答提供商。"""
        if not settings.DEEPSEEK_API_KEY:
            raise ValueError("DeepSeek API Key 未配置")
        return await self._call_openai_compatible(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            model=settings.AI_BUSINESS_ADVICE_MODEL,
            system_prompt=system_prompt,
            user_content=user_content,
            json_mode=True,
        )

    async def _call_openai_compatible(
        self, base_url: str, api_key: str, model: str,
        system_prompt: str, user_content: str, json_mode: bool = False
    ) -> dict:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 4000 if json_mode else 2000,
            "temperature": 0.1 if json_mode else 0.3,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=settings.AI_BUSINESS_ADVICE_TIMEOUT_SECONDS) as client:
            resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            raise ValueError(f"AI API错误: {data['error']}")

        choices = data.get("choices", [])
        if not choices:
            raise ValueError("AI返回空结果")

        content = choices[0]["message"].get("content") or ""
        # 剥离 <think> 标签（推理模型）
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        usage = data.get("usage", {})
        return {
            "content": content,
            "model": data.get("model", model),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }

    def _get_allowed_fields(self, user_roles: list[str]) -> set[str]:
        """根据角色返回允许查看的敏感字段集合"""
        allowed = set()
        boss_roles = {"super_admin", "boss", "shareholder", "ceo"}
        finance_roles = {"finance_manager", "finance"}
        if any(r in boss_roles for r in user_roles):
            allowed.update(["profit", "cost", "cash", "member_phone"])
        if any(r in finance_roles for r in user_roles):
            allowed.update(["profit", "cash"])
        if "product_manager" in user_roles:
            allowed.update(["cost"])
        return allowed

    def _check_sensitive_query(self, question: str, allowed_fields: set[str]) -> list[str]:
        """检查问题是否触及无权限字段"""
        blocked = []
        sensitive_keywords = {
            "profit": ["利润", "毛利", "盈利", "亏损"],
            "cost": ["成本", "进价"],
            "cash": ["现金", "银行余额", "账上"],
            "member_phone": ["手机号", "电话号码", "联系方式"],
        }
        for field, keywords in sensitive_keywords.items():
            if field not in allowed_fields:
                if any(kw in question for kw in keywords):
                    blocked.append(field)
        return blocked

    def _filter_context_data(self, data: dict, allowed_fields: set[str]) -> dict:
        """过滤上下文数据中的敏感字段"""
        result = {}
        for k, v in data.items():
            for perm, fields in SENSITIVE_FIELDS_BY_PERMISSION.items():
                if k in fields and perm not in allowed_fields:
                    result[k] = "***（无权限）"
                    break
            else:
                result[k] = v
        return result

    def _validate_ai_output(self, answer: str):
        """检查AI输出是否包含禁止结论（不抛异常，只记录警告）"""
        for pattern in FORBIDDEN_CONCLUSIONS:
            if pattern in answer:
                logger.warning(f"AI输出包含禁止结论模式: {pattern}")

    def _build_system_prompt(self, user_roles: list[str], allowed_fields: set[str]) -> str:
        role_desc = ", ".join(user_roles) if user_roles else "普通用户"
        return f"""你是华邦服装公司AI经营助手。当前用户角色：{role_desc}。

核心规则（必须严格遵守）：
1. 只基于提供的真实数据回答，绝不编造数据或假设数据
2. 数据不完整时，必须明确说明"数据不完整，以下分析仅供参考"
3. 只能查看权限范围内的数据，越权数据不得展示
4. 只做诊断、解释、建议，不能说"已自动执行"、"已下单"、"已改价"等实际操作
5. 所有建议必须有数据依据，不能凭空建议
6. 高风险操作（下采购单/改价格/调库存/处罚员工）必须提示"需要人工确认"
7. 预测数据必须标注为"预测"，实际数据标注来源

当前用户可查看的数据范围：{", ".join(allowed_fields) if allowed_fields else "基础销售数据"}"""
