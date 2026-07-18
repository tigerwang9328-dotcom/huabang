"""老板 AI 助手：只读经营问答、会话、脱敏联网经验。"""
from __future__ import annotations

import re
import json
import hashlib
import inspect
import time
from dataclasses import dataclass
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import get_redis, rate_limit_check
from app.core.store_whitelist import ALLOWED_STORE_CODES
from app.models.ai import AiAssistantConversation, AiAssistantMessage, AiBusinessAdviceSnapshot
from app.models.log import LogAiCall
from app.services.ai_engine import AIEngine, contains_sensitive_text


ASSISTANT_ALLOWED_ROLES = {
    "boss", "ceo", "shareholder", "admin", "super_admin",
    "owner", "administrator", "general_manager",
}
ASSISTANT_PROMPT_VERSION = "assistant-chat-v1"
ASSISTANT_MODULES = (
    "overview", "sales", "products", "inventory", "finance",
    "hr", "members", "audit", "action-tasks",
)
EXTERNAL_INTENT_TOKENS = ("外部", "经验", "同行", "行业", "怎么做", "案例", "服装零售")
INTERNAL_INTENT_TOKENS = (
    "华邦", "公司", "门店", "销售", "库存", "商品", "财务", "费用", "员工", "人力",
    "会员", "稽核", "任务", "经营", "数据", "快照", "利润", "毛利",
)
MODULE_KEYWORDS = {
    "sales": ("销售", "实收", "退货", "业绩"),
    "products": ("商品", "款", "sku", "SKU", "动销", "滞销"),
    "inventory": ("库存", "仓", "断码", "调拨", "补货"),
    "finance": ("利润", "费用", "财务", "毛利", "盈亏"),
    "hr": ("人力", "员工", "导购", "考勤", "人效"),
    "members": ("会员", "vip", "VIP", "回访", "储值"),
    "audit": ("稽核", "预警"),
    "action-tasks": ("任务", "行动", "闭环", "跟进"),
}
_TAVILY_CACHE: dict[str, tuple[float, list[dict[str, str]]]] = {}
_RATE_LIMIT_BUCKET: dict[int, list[float]] = {}


def wants_external_experience(question: str) -> bool:
    return any(token in question for token in EXTERNAL_INTENT_TOKENS)


def has_internal_business_intent(question: str) -> bool:
    return any(token in question for token in INTERNAL_INTENT_TOKENS)


@dataclass(frozen=True)
class AssistantContext:
    stat_date: str | None
    store_code: str | None
    scope_type: str
    modules: list[str]


def is_assistant_role_allowed(user: Any, roles: list[str]) -> bool:
    if bool(getattr(user, "is_admin", False)):
        return True
    normalized = {str(role).strip().lower() for role in roles}
    return bool(normalized & ASSISTANT_ALLOWED_ROLES)


