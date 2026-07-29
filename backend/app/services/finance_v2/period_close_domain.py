"""Pure V2 period-closing rules, kept independent of database orchestration."""

from __future__ import annotations

from dataclasses import dataclass


class PeriodCloseError(ValueError):
    pass


@dataclass(frozen=True)
class PeriodState:
    status: str


@dataclass(frozen=True)
class PeriodCloseCheck:
    unposted_voucher_count: int = 0
    unbalanced_voucher_count: int = 0
    source_exception_count: int = 0
    ledger_difference_count: int = 0

    def assert_clear(self) -> None:
        for field, value in self.__dict__.items():
            if value:
                raise PeriodCloseError(f"{field} must be zero before period close")


def begin_close(state: PeriodState, checks: PeriodCloseCheck) -> PeriodState:
    if state.status != "open":
        raise PeriodCloseError(f"invalid period close transition: {state.status} -> closing")
    checks.assert_clear()
    return PeriodState("closing")


def complete_close(state: PeriodState) -> PeriodState:
    if state.status != "closing":
        raise PeriodCloseError(f"invalid period close transition: {state.status} -> closed")
    return PeriodState("closed")


def request_reopen(state: PeriodState, *, reason: str, requester: str) -> PeriodState:
    if state.status != "closed":
        raise PeriodCloseError(f"invalid period reopen transition: {state.status} -> reopening")
    if not reason.strip() or not requester.strip():
        raise PeriodCloseError("reopen reason and requester are required")
    return PeriodState("reopening")


def approve_reopen(state: PeriodState, *, first_approver: str, second_approver: str) -> PeriodState:
    if state.status != "reopening":
        raise PeriodCloseError(f"invalid period reopen transition: {state.status} -> open")
    if not first_approver.strip() or not second_approver.strip() or first_approver == second_approver:
        raise PeriodCloseError("reopen requires two distinct approvers")
    return PeriodState("open")


def next_reopen_approval(*, requester: str, existing_approvers: tuple[str, ...], actor: str) -> tuple[int, bool]:
    """Return the next persisted approval step and whether it reopens the period."""

    if not requester.strip() or not actor.strip():
        raise PeriodCloseError("reopen requester and approver are required")
    if len(existing_approvers) >= 2:
        raise PeriodCloseError("reopen already has two approvals")
    if actor == requester:
        raise PeriodCloseError("reopen requester cannot approve the request")
    if actor in existing_approvers:
        raise PeriodCloseError("approver already approved this reopen request")
    return len(existing_approvers) + 1, len(existing_approvers) == 1
