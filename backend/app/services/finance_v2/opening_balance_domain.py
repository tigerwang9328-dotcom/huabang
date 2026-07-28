"""Opening-balance invariants separating read-only rehearsal from cutover."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal


class OpeningBalanceError(ValueError):
    pass


@dataclass(frozen=True)
class OpeningBalanceLine:
    account_version_code: str
    dimension_hash: str
    currency_code: str
    debit: Decimal
    credit: Decimal
    source_system: str


@dataclass(frozen=True)
class OpeningBalanceState:
    batch_kind: str
    status: str
    coverage_continuous: bool
    approved_by: str | None = None


def validate_opening_balance(lines: list[OpeningBalanceLine]) -> tuple[Decimal, Decimal]:
    if not lines:
        raise OpeningBalanceError("opening balance has no lines")
    debit = sum((Decimal(line.debit) for line in lines), Decimal("0"))
    credit = sum((Decimal(line.credit) for line in lines), Decimal("0"))
    if debit != credit or debit <= 0:
        raise OpeningBalanceError("opening balance is not balanced")
    if any(not line.source_system for line in lines):
        raise OpeningBalanceError("opening balance source is required")
    return debit, credit


def approve_opening_balance(
    state: OpeningBalanceState,
    lines: list[OpeningBalanceLine],
    *,
    approver: str,
) -> OpeningBalanceState:
    if state.status != "validated":
        raise OpeningBalanceError("opening balance must be validated before approval")
    if not state.coverage_continuous:
        raise OpeningBalanceError("coverage gap blocks opening-balance approval")
    if not approver.strip():
        raise OpeningBalanceError("opening balance approver is required")
    validate_opening_balance(lines)
    return replace(state, status="locked", approved_by=approver)


def assert_current_writes_allowed(state: OpeningBalanceState) -> None:
    if state.batch_kind != "final" or state.status != "locked" or not state.approved_by:
        raise OpeningBalanceError("final locked opening balance is required before current writes")
    if not state.coverage_continuous:
        raise OpeningBalanceError("coverage gap blocks current writes")
