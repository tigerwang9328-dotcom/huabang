from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.api.v1 import finance_center


class FakeFinanceCenterService:
    def __init__(self, db):
        self.db = db

    async def import_kingdee_history_to_formal_ledger(self, account_set_code):
        return {"status": "ready", "account_set_code": account_set_code}

    async def open_period(self, book_id, period):
        return {"period_id": 8, "book_id": book_id, "period": period, "status": "open"}

    async def create_voucher(self, book_id, period, voucher_no, voucher_date, entries, actor_name, reason):
        return {
            "status": "draft",
            "book_id": book_id,
            "period": period,
            "voucher_no": voucher_no,
            "voucher_date": str(voucher_date),
            "entry_count": len(entries),
            "actor_name": actor_name,
            "reason": reason,
        }

    async def post_voucher(self, voucher_id, actor_name, reason):
        return {"status": "posted", "voucher_id": voucher_id, "actor_name": actor_name, "reason": reason}

    async def reverse_voucher(self, voucher_id, voucher_no, actor_name, reason):
        return {"status": "posted", "voucher_id": 99, "reversal_of_id": voucher_id, "voucher_no": voucher_no}

    async def revise_voucher_entries(self, voucher_id, entries, actor_name, reason):
        return {"status": "posted", "voucher_id": voucher_id, "entry_count": len(entries)}

    async def upsert_statement_line(self, **payload):
        return {"statement_line_id": 7, **payload}

    async def map_account_to_statement(self, **payload):
        return {"mapping_id": 9, "status": "confirmed", **payload}

    async def generate_statement_monthly(self, book_id, period, statement_type):
        return {"status": "ready", "book_id": book_id, "period": period, "statement_type": statement_type}


@pytest.fixture(autouse=True)
def fake_service(monkeypatch):
    monkeypatch.setattr(finance_center, "FinanceCenterService", FakeFinanceCenterService)


@pytest.mark.asyncio
async def test_import_kingdee_history_endpoint_writes_to_formal_ledger():
    response = await finance_center.import_kingdee_history(
        finance_center.KingdeeImportRequest(account_set_code="AIS1"),
        current_user=SimpleNamespace(id=3, username="boss"),
        db=object(),
    )

    assert response.data == {"status": "ready", "account_set_code": "AIS1"}


@pytest.mark.asyncio
async def test_voucher_write_endpoints_preserve_actor_and_reason():
    create_response = await finance_center.create_voucher(
        finance_center.VoucherCreateRequest(
            book_id=1,
            period="2026-02",
            voucher_no="V-1",
            voucher_date=date(2026, 2, 3),
            reason="approved manual entry",
            entries=[
                finance_center.VoucherEntryPayload(
                    account_id=11,
                    summary="debit",
                    debit_amount=Decimal("1"),
                    credit_amount=Decimal("0"),
                )
            ],
        ),
        current_user=SimpleNamespace(id=3, username="accountant"),
        db=object(),
    )
    post_response = await finance_center.post_voucher(
        6,
        finance_center.ReasonRequest(reason="reviewed"),
        current_user=SimpleNamespace(id=3, username="accountant"),
        db=object(),
    )

    assert create_response.data["actor_name"] == "accountant"
    assert create_response.data["reason"] == "approved manual entry"
    assert post_response.data["status"] == "posted"


@pytest.mark.asyncio
async def test_statement_generation_endpoint_does_not_hide_pending_status():
    response = await finance_center.generate_statement_monthly(
        finance_center.StatementGenerateRequest(
            book_id=1,
            period="2026-01",
            statement_type="income_statement",
        ),
        current_user=SimpleNamespace(id=3, username="finance"),
        db=object(),
    )

    assert response.data["status"] == "ready"
    assert response.data["statement_type"] == "income_statement"
