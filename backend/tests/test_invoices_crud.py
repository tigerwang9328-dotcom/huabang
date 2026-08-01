"""Task 3: 发票 CRUD 路由测试(复用 finance_center_mumaren_invoices)。"""
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from mumaren_crud_helpers import _FakeUser, _MockDb, _MockResult

from app.api.v1.mumaren_finance_center_domains import (
    InvoiceInput,
    InvoiceUpdate,
    create_invoice,
    delete_invoice,
    list_invoices,
    update_invoice,
    verify_invoice,
)
from app.models.mumaren_finance_center_domains import FinanceCenterMumarenInvoice


def _invoice(*, inv_id=1, book_id=1, status="draft"):
    return FinanceCenterMumarenInvoice(
        id=inv_id, book_id=book_id, invoice_no="INV001", invoice_type="增值税专用发票",
        invoice_date=date(2026, 7, 1), counterparty_name="供应商甲",
        amount=Decimal("1000.00"), tax_amount=Decimal("130.00"),
        verification_status=status, workflow_status="draft",
    )


@pytest.mark.asyncio
async def test_create_invoice_persists_draft_and_writes_audit_log():
    db = _MockDb()
    inv = await create_invoice(
        body=InvoiceInput(
            book_id=1, invoice_no="INV001", invoice_type="增值税专用发票",
            invoice_date=date(2026, 7, 1), counterparty_name="供应商甲",
            amount=Decimal("1000"), tax_amount=Decimal("130"),
        ),
        current_user=_FakeUser(user_id=4), db=db,
    )
    assert inv.data["verification_status"] == "draft"
    logs = db.audit_logs("create_invoice")
    assert len(logs) == 1
    assert logs[0].operator_id == 4


@pytest.mark.asyncio
async def test_list_invoices_returns_rows():
    rows = [_invoice(inv_id=1), _invoice(inv_id=2)]
    db = _MockDb(execute_results=[_MockResult(scalars=rows)])
    res = await list_invoices(book_id=1, limit=100, _=_FakeUser(), db=db)
    assert len(res.data) == 2


@pytest.mark.asyncio
async def test_update_invoice_only_allowed_in_draft():
    verified = _invoice(inv_id=1, status="verified")
    db = _MockDb(get_map={FinanceCenterMumarenInvoice: {1: verified}})
    with pytest.raises(HTTPException) as exc:
        await update_invoice(
            invoice_id=1, body=InvoiceUpdate(book_id=1, amount=Decimal("2000")),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 409
    assert db.audit_logs() == []

    draft = _invoice(inv_id=1, status="draft")
    db2 = _MockDb(get_map={FinanceCenterMumarenInvoice: {1: draft}})
    res = await update_invoice(
        invoice_id=1, body=InvoiceUpdate(book_id=1, amount=Decimal("2000")),
        current_user=_FakeUser(), db=db2,
    )
    assert res.data["amount"] == Decimal("2000")
    assert len(db2.audit_logs("update_invoice")) == 1


@pytest.mark.asyncio
async def test_update_invoice_rejects_cross_book():
    inv = _invoice(inv_id=1, book_id=1, status="draft")
    db = _MockDb(get_map={FinanceCenterMumarenInvoice: {1: inv}})
    with pytest.raises(HTTPException) as exc:
        await update_invoice(
            invoice_id=1, body=InvoiceUpdate(book_id=2, amount=Decimal("2000")),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_invoice_only_allowed_in_draft():
    verified = _invoice(inv_id=1, status="verified")
    db = _MockDb(get_map={FinanceCenterMumarenInvoice: {1: verified}})
    with pytest.raises(HTTPException) as exc:
        await delete_invoice(invoice_id=1, book_id=1, current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 409

    draft = _invoice(inv_id=1, status="draft")
    db2 = _MockDb(get_map={FinanceCenterMumarenInvoice: {1: draft}})
    res = await delete_invoice(invoice_id=1, book_id=1, current_user=_FakeUser(), db=db2)
    assert res.success
    assert len(db2.deleted) == 1
    assert len(db2.audit_logs("delete_invoice")) == 1


@pytest.mark.asyncio
async def test_verify_invoice_transitions_draft_to_verified():
    draft = _invoice(inv_id=1, status="draft")
    db = _MockDb(get_map={FinanceCenterMumarenInvoice: {1: draft}})
    res = await verify_invoice(invoice_id=1, book_id=1, current_user=_FakeUser(user_id=6), db=db)
    assert res.data["verification_status"] == "verified"
    assert len(db.audit_logs("verify_invoice")) == 1

    # 已核验再核验应被拒绝
    db2 = _MockDb(get_map={FinanceCenterMumarenInvoice: {1: draft}})
    with pytest.raises(HTTPException) as exc:
        await verify_invoice(invoice_id=1, book_id=1, current_user=_FakeUser(), db=db2)
    assert exc.value.status_code == 409
