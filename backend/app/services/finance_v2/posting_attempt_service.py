"""Durable, out-of-transaction evidence for a manual posting attempt."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_finance_session_factory
from app.models.finance_v2_operations import FinanceV2PostingAttempt


class FinanceV2PostingAttemptRecorder:
    """Persist posting-attempt transitions in sessions independent of account writes."""

    def __init__(self, session_factory: Callable[[], AsyncSession] | None = None):
        self._session_factory = session_factory

    def _new_session(self) -> AsyncSession:
        factory = self._session_factory or get_finance_session_factory()
        return factory()

    async def start(self, *, voucher_id: int, command_id: str) -> int:
        async with self._new_session() as session:
            existing = (
                await session.execute(
                    select(FinanceV2PostingAttempt).where(FinanceV2PostingAttempt.command_id == command_id)
                )
            ).scalar_one_or_none()
            if existing:
                return existing.id
            attempt = FinanceV2PostingAttempt(voucher_id=voucher_id, command_id=command_id, status="running")
            session.add(attempt)
            await session.flush()
            await session.commit()
            return attempt.id

    async def mark_succeeded(self, attempt_id: int) -> None:
        await self._complete(attempt_id, status="success")

    async def mark_failed(
        self,
        attempt_id: int,
        *,
        error_code: str,
        error_context: dict[str, Any] | None = None,
    ) -> None:
        await self._complete(
            attempt_id,
            status="failed",
            error_code=error_code[:64],
            error_context=self.sanitize_context(error_context or {}),
        )

    async def _complete(
        self,
        attempt_id: int,
        *,
        status: str,
        error_code: str | None = None,
        error_context: dict[str, Any] | None = None,
    ) -> None:
        async with self._new_session() as session:
            attempt = await session.get(FinanceV2PostingAttempt, attempt_id)
            if not attempt:
                raise LookupError(f"posting attempt {attempt_id} not found")
            attempt.status = status
            attempt.error_code = error_code
            attempt.error_context = error_context
            attempt.completed_at = datetime.now(timezone.utc)
            await session.commit()

    @staticmethod
    def sanitize_context(context: dict[str, Any]) -> dict[str, Any]:
        sensitive_fragments = ("password", "secret", "token", "authorization", "database_url", "dsn", "credential")

        def clean(value: Any, key: str = "") -> Any:
            if any(fragment in key.lower() for fragment in sensitive_fragments):
                return "[redacted]"
            if isinstance(value, dict):
                return {str(child_key): clean(child_value, str(child_key)) for child_key, child_value in value.items()}
            if isinstance(value, list):
                return [clean(item) for item in value]
            if isinstance(value, (str, int, float, bool)) or value is None:
                return value
            return str(value)

        return clean(context)
