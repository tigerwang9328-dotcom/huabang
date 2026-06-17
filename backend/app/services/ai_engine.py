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
    "cost": ["cost_price", "cost_amount"],
    "cash": ["cash_balance", "cash_safety_days", "total_cash"],
    "member_phone": ["phone", "member_phone"],
}


class AIEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

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
            data = resp.json()

        if "error" in data:
            raise ValueError(f"AI API错误: {data[error]}")

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
