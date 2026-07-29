import pytest

from app.services.finance_v2.period_close_domain import (
    PeriodCloseCheck,
    PeriodCloseError,
    PeriodState,
    approve_reopen,
    begin_close,
    complete_close,
    request_reopen,
)


def test_period_can_close_only_after_all_required_finance_checks_pass():
    closing = begin_close(PeriodState("open"), PeriodCloseCheck())
    closed = complete_close(closing)

    assert closing.status == "closing"
    assert closed.status == "closed"


@pytest.mark.parametrize("field", ["unposted_voucher_count", "unbalanced_voucher_count", "source_exception_count", "ledger_difference_count"])
def test_period_close_is_blocked_by_any_unresolved_finance_check(field):
    checks = PeriodCloseCheck(**{field: 1})

    with pytest.raises(PeriodCloseError, match=field):
        begin_close(PeriodState("open"), checks)


def test_reopen_requires_a_reason_and_two_distinct_approvers():
    reopening = request_reopen(PeriodState("closed"), reason="更正已核对差异", requester="finance-a")
    with pytest.raises(PeriodCloseError, match="distinct"):
        approve_reopen(reopening, first_approver="finance-b", second_approver="finance-b")

    reopened = approve_reopen(reopening, first_approver="finance-b", second_approver="finance-c")
    assert reopened.status == "open"
