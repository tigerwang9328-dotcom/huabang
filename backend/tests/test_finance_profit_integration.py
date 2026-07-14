import asyncio
from types import SimpleNamespace

from app.api.v1.finance import ExpenseCreateRequest, create_manual_expense
from app.services.ai_diagnosis_service import _can_assert_operating_profit


class _FakeDb:
    def __init__(self):
        self.added = None

    def add(self, value):
        self.added = value

    async def flush(self):
        self.added.id = 17


def test_manual_expense_accepts_explicit_zero_declaration_and_allocation_period():
    db = _FakeDb()
    body = ExpenseCreateRequest(
        expense_date="2026-07-01",
        allocation_start="2026-07-01",
        allocation_end="2026-07-31",
        expense_type="platform_fee",
        expense_amount=0,
        data_type="actual",
    )

    response = asyncio.run(
        create_manual_expense(body=body, current_user=SimpleNamespace(id=9), db=db)
    )

    assert response.success is True
    assert response.data == {"id": 17}
    assert "财务核准" in response.message
    assert str(db.added.allocation_start) == "2026-07-01"
    assert str(db.added.allocation_end) == "2026-07-31"


def test_ai_only_asserts_operating_profit_when_cost_expense_and_approval_are_complete():
    ready = {
        "operating_profit": -100,
        "is_cost_complete": True,
        "is_expense_complete": True,
        "finance_approved": True,
    }

    assert _can_assert_operating_profit(ready) is True
    for key in ("is_cost_complete", "is_expense_complete", "finance_approved"):
        incomplete = {**ready, key: False}
        assert _can_assert_operating_profit(incomplete) is False
    assert _can_assert_operating_profit({**ready, "operating_profit": None}) is False