def sanitize_tavily_query(question: str) -> str:
    value = str(question or "")
    value = re.sub(r"(?<![A-Za-z0-9])(?:134681|285204|285702|185805|185808|285101|285102|GZ001|GZ002|GYNG|gz002)(?![A-Za-z0-9])", " ", value)
    value = re.sub(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?%?(?![A-Za-z0-9])", " ", value)
    value = re.sub(r"1[3-9]\d{9}", " ", value)
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", " ", value)
    value = re.sub(r"[\u4e00-\u9fff]{2,3}(?=(?:昨天|今日|审批|备注|会员|员工|导购|负责|复核|处理|联系))", " ", value)
    value = re.sub(r"(员工|导购|负责人|会员|客户)[\u4e00-\u9fff]{2,3}", r"\1 ", value)
    value = re.sub(r"(?:员工|导购|负责人|会员|客户|审批|备注|手机号|门店编码|金额|比例|原始问题|原始数据|JSON|cookie|token|secret)", " ", value, flags=re.I)
    terms = [part for part in re.split(r"[，。！？、\s,.;:!?]+", value) if part]
    cleaned = " ".join(terms)
    if "服装" not in cleaned and "零售" not in cleaned:
        cleaned = f"服装零售 {cleaned}".strip()
    return cleaned[:80] or "服装零售经营优化经验"


def parse_assistant_context(
    *,
    question: str,
    route: str | None,
    stat_date: str | None,
    store_code: str | None,
    today: date | None = None,
) -> AssistantContext:
    current_day = today or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    parsed_date = stat_date
    if not parsed_date:
        route_date = re.search(r"(?:stat_date|date)=([0-9]{4}-[0-9]{2}-[0-9]{2})", route or "")
        if route_date:
            parsed_date = route_date.group(1)
    if not parsed_date and "昨天" in question:
        parsed_date = (current_day - timedelta(days=1)).isoformat()
    if not parsed_date and ("今天" in question or "今日" in question):
        parsed_date = current_day.isoformat()

    parsed_store = store_code
    if not parsed_store:
        route_store = re.search(r"store_code=([A-Za-z0-9]+)", route or "")
        if route_store:
            parsed_store = route_store.group(1).upper()
    if not parsed_store:
        for code in sorted(ALLOWED_STORE_CODES):
            if code.lower() in question.lower():
                parsed_store = code
                break
    if parsed_store and parsed_store.upper() == "GZ002":
        parsed_store = "GZ002"

    text = f"{route or ''} {question}"
    modules = []
    route_map = {
        "sales": "sales",
        "products": "products",
        "product": "products",
        "inventory": "inventory",
        "finance": "finance",
        "hr": "hr",
        "members": "members",
        "member": "members",
        "audit": "audit",
        "actions": "action-tasks",
        "task": "action-tasks",
    }
    for token, module in route_map.items():
        if f"/{token}" in (route or "") and module not in modules:
            modules.append(module)
    for module, keywords in MODULE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords) and module not in modules:
            modules.append(module)
    if not modules:
        modules = ["overview"]
    return AssistantContext(
        stat_date=parsed_date,
        store_code=parsed_store,
        scope_type="store" if parsed_store else "company",
        modules=[module for module in modules if module in ASSISTANT_MODULES],
    )


async def _get_redis_client() -> Any:
    client = get_redis()
    if inspect.isawaitable(client):
        return await client
    return client


def _data_as_of(snapshots: list[Any]) -> str | None:
    dates = [item.stat_date for item in snapshots if getattr(item, "stat_date", None)]
    if not dates:
        return None
    latest = max(dates)
    return latest.isoformat() if hasattr(latest, "isoformat") else str(latest)


def _dedupe_text_items(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        text = str(item.get("text") or item.get("title") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _coerce_confidence(value: str | None, data_status: str) -> str:
    if data_status in {"estimated", "stale"} and value == "high":
        return "medium"
    if value in {"high", "medium", "low"}:
        return value
    return "medium"


def _finding_from_snapshot(snapshot: Any) -> list[dict[str, Any]]:
    conclusion = snapshot.conclusion or {}
    data_status = snapshot.data_status or "pending_data"
    findings: list[dict[str, Any]] = []
    for item in conclusion.get("key_findings") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("title") or "").strip()
        if not text:
            continue
        findings.append({
            "text": text,
            "evidence_refs": list(item.get("evidence_refs") or []),
            "confidence": _coerce_confidence(item.get("confidence"), data_status),
        })
    if not findings:
        summary = str(conclusion.get("executive_summary") or "").strip()
        if summary:
            findings.append({
                "text": summary,
                "evidence_refs": [],
                "confidence": _coerce_confidence("medium", data_status),
            })
    return findings


def _actions_from_snapshots(snapshots: list[Any], limit: int = 3) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for snapshot in snapshots:
        for item in (snapshot.conclusion or {}).get("recommendations") or []:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("title") or "").strip()
            if not text:
                continue
            actions.append({
                "text": text,
                "evidence_refs": list(item.get("evidence_refs") or []),
                "requires_human_confirm": True,
                "executed": False,
            })
    return _dedupe_text_items(actions, limit)


def _limitations_from_snapshots(snapshots: list[Any]) -> list[str]:
    limitations = []
    for snapshot in snapshots:
        status = snapshot.data_status or "pending_data"
        if status == "pending_data":
            limitations.append("存在待接入数据，未展示对应数值。")
        elif status == "stale":
            limitations.append("部分数据较旧，需要先核验最新同步结果。")
        elif status == "estimated":
            limitations.append("部分指标为估算值，结论置信度最高为中。")
        for item in (snapshot.conclusion or {}).get("limitations") or []:
            if isinstance(item, str) and item.strip():
                limitations.append(item.strip())
    return list(dict.fromkeys(limitations))[:8]


