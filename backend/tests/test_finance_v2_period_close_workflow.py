from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.finance_v2.domain import FinanceV2DomainError
from app.services.finance_v2.period_close_workflow import FinanceV2PeriodCloseWorkflow, PeriodCloseMetrics
from app.models.finance_v2 import FinanceV2CommandIdempotency, FinanceV2OperationEvent
from app.models.finance_v2_period_close import FinanceV2PeriodCloseBatch, FinanceV2ProfitClosingEvidence


def test_period_close_metrics_are_ready_only_when_every_required_check_is_zero():
    ready = PeriodCloseMetrics(
        unposted_voucher_count=0,
        unbalanced_voucher_count=0,
        source_exception_count=0,
        ledger_difference_count=0,
        posted_debit=Decimal("120.00"),
        posted_credit=Decimal("120.00"),
        ledger_debit=Decimal("120.00"),
        ledger_credit=Decimal("120.00"),
    )
    assert ready.ready is True
    assert ready.to_report()["posted_debit"] == "120.00"

    blocked = PeriodCloseMetrics(
        unposted_voucher_count=1,
        unbalanced_voucher_count=0,
        source_exception_count=0,
        ledger_difference_count=0,
        posted_debit=Decimal("0"),
        posted_credit=Decimal("0"),
        ledger_debit=Decimal("0"),
        ledger_credit=Decimal("0"),
    )
    assert blocked.ready is False
    assert blocked.to_period_check().unposted_voucher_count == 1


def test_period_close_metrics_require_a_registered_manual_profit_closing_evidence_for_activity():
    missing_evidence = PeriodCloseMetrics(
        unposted_voucher_count=0,
        unbalanced_voucher_count=0,
        source_exception_count=0,
        ledger_difference_count=0,
        posted_debit=Decimal("120.00"),
        posted_credit=Decimal("120.00"),
        ledger_debit=Decimal("120.00"),
        ledger_credit=Decimal("120.00"),
        profit_closing_evidence_required=True,
        profit_closing_evidence_count=0,
    )
    registered_evidence = PeriodCloseMetrics(
        unposted_voucher_count=0,
        unbalanced_voucher_count=0,
        source_exception_count=0,
        ledger_difference_count=0,
        posted_debit=Decimal("120.00"),
        posted_credit=Decimal("120.00"),
        ledger_debit=Decimal("120.00"),
        ledger_credit=Decimal("120.00"),
        profit_closing_evidence_required=True,
        profit_closing_evidence_count=1,
    )

    assert missing_evidence.ready is False
    assert missing_evidence.to_report()["profit_closing_evidence_missing_count"] == 1
    assert registered_evidence.ready is True


@pytest.mark.asyncio
async def test_complete_close_cannot_skip_the_closing_state_even_when_checks_are_clear(monkeypatch):
    period = SimpleNamespace(id=9, book_id=3, period_code="2026-07", status="open", version=1)

    class Result:
        def __init__(self, scalar):
            self.scalar = scalar

        def scalar_one_or_none(self):
            return self.scalar

    class Db:
        def __init__(self):
            self.calls = 0

        async def execute(self, _statement):
            self.calls += 1
            return Result(period if self.calls == 1 else None)

    async def clear_metrics(**_kwargs):
        return PeriodCloseMetrics(0, 0, 0, 0, *(Decimal("0"),) * 4)

    workflow = FinanceV2PeriodCloseWorkflow(Db())
    monkeypatch.setattr(workflow, "_metrics", clear_metrics)

    with pytest.raises(FinanceV2DomainError, match="open -> closed"):
        await workflow.command(
            book_id=3,
            period_id=9,
            action="complete_close",
            actor_id="finance-a",
            expected_version=1,
            command_id="close-202607-001",
            reason=None,
        )


@pytest.mark.asyncio
async def test_start_close_persists_the_clear_check_report_and_append_only_audit_event():
    period = SimpleNamespace(id=9, book_id=3, period_code="2026-07", end_date=SimpleNamespace(month=7), status="open", version=1)

    class Result:
        def __init__(self, *, scalar=None, row=None, rowcount=None):
            self.scalar = scalar
            self.row = row
            self.rowcount = rowcount

        def scalar_one_or_none(self):
            return self.scalar

        def scalar_one(self):
            return self.scalar

        def one(self):
            return self.row

    class Db:
        def __init__(self):
            self.calls = 0
            self.added = []

        async def execute(self, _statement):
            self.calls += 1
            results = [
                Result(scalar=period),
                Result(scalar=None),
                Result(scalar=0),
                Result(scalar=0),
                Result(row=(Decimal("0"), Decimal("0"))),
                Result(row=(Decimal("0"), Decimal("0"))),
                Result(scalar=0),
                Result(scalar=0),
                Result(rowcount=1),
            ]
            return results[self.calls - 1]

        def add(self, item):
            if isinstance(item, FinanceV2PeriodCloseBatch):
                item.id = 44
            self.added.append(item)

        async def flush(self):
            pass

    db = Db()
    result = await FinanceV2PeriodCloseWorkflow(db).command(
        book_id=3,
        period_id=9,
        action="start_close",
        actor_id="finance-a",
        expected_version=1,
        command_id="period-close-202607-001",
        reason=None,
    )

    batch = next(item for item in db.added if isinstance(item, FinanceV2PeriodCloseBatch))
    event = next(item for item in db.added if isinstance(item, FinanceV2OperationEvent))
    idempotency = next(item for item in db.added if isinstance(item, FinanceV2CommandIdempotency))
    assert result["status"] == "closing"
    assert batch.check_report["ledger_difference_count"] == 0
    assert event.before_data == {"period_id": 9, "status": "open", "version": 1}
    assert event.after_data["status"] == "closing"
    assert idempotency.result_payload == result


