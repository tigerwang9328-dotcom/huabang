"""One transaction-aware, redacted writer for Huabang operation audits."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sys import SysOperationLog, SysUser


_SENSITIVE_KEY_FRAGMENTS = (
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "signature",
    "token",
)
_REDACTED = "[REDACTED]"
_SENSITIVE_STRING_MARKERS = ("bearer ", "mstoken", "a_bogus", "cookie=", "authorization:")


class RequestLike(Protocol):
    client: Any
    headers: Mapping[str, str]


def redact_audit_payload(value: Any, key: str = "") -> Any:
    """Return JSON-safe audit data without credentials or signed request material."""
    lowered_key = key.lower()
    if any(fragment in lowered_key for fragment in _SENSITIVE_KEY_FRAGMENTS):
        return _REDACTED
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        lowered_value = value.lower()
        if any(marker in lowered_value for marker in _SENSITIVE_STRING_MARKERS):
            return _REDACTED
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"} and (parsed.query or parsed.fragment):
            return _REDACTED
        return value
    if isinstance(value, Mapping):
        return {str(item_key): redact_audit_payload(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_audit_payload(item, key) for item in value]
    return str(value)


async def write_operation_audit(
    db: AsyncSession,
    *,
    actor: SysUser | None,
    actor_username: str | None = None,
    module: str,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    before_data: Any = None,
    after_data: Any = None,
    request: RequestLike | None = None,
) -> SysOperationLog:
    """Append and flush an audit row in the caller's existing transaction.

    This function never commits or rolls back. The owning FastAPI dependency
    retains the single transaction boundary, so a failed business write cannot
    leave a misleading audit event behind.
    """
    log = SysOperationLog(
        user_id=actor.id if actor else None,
        username=actor.username if actor else actor_username,
        module=module,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        before_data=redact_audit_payload(before_data),
        after_data=redact_audit_payload(after_data),
        ip=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(log)
    await db.flush()
    return log