def build_brief_payload(snapshots: list[Any]) -> dict[str, Any]:
    counts = Counter(getattr(item, "data_status", "pending_data") or "pending_data" for item in snapshots)
    findings = []
    for snapshot in snapshots:
        if (snapshot.data_status or "pending_data") == "pending_data":
            continue
        findings.extend(_finding_from_snapshot(snapshot))
    actions = _actions_from_snapshots(snapshots)
    return {
        "data_as_of": _data_as_of(snapshots),
        "data_health": {
            "ready": counts.get("ready", 0),
            "estimated": counts.get("estimated", 0),
            "stale": counts.get("stale", 0),
            "pending_data": counts.get("pending_data", 0),
        },
        "findings": _dedupe_text_items(findings, 3),
        "actions": actions[:3],
        "suggested_questions": [
            "昨天整体经营最需要关注什么？",
            "哪些门店或模块的数据需要先核验？",
            "库存和销售之间有什么风险信号？",
            "如果参考服装零售经验，下一步该怎么做？",
        ],
    }


def build_deterministic_answer(
    *,
    question: str,
    snapshots: list[Any],
    external_findings: list[dict[str, Any]],
    used_web: bool,
    requested_web: bool = False,
) -> dict[str, Any]:
    findings = []
    evidence = []
    for snapshot in snapshots:
        findings.extend(_finding_from_snapshot(snapshot))
        safe_context = snapshot.safe_context or {}
        for key, metric in (safe_context.get("metrics") or {}).items():
            if not isinstance(metric, dict):
                continue
            if metric.get("status") == "pending_data":
                evidence.append({
                    "ref": metric.get("fact_id") or f"fact:{key}",
                    "label": metric.get("label") or key,
                    "status": "pending_data",
                    "value": None,
                    "source": metric.get("source"),
                })
                continue
            evidence.append({
                "ref": metric.get("fact_id") or f"fact:{key}",
                "label": metric.get("label") or key,
                "status": metric.get("status"),
                "value": metric.get("value"),
                "unit": metric.get("unit"),
                "source": metric.get("source"),
            })
    answer_type = "internal"
    if requested_web:
        answer_type = "mixed" if has_internal_business_intent(question) and snapshots else "external"
    elif used_web and external_findings:
        answer_type = "mixed"
    if not snapshots and external_findings:
        answer_type = "external"
    limitations = _limitations_from_snapshots(snapshots)
    if requested_web and not external_findings:
        limitations.append("外部经验检索暂不可用，本次仅返回华邦中台事实。")
    if not snapshots:
        limitations.append("当前没有可用经营快照，请先确认九模块快照生成状态。")
    return {
        "answer_type": answer_type,
        "summary": "已基于华邦经营快照生成只读分析；建议仅作为人工决策参考。",
        "findings": _dedupe_text_items(findings, 6),
        "evidence": evidence[:30],
        "external_findings": external_findings[:5],
        "sources": [
            {"title": item.get("title"), "url": item.get("url")}
            for item in external_findings[:5]
            if item.get("url")
        ],
        "actions": _actions_from_snapshots(snapshots, 5),
        "limitations": list(dict.fromkeys(limitations))[:10],
        "suggested_questions": [
            "这个结论需要先核验哪些数据？",
            "哪些建议可以安排人工复盘？",
            "同类服装零售公司通常怎么处理？",
        ],
        "data_as_of": _data_as_of(snapshots),
        "used_web": used_web and bool(external_findings),
    }