@pytest.mark.asyncio
async def test_start_close_fails_closed_for_a_period_with_posted_activity_until_manual_profit_closing_evidence_exists(monkeypatch):
    period = SimpleNamespace(id=9, book_id=3, period_code="2026-07", end_date=SimpleNamespace(month=7), status="open", version=1)

    class Result:
        def __init__(self, scalar): self.scalar = scalar
        def scalar_one_or_none(self): return self.scalar

    class Db:
        def __init__(self): self.calls = 0
        async def execute(self, _statement):
            self.calls += 1
            return Result(period if self.calls == 1 else None)

    async def active_metrics(**_kwargs):
        return PeriodCloseMetrics(
            0, 0, 0, 0, Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"),
            profit_closing_evidence_required=True,
            profit_closing_evidence_count=0,
        )

    workflow = FinanceV2PeriodCloseWorkflow(Db())
    monkeypatch.setattr(workflow, "_metrics", active_metrics)

    with pytest.raises(FinanceV2DomainError, match="manual profit-closing evidence"):
        await workflow.command(
            book_id=3, period_id=9, action="start_close", actor_id="finance-a", expected_version=1,
            command_id="period-close-activity-001", reason=None,
        )


@pytest.mark.asyncio
async def test_register_profit_closing_evidence_requires_a_posted_manual_voucher_and_records_an_audit_link():
    period = SimpleNamespace(id=9, book_id=3, period_code="2026-07", status="open", version=1)
    voucher = SimpleNamespace(
        id=88,
        book_id=3,
        period_id=9,
        status="posted",
        source_system="manual",
        total_debit=Decimal("100"),
        total_credit=Decimal("100"),
        voucher_no="记-0001",
    )

    class Result:
        def __init__(self, scalar=None):
            self.scalar = scalar

        def scalar_one_or_none(self):
            return self.scalar

    class Db:
        def __init__(self):
            self.calls = 0
            self.added = []

        async def execute(self, _statement):
            self.calls += 1
            return [Result(period), Result(), Result(voucher), Result()][self.calls - 1]

        def add(self, item):
            if isinstance(item, FinanceV2ProfitClosingEvidence):
                item.id = 72
            self.added.append(item)

        async def flush(self):
            pass

    db = Db()
    result = await FinanceV2PeriodCloseWorkflow(db).command(
        book_id=3,
        period_id=9,
        action="register_profit_closing",
        actor_id="finance-a",
        expected_version=1,
        command_id="profit-close-202607-001",
        reason="已人工核对损益结转凭证",
        voucher_id=88,
    )

    evidence = next(item for item in db.added if isinstance(item, FinanceV2ProfitClosingEvidence))
    event = next(item for item in db.added if isinstance(item, FinanceV2OperationEvent))
    assert result == {"period_id": 9, "book_id": 3, "voucher_id": 88, "evidence_id": 72, "status": "registered"}
    assert evidence.voucher_id == 88
    assert evidence.confirmed_by == "finance-a"
    assert event.action == "period.register_profit_closing"
    assert event.voucher_id == 88


@pytest.mark.asyncio
async def test_period_command_retry_returns_the_original_result_after_the_period_version_advances():
    period = SimpleNamespace(id=9, book_id=3, period_code="2026-07", status="closing", version=2)
    request_hash = FinanceV2PeriodCloseWorkflow.command_payload_hash(
        book_id=3,
        period_id=9,
        action="register_profit_closing",
        actor_id="finance-a",
        expected_version=1,
        reason="已人工核对损益结转凭证",
        voucher_id=88,
    )
    existing = SimpleNamespace(
        request_hash=request_hash,
        result_payload={"period_id": 9, "book_id": 3, "voucher_id": 88, "evidence_id": 72, "status": "registered"},
    )

    class Result:
        def __init__(self, scalar):
            self.scalar = scalar

        def scalar_one_or_none(self):
            return self.scalar

    class Db:
        def __init__(self):
            self.calls = 0

        async def execute(self, _statement):
            self.calls += 1
            return Result(period if self.calls == 1 else existing)

    result = await FinanceV2PeriodCloseWorkflow(Db()).command(
        book_id=3,
        period_id=9,
        action="register_profit_closing",
        actor_id="finance-a",
        expected_version=1,
        command_id="profit-close-202607-001",
        reason="已人工核对损益结转凭证",
        voucher_id=88,
    )

    assert result == {**existing.result_payload, "idempotent": True}
