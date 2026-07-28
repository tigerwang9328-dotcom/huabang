"""Pure, testable invariants for the V2.0 voucher state machine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from hashlib import sha256
import json


class FinanceV2DomainError(ValueError):
    """A user-correctable accounting command or validation error."""


@dataclass(frozen=True)
class VoucherLineDraft:
    account_version_id: str
    summary: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")


@dataclass(frozen=True)
class VoucherDraft:
    voucher_id: str
    status: str
    version: int
    prepared_by: str
    reviewer_id: str | None
    posted_by: str | None = None


@dataclass(frozen=True)
class VoucherCommand:
    action: str
    actor_id: str
    expected_version: int
    reason: str | None = None


_TRANSITIONS = {
    "draft": {"submit": "submitted", "cancel": "cancelled"},
    "submitted": {"start_review": "reviewing", "cancel": "cancelled"},
    "reviewing": {"approve": "approved", "reject": "rejected", "cancel": "cancelled"},
    "rejected": {"reopen": "draft"},
    "approved": {"withdraw": "draft", "post": "posted", "cancel": "cancelled"},
    "posted": {},
    "cancelled": {},
}

_REASON_REQUIRED = {"reject", "reopen", "withdraw", "cancel", "post"}
_BALANCE_REQUIRED = {"submit", "approve", "post"}


def canonical_dimension_hash(items: dict[str, str | None]) -> str:
    """Return the stable, order-independent identity for a dimension set."""

    normalized = {str(key): "" if value is None else str(value) for key, value in items.items()}
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def validate_voucher_lines(lines: list[VoucherLineDraft]) -> tuple[Decimal, Decimal]:
    """Validate submit/approve/post line invariants and return balanced totals."""

    if not lines:
        raise FinanceV2DomainError("voucher has no lines")
    debit_total = Decimal("0")
    credit_total = Decimal("0")
    for line in lines:
        debit = Decimal(line.debit)
        credit = Decimal(line.credit)
        if debit < 0 or credit < 0:
            raise FinanceV2DomainError("voucher amounts cannot be negative")
        if (debit > 0) == (credit > 0):
            raise FinanceV2DomainError("each voucher line must have exactly one debit or credit amount")
        if not line.account_version_id:
            raise FinanceV2DomainError("voucher line account is required")
        debit_total += debit
        credit_total += credit
    if debit_total <= 0 or debit_total != credit_total:
        raise FinanceV2DomainError("voucher is not balanced")
    return debit_total, credit_total


def apply_voucher_command(
    voucher: VoucherDraft,
    command: VoucherCommand,
    lines: list[VoucherLineDraft],
) -> VoucherDraft:
    """Apply one optimistic-concurrency command without mutating the source draft.

    Persistence layers must use the same expected-version predicate in SQL;
    this function is the source of truth for state transition semantics.
    """

    if command.expected_version != voucher.version:
        raise FinanceV2DomainError(
            f"version conflict: expected {command.expected_version}, current {voucher.version}"
        )
    target = _TRANSITIONS.get(voucher.status, {}).get(command.action)
    if target is None:
        raise FinanceV2DomainError(f"invalid voucher transition: {voucher.status} -> {command.action}")
    if command.action in _REASON_REQUIRED and not (command.reason or "").strip():
        raise FinanceV2DomainError(f"reason is required for {command.action}")
    if command.action in _BALANCE_REQUIRED:
        validate_voucher_lines(lines)

    changes: dict[str, object] = {"status": target, "version": voucher.version + 1}
    if command.action == "start_review":
        changes["reviewer_id"] = command.actor_id
    elif command.action == "post":
        changes["posted_by"] = command.actor_id
    elif command.action in {"reopen", "withdraw"}:
        changes["reviewer_id"] = None

    return replace(voucher, **changes)
