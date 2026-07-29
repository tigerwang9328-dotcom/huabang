from types import SimpleNamespace

import pytest

from app.models.finance_v2 import FinanceV2CommandIdempotency, FinanceV2OperationEvent
from app.services.finance_v2.domain import FinanceV2DomainError
from app.services.finance_v2 import voucher_workflow
from app.services.finance_v2.voucher_workflow import FinanceV2VoucherWorkflow


class _Result:
    def __init__(self, *, scalar=None, rows=None, rowcount=None):
        self._scalar = scalar
        self._rows = rows or []
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _WorkflowDb:
    def __init__(self, voucher, *, existing_command=None):
        self.voucher = voucher
        self.existing_command = existing_command
        self.calls = 0
        self.added = []

    async def execute(self, _statement):
        self.calls += 1
        if self.calls == 1:
            return _Result(scalar=self.voucher)
        if self.calls == 2:
            return _Result(scalar=self.existing_command)
        if self.calls == 3:
            return _Result(rows=[
                SimpleNamespace(account_version_id=1001, summary="收款", debit_amount="100", credit_amount="0"),
                SimpleNamespace(account_version_id=6001, summary="收入", debit_amount="0", credit_amount="100"),
            ])
        return _Result(rowcount=1)

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        pass


def _voucher():
    return SimpleNamespace(
        id=7,
        book_id=3,
        period_id=9,
        voucher_group="记",
        voucher_no=None,
        status="draft",
        version=1,
        prepared_by="maker",
        reviewer_id=None,
        approved_by=None,
        posted_by=None,
    )


@pytest.mark.asyncio
async def test_voucher_command_persists_retryable_result_and_uses_client_command_id_for_audit():
    db = _WorkflowDb(_voucher())

    result = await FinanceV2VoucherWorkflow(db).command(
        voucher_id=7,
        action="submit",
        actor_id="maker",
        expected_version=1,
        reason=None,
        command_id="submit-20260729-001",
    )

    idempotency = next(item for item in db.added if isinstance(item, FinanceV2CommandIdempotency))
    event = next(item for item in db.added if isinstance(item, FinanceV2OperationEvent))
    assert result == idempotency.result_payload
    assert idempotency.idempotency_key == "submit-20260729-001"
    assert idempotency.completed_at is not None
    assert event.command_id == "submit-20260729-001"


@pytest.mark.asyncio
async def test_voucher_command_retry_returns_persisted_result_without_reapplying_transition():
    stored = SimpleNamespace(
        request_hash=FinanceV2VoucherWorkflow.command_payload_hash(
            voucher_id=7, action="submit", actor_id="maker", expected_version=1, reason=None
        ),
        result_payload={"voucher_id": 7, "status": "submitted", "version": 2, "idempotent": False},
    )
    db = _WorkflowDb(_voucher(), existing_command=stored)

    result = await FinanceV2VoucherWorkflow(db).command(
        voucher_id=7,
        action="submit",
        actor_id="maker",
        expected_version=1,
        reason=None,
        command_id="submit-20260729-001",
    )

    assert result == {"voucher_id": 7, "status": "submitted", "version": 2, "idempotent": True}
    assert db.calls == 2
    assert db.added == []


def test_voucher_command_payload_hash_binds_the_idempotency_record_to_one_voucher():
    common = {"action": "submit", "actor_id": "maker", "expected_version": 1, "reason": None}

    assert FinanceV2VoucherWorkflow.command_payload_hash(voucher_id=7, **common) != (
        FinanceV2VoucherWorkflow.command_payload_hash(voucher_id=8, **common)
    )


@pytest.mark.asyncio
async def test_voucher_command_rejects_reuse_of_a_command_id_with_different_parameters():
    db = _WorkflowDb(
        _voucher(),
        existing_command=SimpleNamespace(request_hash="different", result_payload={}),
    )

    with pytest.raises(FinanceV2DomainError, match="different parameters"):
        await FinanceV2VoucherWorkflow(db).command(
            voucher_id=7,
            action="submit",
            actor_id="maker",
            expected_version=1,
            reason=None,
            command_id="submit-20260729-001",
        )


@pytest.mark.asyncio
async def test_manual_post_assigns_and_finalizes_a_reserved_voucher_number(monkeypatch):
    voucher = _voucher()
    voucher.status = "approved"
    voucher.version = 4
    db = _WorkflowDb(voucher)
    reservation = SimpleNamespace(voucher_no="0007", status="reserved")

    class FakeNumberService:
        def __init__(self, _db):
            pass

        async def reserve(self, **kwargs):
            assert kwargs == {
                "book_id": 3,
                "period_id": 9,
                "voucher_group": "记",
                "command_id": "post-20260729-001",
                "voucher_id": 7,
            }
            return reservation

        @staticmethod
        def mark_used(item):
            item.status = "used"

    class FakeLedgerService:
        async def rebuild_period(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(voucher_workflow, "FinanceV2VoucherNumberService", FakeNumberService)
    monkeypatch.setattr(voucher_workflow, "FinanceV2LedgerService", FakeLedgerService)

    result = await FinanceV2VoucherWorkflow(db).command(
        voucher_id=7,
        action="post",
        actor_id="poster",
        expected_version=4,
        reason="人工过账",
        command_id="post-20260729-001",
    )

    assert voucher.voucher_no == "0007"
    assert reservation.status == "used"
    assert result["voucher_no"] == "0007"
