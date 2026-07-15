"""AI诊断引擎（规则优先 + AI摘要 + 权限过滤 + 格式固定）"""
import logging
import httpx
import json
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.log import LogAiCall
from app.models.sys import SysUser

logger = logging.getLogger(__name__)

# AI禁止输出的敏感结论模式（后处理检查）
FORBIDDEN_CONCLUSIONS = [
    "已下单", "已采购", "已改价", "已调库存", "已扣款", "已罚款",
    "自动完成", "已执行", "已生成凭证",
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
FORBIDDEN_INCOMPLETE_FINANCE_CLAIMS = (
    "公司盈利", "公司亏损", "最终盈利", "最终亏损", "实现盈利", "实现亏损",
    "利润为正", "利润为负", "净利润为",
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
        reason = raw.get("reason")
        if status == "pending_data":
            value = None
        if key == "operating_profit" and not finance_complete:
            if value is None or status != "estimated":
                value = None
                status = "pending_data"
            else:
                status = "estimated"
            reason = reason or "费用未完整接入，经营利润仅为估算值"
        metrics[key] = {
            "label": COMMAND_METRIC_LABELS[key],
            "value": value,
            "status": status,
            "source": source,
            "as_of": raw.get("as_of"),
            "reason": reason,
        }

    rules = []
    for raw in (context.get("rules") or [])[:50]:
        if not isinstance(raw, dict) or not raw.get("id") or not raw.get("title"):
            continue
        rules.append({
            "id": str(raw["id"]),
            "title": str(raw["title"]),
            "level": str(raw.get("level") or "warning"),
            "evidence": [str(value) for value in (raw.get("evidence") or [])[:10]],
            "source": str(raw.get("source") or "rule_engine"),
        })

    tasks = []
    for raw in (context.get("tasks") or [])[:50]:
        if not isinstance(raw, dict) or raw.get("id") is None:
            continue
        tasks.append({
            "id": raw["id"],
            "title": str(raw.get("title") or ""),
            "status": str(raw.get("status") or ""),
            "owner": str(raw.get("owner") or ""),
            "due_date": raw.get("due_date"),
        })
    return {
        "metrics": metrics,
        "rules": rules,
        "tasks": tasks,
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
                "key": key,
                "label": metric["label"],
                "value": metric["value"],
                "status": status,
                "source": metric["source"],
                "as_of": metric.get("as_of"),
                "reason": metric.get("reason"),
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
        "id": rule["id"],
        "title": rule["title"],
        "level": rule["level"],
        "evidence": rule["evidence"],
        "source": rule["source"],
    } for rule in context.get("rules", [])]
    recommendations = [{
        "title": f"复核{risk['title']}",
        "reason": "依据确定性规则和原始证据处理，执行前由负责人确认。",
        "evidence": [risk["id"]],
    } for risk in risks[:5]]
    actions = [{
        "title": f"处理{risk['title']}",
        "owner": "待主管确认",
        "status": "draft",
        "requires_human_confirm": True,
        "evidence": [risk["id"], *risk.get("evidence", [])[:3]],
    } for risk in risks[:5]]
    return {
        "facts": facts,
        "risks": risks,
        "recommendations": recommendations,
        "actions": actions,
        "limitations": list(dict.fromkeys(str(item) for item in limitations if item)),
    }


def validate_command_conclusion(payload: dict[str, Any], *, finance_complete: bool) -> dict[str, Any]:
    if not isinstance(payload, dict) or any(not isinstance(payload.get(key), list) for key in COMMAND_OUTPUT_KEYS):
        raise ValueError("AI经营结论结构不合法")
    if set(payload) != set(COMMAND_OUTPUT_KEYS):
        raise ValueError("AI经营结论包含未授权字段")
    rendered = json.dumps(payload, ensure_ascii=False)
    if any(pattern in rendered for pattern in FORBIDDEN_CONCLUSIONS):
        raise ValueError("AI经营结论包含禁止的执行结果表述")
    if not finance_complete and any(pattern in rendered for pattern in FORBIDDEN_INCOMPLETE_FINANCE_CLAIMS):
        raise ValueError("费用不完整时禁止输出确定性盈亏结论")

    for key in ("facts", "risks", "recommendations"):
        if any(not isinstance(item, dict) or not item.get("title", item.get("label")) for item in payload[key]):
            raise ValueError(f"AI经营结论的{key}结构不合法")
    if any(not isinstance(item.get("evidence", []), list) for item in payload["recommendations"]):
        raise ValueError("AI建议证据结构不合法")
    if any(not isinstance(item, str) for item in payload["limitations"]):
        raise ValueError("AI经营结论的数据限制结构不合法")
    for action in payload["actions"]:
        if not isinstance(action, dict) or not action.get("title"):
            raise ValueError("AI行动结构不合法")
        if not isinstance(action.get("evidence", []), list):
            raise ValueError("AI行动证据结构不合法")
        if action.get("status") not in (None, "draft") or action.get("requires_human_confirm") is not True:
            raise ValueError("AI行动必须是待人工确认的草稿")
        action["status"] = "draft"
        action["requires_human_confirm"] = True
    payload["facts"] = payload["facts"][:50]
    payload["risks"] = payload["risks"][:50]
    payload["recommendations"] = payload["recommendations"][:10]
    payload["actions"] = payload["actions"][:10]
    payload["limitations"] = payload["limitations"][:20]
    return payload


def validate_model_grounding(
    payload: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    """Reject model facts or risks that cannot be traced to the supplied context."""
    fallback = build_template_command_conclusion(context)
    metrics = context.get("metrics") or {}
    for fact in payload.get("facts", []):
        key = fact.get("key") if isinstance(fact, dict) else None
        metric = metrics.get(key)
        if not metric:
            raise ValueError("AI事实缺少已接入指标来源")
        if metric.get("status") not in {"ready", "estimated"} or metric.get("value") is None:
            raise ValueError("AI事实引用了未就绪指标")
        if fact.get("label") != metric.get("label"):
            raise ValueError("AI事实名称与来源数据不一致")
        for field in ("value", "status", "source", "as_of", "reason"):
            if fact.get(field) != metric.get(field):
                raise ValueError(f"AI事实的{field}与来源数据不一致")

    rules = {item["id"]: item for item in context.get("rules", [])}
    for risk in payload.get("risks", []):
        source = rules.get(risk.get("id")) if isinstance(risk, dict) else None
        if not source or any(
            risk.get(field) != source.get(field)
            for field in ("title", "level", "source", "evidence")
        ):
            raise ValueError("AI风险缺少确定性规则来源")

    expected_fact_keys = {item["key"] for item in fallback["facts"]}
    actual_fact_keys = {item.get("key") for item in payload.get("facts", [])}
    if actual_fact_keys != expected_fact_keys:
        raise ValueError("AI事实未完整覆盖已就绪指标")

    expected_risk_ids = set(rules)
    actual_risk_ids = {item.get("id") for item in payload.get("risks", [])}
    if actual_risk_ids != expected_risk_ids:
        raise ValueError("AI风险未完整覆盖确定性规则")

    allowed_evidence = {
        key for key, metric in metrics.items()
        if metric.get("status") in {"ready", "estimated"} and metric.get("value") is not None
    } | set(rules)
    grounded_recommendations = []
    seen_evidence = set()
    for recommendation in payload.get("recommendations", []):
        evidence = {str(item) for item in recommendation.get("evidence", [])}
        if len(evidence) != 1 or not evidence.issubset(allowed_evidence):
            raise ValueError("AI建议缺少指标或规则证据")
        evidence_id = next(iter(evidence))
        if evidence_id in seen_evidence:
            continue
        seen_evidence.add(evidence_id)
        if evidence_id in rules:
            title = f"复核{rules[evidence_id]['title']}"
        else:
            title = f"复核{metrics[evidence_id]['label']}"
        grounded_recommendations.append({
            "title": title,
            "reason": "依据已接入指标或确定性规则处理，执行前由负责人确认。",
            "evidence": [evidence_id],
        })
    if fallback["recommendations"] and not grounded_recommendations:
        raise ValueError("AI建议遗漏已有经营风险")

    known_limitations = set(fallback["limitations"])
    if set(payload.get("limitations", [])) != known_limitations:
        raise ValueError("AI数据限制未完整匹配系统来源")
    payload["facts"] = fallback["facts"]
    payload["risks"] = fallback["risks"]
    payload["recommendations"] = grounded_recommendations
    payload["actions"] = fallback["actions"]
    payload["limitations"] = fallback["limitations"]
    return payload


def parse_model_json(content: str) -> dict[str, Any]:
    text_content = str(content or "").strip()
    if text_content.startswith("```"):
        lines = text_content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text_content = "\n".join(lines).strip()
    payload = json.loads(text_content)
    if not isinstance(payload, dict):
        raise ValueError("AI经营结论必须是JSON对象")
    return payload


class AIEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_command_conclusion(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """Build an auditable conclusion exclusively from sourced metrics and deterministic rules."""
        safe_context = sanitize_command_context(context_data)
        fallback = build_template_command_conclusion(safe_context)
        system_prompt = """你是华邦老板经营指挥台的经营分析模型。
只能使用输入中的指标、确定性规则和任务，不得补充、猜测或改写任何数值、状态、来源和规则事实。
费用不完整时不得判断公司盈利、亏损、净利润或最终经营结果。
所有行动必须保持 status=draft、requires_human_confirm=true，并引用输入中的规则ID作为 evidence。
facts必须包含全部已就绪或预估指标，risks必须包含全部输入规则，limitations必须完整保留示例中的系统限制。
recommendations只能选择一个已就绪指标键或规则ID放入evidence，标题和原因会由系统重新生成。
只输出JSON，不要Markdown，不要解释。JSON必须包含且只需包含 facts、risks、recommendations、actions、limitations 五个数组。"""
        user_content = json.dumps(
            {"context": safe_context, "required_shape_example": fallback},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            response = await self._call_ai(system_prompt, user_content)
        except Exception as exc:
            logger.warning("AI经营结论调用失败，回退到确定性模板: %s", exc)
            fallback.update({
                "mode": "template",
                "model_used": "deterministic_rules",
                "fallback_reason": "model_unavailable",
            })
            return fallback

        try:
            result = parse_model_json(response.get("content", ""))
            result = validate_command_conclusion(
                result, finance_complete=bool(safe_context.get("finance_complete"))
            )
            result = validate_model_grounding(result, safe_context)
            result.update({
                "mode": "model",
                "model_used": response.get("model") or settings.DEEPSEEK_MODEL,
                "fallback_reason": None,
            })
            return result
        except Exception as exc:
            logger.warning("AI经营结论校验失败，回退到确定性模板: %s", exc)
            fallback.update({
                "mode": "template",
                "model_used": "deterministic_rules",
                "fallback_reason": "model_output_invalid",
            })
            return fallback

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

    async def _call_ai(self, system_prompt: str, user_content: str) -> dict:
        """调用AI API（支持百炼/DeepSeek/OpenAI兼容）"""
        provider = settings.AI_PROVIDER

        if provider == "dashscope" and settings.DASHSCOPE_API_KEY:
            return await self._call_openai_compatible(
                base_url=settings.DASHSCOPE_BASE_URL,
                api_key=settings.DASHSCOPE_API_KEY,
                model=settings.DASHSCOPE_MODEL,
                system_prompt=system_prompt,
                user_content=user_content,
            )
        elif provider == "deepseek" and settings.DEEPSEEK_API_KEY:
            return await self._call_openai_compatible(
                base_url=settings.DEEPSEEK_BASE_URL,
                api_key=settings.DEEPSEEK_API_KEY,
                model=settings.DEEPSEEK_MODEL,
                system_prompt=system_prompt,
                user_content=user_content,
            )
        else:
            raise ValueError(f"AI提供商未配置或API Key为空: provider={provider}")

    async def _call_openai_compatible(
        self, base_url: str, api_key: str, model: str,
        system_prompt: str, user_content: str
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
            "max_tokens": 2000,
            "temperature": 0.3,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            raise ValueError(f"AI API错误: {data['error']}")

        choices = data.get("choices", [])
        if not choices:
            raise ValueError("AI返回空结果")

        content = choices[0]["message"]["content"]
        # 剥离 <think> 标签（推理模型）
        import re
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