def validate_assistant_model_answer(payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    required = {
        "answer_type", "summary", "findings", "evidence", "external_findings",
        "sources", "actions", "limitations", "suggested_questions", "data_as_of", "used_web",
    }
    if not isinstance(payload, dict) or not required <= set(payload):
        raise ValueError("助手模型回答结构不合法")
    allowed_refs = {str(item.get("ref")) for item in fallback.get("evidence", []) if item.get("ref")}
    text_values = [payload.get("summary") or ""]
    text_values.extend(str(item) for item in payload.get("limitations") or [])
    text_values.extend(str(item) for item in payload.get("suggested_questions") or [])
    if payload.get("used_web") and not fallback.get("used_web"):
        raise ValueError("助手模型错误声明使用了联网经验")
    for item in payload.get("findings") or []:
        if not isinstance(item, dict):
            raise ValueError("助手模型 findings 结构不合法")
        text_values.append(str(item.get("text") or ""))
        refs = [str(ref) for ref in item.get("evidence_refs") or []]
        if refs and not set(refs) <= allowed_refs:
            raise ValueError("助手模型证据引用不合法")
        if item.get("confidence") not in {"high", "medium", "low"}:
            item["confidence"] = "medium"
    for action in payload.get("actions") or []:
        if not isinstance(action, dict):
            raise ValueError("助手模型 actions 结构不合法")
        text_values.append(str(action.get("text") or action.get("title") or ""))
        action["requires_human_confirm"] = True
        action["executed"] = False
    if any(contains_sensitive_text(value) for value in text_values if value):
        raise ValueError("助手模型回答包含敏感文本")
    payload["evidence"] = fallback.get("evidence", [])
    payload["external_findings"] = fallback.get("external_findings", [])
    payload["sources"] = fallback.get("sources", [])
    payload["data_as_of"] = fallback.get("data_as_of")
    payload["used_web"] = fallback.get("used_web", False)
    payload["answer_type"] = fallback.get("answer_type", payload.get("answer_type"))
    return payload


class AiAssistantService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def assert_allowed(self, user: Any, roles: list[str]) -> None:
        if not settings.AI_ASSISTANT_ENABLED:
            raise PermissionError("老板AI助手未启用")
        if not is_assistant_role_allowed(user, roles):
            raise PermissionError("仅老板、CEO、股东和管理员可使用老板AI助手")

    async def check_rate_limit(self, user_id: int) -> bool:
        try:
            return await rate_limit_check(
                f"ai-assistant:rate:{user_id}",
                settings.AI_ASSISTANT_RATE_LIMIT_PER_MINUTE,
                60,
            )
        except Exception:
            pass
        now = time.time()
        bucket = [item for item in _RATE_LIMIT_BUCKET.get(user_id, []) if now - item < 60]
        if len(bucket) >= settings.AI_ASSISTANT_RATE_LIMIT_PER_MINUTE:
            _RATE_LIMIT_BUCKET[user_id] = bucket
            return False
        bucket.append(now)
        _RATE_LIMIT_BUCKET[user_id] = bucket
        return True

    async def latest_snapshots(
        self,
        *,
        stat_date: str | None = None,
        store_code: str | None = None,
        modules: list[str] | None = None,
    ) -> list[AiBusinessAdviceSnapshot]:
        target_date = date.fromisoformat(stat_date) if stat_date else None
        if target_date is None:
            target_date = (await self.db.execute(select(AiBusinessAdviceSnapshot.stat_date).order_by(desc(AiBusinessAdviceSnapshot.stat_date)).limit(1))).scalar_one_or_none()
        if target_date is None:
            return []
        statement = select(AiBusinessAdviceSnapshot).where(AiBusinessAdviceSnapshot.stat_date == target_date)
        if store_code:
            statement = statement.where(
                AiBusinessAdviceSnapshot.scope_type == "store",
                AiBusinessAdviceSnapshot.target_code == store_code,
            )
        else:
            statement = statement.where(AiBusinessAdviceSnapshot.scope_type == "company")
        if modules:
            statement = statement.where(AiBusinessAdviceSnapshot.module.in_(modules))
        result = await self.db.execute(statement.order_by(AiBusinessAdviceSnapshot.module))
        return list(result.scalars().all())

    async def brief(self, *, stat_date: str | None = None, store_code: str | None = None) -> dict[str, Any]:
        return build_brief_payload(await self.latest_snapshots(stat_date=stat_date, store_code=store_code))

    async def list_conversations(self, user_id: int) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(AiAssistantConversation)
            .where(AiAssistantConversation.user_id == user_id, AiAssistantConversation.is_archived == False)
            .order_by(desc(AiAssistantConversation.last_message_at))
        )
        return [self._conversation_payload(item) for item in result.scalars().all()]

    async def create_conversation(self, user_id: int, *, route: str | None, stat_date: str | None, store_code: str | None) -> dict[str, Any]:
        item = AiAssistantConversation(
            user_id=user_id,
            title="新对话",
            route=route,
            stat_date=date.fromisoformat(stat_date) if stat_date else None,
            store_code=store_code,
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return self._conversation_payload(item)

    async def get_owned_conversation(self, user_id: int, conversation_id: int) -> AiAssistantConversation | None:
        result = await self.db.execute(select(AiAssistantConversation).where(
            AiAssistantConversation.id == conversation_id,
            AiAssistantConversation.user_id == user_id,
            AiAssistantConversation.is_archived == False,
        ))
        return result.scalar_one_or_none()

    async def list_messages(self, user_id: int, conversation_id: int) -> list[dict[str, Any]]:
        if not await self.get_owned_conversation(user_id, conversation_id):
            return []
        result = await self.db.execute(
            select(AiAssistantMessage)
            .where(AiAssistantMessage.conversation_id == conversation_id, AiAssistantMessage.user_id == user_id)
            .order_by(AiAssistantMessage.created_at)
        )
        return [self._message_payload(item) for item in result.scalars().all()]

    async def archive_conversation(self, user_id: int, conversation_id: int) -> bool:
        result = await self.db.execute(update(AiAssistantConversation).where(
            AiAssistantConversation.id == conversation_id,
            AiAssistantConversation.user_id == user_id,
            AiAssistantConversation.is_archived == False,
        ).values(is_archived=True, archived_at=datetime.now(timezone.utc)))
        await self.db.commit()
        return bool(result.rowcount)

    async def ask(
        self,
        *,
        user: Any,
        roles: list[str],
        conversation_id: int,
        question: str,
        route: str | None,
        stat_date: str | None,
        store_code: str | None,
        web_mode: str = "auto",
    ) -> dict[str, Any]:
        self.assert_allowed(user, roles)
        if not await self.check_rate_limit(int(user.id)):
            raise RuntimeError("提问过于频繁，请稍后再试")
        conversation = await self.get_owned_conversation(int(user.id), conversation_id)
        if not conversation:
            raise LookupError("会话不存在或无权访问")
        parsed = parse_assistant_context(
            question=question,
            route=route,
            stat_date=stat_date,
            store_code=store_code,
        )
        context = {
            "route": route,
            "stat_date": parsed.stat_date,
            "store_code": parsed.store_code,
            "scope_type": parsed.scope_type,
            "modules": parsed.modules,
            "web_mode": web_mode,
        }
        snapshots = await self.latest_snapshots(
            stat_date=parsed.stat_date,
            store_code=parsed.store_code,
            modules=parsed.modules,
        )
        external = []
        requested_web = web_mode == "auto" and wants_external_experience(question)
        if requested_web and self._should_search(question):
            external = await self.search_external_experience(question)
        answer = build_deterministic_answer(
            question=question,
            snapshots=snapshots,
            external_findings=external,
            used_web=bool(external),
            requested_web=requested_web,
        )
        model_meta = {"model": "deterministic_template", "provider": "internal"}
        model_answer = await self.generate_model_answer(question=question, fallback=answer)
        if model_answer:
            answer = model_answer["answer"]
            model_meta = {"model": model_answer["model"], "provider": "deepseek"}
        self.db.add(AiAssistantMessage(
            conversation_id=conversation_id,
            user_id=int(user.id),
            role="user",
            content=question,
            context=context,
        ))
        self.db.add(AiAssistantMessage(
            conversation_id=conversation_id,
            user_id=int(user.id),
            role="assistant",
            content=answer["summary"],
            answer_payload=answer,
            sources=answer["sources"],
            context=context,
            used_web=answer["used_web"],
        ))
        conversation.title = question[:40] or conversation.title
        conversation.route = route or conversation.route
        conversation.store_code = store_code or conversation.store_code
        conversation.last_message_at = datetime.now(timezone.utc)
        self.db.add(LogAiCall(
            user_id=int(user.id),
            user_role=",".join(roles)[:64],
            call_type="assistant_chat",
            user_question=question[:500],
            data_scope=f"route={route or ''};date={parsed.stat_date or ''};store={parsed.store_code or ''};modules={','.join(parsed.modules)}",
            prompt_version=ASSISTANT_PROMPT_VERSION,
            model_name=model_meta["model"],
            ai_provider=model_meta["provider"],
            response_summary=answer["summary"][:500],
            permission_blocked=False,
            data_quality_blocked=bool(answer["limitations"]),
            status="success",
        ))
        await self.db.commit()
        return answer

    async def generate_model_answer(self, *, question: str, fallback: dict[str, Any]) -> dict[str, Any] | None:
        if not settings.DEEPSEEK_API_KEY:
            return None
        system_prompt = (
            "你是华邦老板AI助手。只根据输入的聚合事实、证据卡和网页摘要回答。"
            "必须返回JSON，字段固定为 answer_type, summary, findings, evidence, external_findings, "
            "sources, actions, limitations, suggested_questions, data_as_of, used_web。"
            "findings 每项包含 text, evidence_refs, confidence；actions 每项必须 requires_human_confirm=true 且 executed=false。"
            "不能编造证据，不能声称已执行业务动作，不能输出手机号、员工/会员姓名、审批备注、Cookie、Token 或原始JSON。"
        )
        safe_payload = {
            "question": sanitize_tavily_query(question),
            "fallback_answer": fallback,
        }
        try:
            result = await AIEngine(self.db)._call_openai_compatible(
                base_url=settings.DEEPSEEK_BASE_URL,
                api_key=settings.DEEPSEEK_API_KEY,
                model=settings.DEEPSEEK_MODEL,
                system_prompt=system_prompt,
                user_content=json.dumps(safe_payload, ensure_ascii=False, default=str),
                json_mode=True,
            )
            payload = validate_assistant_model_answer(json.loads(result["content"]), fallback)
        except Exception:
            return None
        return {"answer": payload, "model": result.get("model") or settings.DEEPSEEK_MODEL}

    async def cleanup_archived(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.AI_ASSISTANT_HISTORY_RETENTION_DAYS)
        result = await self.db.execute(select(AiAssistantConversation).where(
            AiAssistantConversation.is_archived == True,
            AiAssistantConversation.archived_at < cutoff,
        ))
        items = list(result.scalars().all())
        for item in items:
            await self.db.delete(item)
        await self.db.commit()
        return len(items)

    async def search_external_experience(self, question: str) -> list[dict[str, str]]:
        if not settings.AI_ASSISTANT_WEB_SEARCH_ENABLED or not settings.TAVILY_API_KEY:
            return []
        query = sanitize_tavily_query(question)
        cache_key = f"ai-assistant:tavily:{hashlib.sha256(query.encode('utf-8')).hexdigest()}"
        try:
            r = await _get_redis_client()
            cached_json = await r.get(cache_key)
            if cached_json:
                return json.loads(cached_json)
        except Exception:
            cached_json = None
        cached = _TAVILY_CACHE.get(query)
        now = time.time()
        if cached and now - cached[0] < settings.AI_ASSISTANT_TAVILY_CACHE_SECONDS:
            return cached[1]
        try:
            async with httpx.AsyncClient(timeout=settings.AI_ASSISTANT_TAVILY_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": settings.TAVILY_API_KEY,
                        "query": query,
                        "search_depth": "basic",
                        "max_results": min(5, settings.AI_ASSISTANT_TAVILY_MAX_RESULTS),
                    },
                )
                response.raise_for_status()
                data = response.json()
        except Exception:
            return []
        results = []
        for item in (data.get("results") or [])[:5]:
            if not isinstance(item, dict):
                continue
            results.append({
                "title": str(item.get("title") or "")[:120],
                "url": str(item.get("url") or ""),
                "summary": str(item.get("content") or item.get("snippet") or "")[:300],
            })
        try:
            r = await _get_redis_client()
            await r.setex(
                cache_key,
                settings.AI_ASSISTANT_TAVILY_CACHE_SECONDS,
                json.dumps(results, ensure_ascii=False),
            )
        except Exception:
            pass
        _TAVILY_CACHE[query] = (now, results)
        return results

    def _should_search(self, question: str) -> bool:
        if not settings.AI_ASSISTANT_WEB_SEARCH_ENABLED:
            return False
        return wants_external_experience(question)

    def _conversation_payload(self, item: AiAssistantConversation) -> dict[str, Any]:
        return {
            "id": item.id,
            "title": item.title,
            "route": item.route,
            "stat_date": item.stat_date.isoformat() if item.stat_date else None,
            "store_code": item.store_code,
            "last_message_at": item.last_message_at.isoformat() if item.last_message_at else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    def _message_payload(self, item: AiAssistantMessage) -> dict[str, Any]:
        return {
            "id": item.id,
            "conversation_id": item.conversation_id,
            "role": item.role,
            "content": item.content,
            "answer": item.answer_payload or None,
            "sources": item.sources or [],
            "context": item.context or {},
            "used_web": item.used_web,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
