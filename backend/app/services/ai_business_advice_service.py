"""AI 经营建议批处理、缓存与状态查询。"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.store_whitelist import ALLOWED_STORE_CODES
from app.models.ai import AiBusinessAdviceSnapshot
from app.models.log import LogAiCall
from app.services.ai_diagnosis_service import AIDiagnosisService
from app.services.ai_engine import AIEngine, build_template_command_conclusion, sanitize_command_context


BUSINESS_ADVICE_MODULES = (
    "overview", "sales", "products", "inventory", "finance",
    "hr", "members", "audit", "action-tasks",
)
BUSINESS_ADVICE_SCOPES = (
    ("company", "company"),
    *(("store", code) for code in sorted(ALLOWED_STORE_CODES)),
)
PROMPT_VERSION = "business-advice-v2"
SCHEMA_VERSION = "business-advice-json-v1"


def business_advice_input_hash(context: dict[str, Any]) -> str:
    contract = {
        "context": context,
        "provider": "deepseek",
        "model": settings.AI_BUSINESS_ADVICE_MODEL,
        "enabled": settings.AI_BUSINESS_ADVICE_ENABLED,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
    }
    encoded = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def business_advice_data_status(context: dict[str, Any]) -> str:
    statuses = [metric.get("status") for metric in (context.get("metrics") or {}).values()]
    if "ready" in statuses:
        return "ready"
    if "estimated" in statuses:
        return "estimated"
    if "stale" in statuses:
        return "stale"
    return "pending_data"


class BusinessAdviceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def latest_snapshot(
        self, module: str, stat_date: date, scope_type: str, target_code: str
    ) -> AiBusinessAdviceSnapshot | None:
        result = await self.db.execute(select(AiBusinessAdviceSnapshot).where(
            AiBusinessAdviceSnapshot.stat_date == stat_date,
            AiBusinessAdviceSnapshot.module == module,
            AiBusinessAdviceSnapshot.scope_type == scope_type,
            AiBusinessAdviceSnapshot.target_code == target_code,
        ))
        return result.scalar_one_or_none()

    async def latest_stat_date(self) -> date:
        value = (await self.db.execute(select(func.max(AiBusinessAdviceSnapshot.stat_date)))).scalar_one_or_none()
        if value:
            return value
        latest = await AIDiagnosisService(self.db)._latest_date()
        return latest if isinstance(latest, date) else date.fromisoformat(str(latest))

    async def attach_cached(
        self,
        payload: dict[str, Any],
        module: str,
        stat_date: str | None,
        store_code: str | None,
    ) -> dict[str, Any]:
        raw_date = stat_date or (payload.get("summary") or {}).get("stat_date")
        if not raw_date:
            return payload
        dt = raw_date if isinstance(raw_date, date) else date.fromisoformat(str(raw_date))
        scope_type = "store" if store_code else "company"
        target_code = store_code or "company"
        snapshot = await self.latest_snapshot(module, dt, scope_type, target_code)
        if not snapshot:
            return payload
        payload["command_conclusion"] = {
            **(snapshot.conclusion or {}),
            "generated_at": snapshot.generated_at.isoformat() if snapshot.generated_at else None,
            "data_status": snapshot.data_status,
            "snapshot_status": snapshot.status,
        }
        return payload

    async def generate_unit(
        self,
        module: str,
        stat_date: date,
        scope_type: str,
        target_code: str,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        request_started = datetime.now(timezone.utc)
        store_code = None if scope_type == "company" else target_code
        diagnosis = AIDiagnosisService(self.db)
        payload = await diagnosis.module(module, stat_date.isoformat(), store_code)
        safe_context = diagnosis.command_context(payload)
        input_hash = business_advice_input_hash(safe_context)
        lock_source = f"{stat_date}|{module}|{scope_type}|{target_code}"
        lock_key = int(hashlib.sha256(lock_source.encode("utf-8")).hexdigest()[:15], 16)
        lock_acquired = (await self.db.execute(
            select(func.pg_try_advisory_xact_lock(lock_key))
        )).scalar_one()
        waited_for_lock = not bool(lock_acquired)
        if waited_for_lock:
            await self.db.execute(select(func.pg_advisory_xact_lock(lock_key)))
        existing = await self.latest_snapshot(module, stat_date, scope_type, target_code)
        if (
            existing
            and existing.input_hash == input_hash
            and not force
        ):
            await self.db.commit()
            return {"cached": True, "snapshot": existing}
        if existing and force and existing.generated_at:
            generated_at = existing.generated_at
            if generated_at.tzinfo is None:
                generated_at = generated_at.replace(tzinfo=timezone.utc)
            if generated_at.astimezone(timezone.utc) >= request_started:
                await self.db.commit()
                return {"cached": True, "snapshot": existing}

        conclusion = await AIEngine(self.db).generate_command_conclusion(safe_context)
        self.db.add(LogAiCall(
            user_id=1,
            user_role="system_batch",
            call_type="business_advice",
            data_scope=f"{scope_type}:{target_code}:{module}",
            prompt_version=PROMPT_VERSION,
            model_name=conclusion.get("model_used"),
            ai_provider="deepseek",
            prompt_tokens=conclusion.get("prompt_tokens"),
            completion_tokens=conclusion.get("completion_tokens"),
            total_tokens=conclusion.get("total_tokens"),
            response_summary=(conclusion.get("executive_summary") or "")[:500],
            data_quality_blocked=conclusion.get("fallback_reason") == "没有可供模型解释的就绪事实",
            latency_ms=conclusion.get("latency_ms"),
            status="success" if conclusion.get("mode") == "model" else "blocked",
            error_message=conclusion.get("fallback_reason"),
        ))
        values = {
            "stat_date": stat_date,
            "module": module,
            "scope_type": scope_type,
            "target_code": target_code,
            "safe_context": safe_context,
            "input_hash": input_hash,
            "conclusion": conclusion,
            "mode": conclusion.get("mode", "template"),
            "status": "success" if conclusion.get("mode") == "model" else "fallback",
            "data_status": business_advice_data_status(safe_context),
            "provider": "deepseek",
            "model_name": conclusion.get("model_used"),
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "prompt_tokens": conclusion.get("prompt_tokens"),
            "completion_tokens": conclusion.get("completion_tokens"),
            "total_tokens": conclusion.get("total_tokens"),
            "latency_ms": conclusion.get("latency_ms"),
            "error_code": conclusion.get("error_code"),
            "fallback_reason": conclusion.get("fallback_reason"),
            "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")),
            "updated_at": datetime.now(ZoneInfo("Asia/Shanghai")),
            "last_attempt_status": "success" if conclusion.get("mode") == "model" else "fallback",
            "last_attempt_error_code": conclusion.get("error_code"),
            "last_attempt_at": datetime.now(ZoneInfo("Asia/Shanghai")),
        }
        statement = insert(AiBusinessAdviceSnapshot).values(**values)
        statement = statement.on_conflict_do_update(
            constraint="uq_ai_business_advice_snapshot_unit",
            set_={key: value for key, value in values.items() if key not in {
                "stat_date", "module", "scope_type", "target_code",
            }},
        ).returning(AiBusinessAdviceSnapshot)
        result = await self.db.execute(statement)
        await self.db.commit()
        return {"cached": False, "snapshot": result.scalar_one()}

    async def record_attempt_failure(
        self, module: str, stat_date: date, scope_type: str, target_code: str, exc: Exception
    ) -> None:
        safe_context = {"metrics": {}, "rules": [], "tasks": [], "finance_complete": False}
        conclusion = build_template_command_conclusion(safe_context)
        error_code = type(exc).__name__
        conclusion.update({
            "mode": "template",
            "model_used": "deterministic_rules",
            "fallback_reason": f"分析单元生成失败：{error_code}",
            "error_code": error_code,
        })
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        values = {
            "stat_date": stat_date,
            "module": module,
            "scope_type": scope_type,
            "target_code": target_code,
            "safe_context": safe_context,
            "input_hash": business_advice_input_hash(safe_context),
            "conclusion": conclusion,
            "mode": "template",
            "status": "failed",
            "data_status": "pending_data",
            "provider": "deepseek",
            "model_name": "deterministic_rules",
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "error_code": error_code,
            "fallback_reason": conclusion["fallback_reason"],
            "generated_at": now,
            "updated_at": now,
            "last_attempt_status": "failed",
            "last_attempt_error_code": error_code,
            "last_attempt_at": now,
        }
        statement = insert(AiBusinessAdviceSnapshot).values(**values)
        statement = statement.on_conflict_do_update(
            constraint="uq_ai_business_advice_snapshot_unit",
            set_={
                "last_attempt_status": "failed",
                "last_attempt_error_code": error_code,
                "last_attempt_at": now,
            },
        )
        await self.db.execute(statement)
        await self.db.commit()

    async def status(
        self,
        stat_date: date,
        *,
        allowed_scopes: tuple[tuple[str, str], ...] | None = None,
    ) -> dict[str, Any]:
        result = await self.db.execute(select(AiBusinessAdviceSnapshot).where(
            AiBusinessAdviceSnapshot.stat_date == stat_date
        ))
        snapshots = list(result.scalars().all())
        by_key = {
            f"{item.scope_type}:{item.target_code}:{item.module}": item for item in snapshots
        }
        units = []
        scopes = BUSINESS_ADVICE_SCOPES if allowed_scopes is None else allowed_scopes
        for scope_type, target_code in scopes:
            for module in BUSINESS_ADVICE_MODULES:
                key = f"{scope_type}:{target_code}:{module}"
                item = by_key.get(key)
                units.append({
                    "key": key,
                    "module": module,
                    "scope_type": scope_type,
                    "target_code": target_code,
                    "status": item.status if item else "missing",
                    "mode": item.mode if item else None,
                    "model_name": item.model_name if item else None,
                    "data_status": item.data_status if item else "pending_data",
                    "latency_ms": item.latency_ms if item else None,
                    "generated_at": item.generated_at.isoformat() if item and item.generated_at else None,
                    "fallback_reason": item.fallback_reason if item else "尚未生成",
                    "last_attempt_status": item.last_attempt_status if item else "missing",
                    "last_attempt_error_code": item.last_attempt_error_code if item else None,
                    "last_attempt_at": item.last_attempt_at.isoformat() if item and item.last_attempt_at else None,
                })
        visible_items = [by_key.get(unit["key"]) for unit in units]
        visible_items = [item for item in visible_items if item is not None]
        return {
            "stat_date": stat_date.isoformat(),
            "expected_count": len(scopes) * len(BUSINESS_ADVICE_MODULES),
            "generated_count": len(visible_items),
            "model_count": sum(1 for item in visible_items if item.mode == "model"),
            "fallback_count": sum(1 for item in visible_items if item.mode == "template"),
            "units": units,
        }


async def run_business_advice_batch(db: AsyncSession, stat_date: date) -> dict[str, Any]:
    """公司总览先生成，其余单元限并发；一个失败不阻断其他单元。"""
    from app.core.database import AsyncSessionLocal

    results: list[dict[str, Any]] = []

    async def run_one(scope_type: str, target_code: str, module: str) -> None:
        try:
            async with AsyncSessionLocal() as unit_db:
                item = await BusinessAdviceService(unit_db).generate_unit(
                    module, stat_date, scope_type, target_code
                )
            results.append({"key": f"{scope_type}:{target_code}:{module}", "ok": True, "cached": item["cached"]})
        except Exception as exc:  # 单元隔离，错误由批处理状态展示
            try:
                async with AsyncSessionLocal() as failure_db:
                    await BusinessAdviceService(failure_db).record_attempt_failure(
                        module, stat_date, scope_type, target_code, exc,
                    )
            except Exception:
                pass
            results.append({"key": f"{scope_type}:{target_code}:{module}", "ok": False, "error": type(exc).__name__})

    await run_one("company", "company", "overview")
    semaphore = asyncio.Semaphore(min(3, max(1, settings.AI_BUSINESS_ADVICE_CONCURRENCY)))

    async def limited(scope_type: str, target_code: str, module: str) -> None:
        if (scope_type, target_code, module) == ("company", "company", "overview"):
            return
        async with semaphore:
            await run_one(scope_type, target_code, module)

    await asyncio.gather(*(
        limited(scope_type, target_code, module)
        for scope_type, target_code in BUSINESS_ADVICE_SCOPES
        for module in BUSINESS_ADVICE_MODULES
    ))
    return {
        "stat_date": stat_date.isoformat(),
        "total": len(results),
        "success": sum(1 for item in results if item["ok"]),
        "failed": sum(1 for item in results if not item["ok"]),
        "units": results,
    }
