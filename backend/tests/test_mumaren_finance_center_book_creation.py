import os

import pytest


os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("DB_PASSWORD", "test-only-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")

from app.models.mumaren_finance_center import (
    FinanceCenterMumarenAccount,
    FinanceCenterMumarenAuditLog,
    FinanceCenterMumarenBook,
    FinanceCenterMumarenFiscalPeriod,
)
from app.services.mumaren_finance_center.workflow import create_book


class _Result:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _Db:
    def __init__(self, existing_book=None):
        self.added = []
        self.existing_book = existing_book

    async def execute(self, _statement):
        return _Result(self.existing_book)

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        for item in self.added:
            if isinstance(item, FinanceCenterMumarenBook) and item.id is None:
                item.id = 88


@pytest.mark.asyncio
async def test_create_book_seeds_independent_accounts_periods_and_audit_log():
    db = _Db()

    book = await create_book(
        db,
        book_code="NEW2026",
        book_name="新建账簿",
        company_name="华邦新公司",
        status="active",
        operator_id=7,
    )

    assert book.id == 88
    assert book.book_code == "NEW2026"
    assert book.status == "active"
    accounts = [item for item in db.added if isinstance(item, FinanceCenterMumarenAccount)]
    periods = [item for item in db.added if isinstance(item, FinanceCenterMumarenFiscalPeriod)]
    audits = [item for item in db.added if isinstance(item, FinanceCenterMumarenAuditLog)]
    assert {account.book_id for account in accounts} == {88}
    assert {account.account_code for account in accounts} >= {"1001", "1122", "2202", "6001"}
    assert [period.period_code for period in periods] == [f"2026-{month:02d}" for month in range(1, 13)]
    assert all(period.status == "open" and period.book_id == 88 for period in periods)
    assert [(audit.action, audit.book_id, audit.operator_id) for audit in audits] == [("create_book", 88, 7)]


@pytest.mark.asyncio
async def test_create_book_rejects_duplicate_or_invalid_book_code():
    existing = FinanceCenterMumarenBook(id=1, book_code="EXISTS", book_name="已有账簿", status="active")

    with pytest.raises(ValueError, match="账簿编码已存在"):
        await create_book(
            _Db(existing), book_code="EXISTS", book_name="重复", company_name=None,
            status="active", operator_id=7,
        )

    with pytest.raises(ValueError, match="账簿编码只能"):
        await create_book(
            _Db(), book_code="bad code", book_name="非法", company_name=None,
            status="active", operator_id=7,
        )


@pytest.mark.asyncio
async def test_create_book_endpoint_returns_new_book_data(monkeypatch):
    from app.api.v1 import mumaren_finance_center as api

    created = FinanceCenterMumarenBook(
        id=99, book_code="API2026", book_name="接口账簿",
        company_name="华邦", status="active",
    )

    async def fake_create(_db, **kwargs):
        assert kwargs == {
            "book_code": "API2026", "book_name": "接口账簿", "company_name": "华邦",
            "status": "active", "operator_id": 7,
        }
        return created

    monkeypatch.setattr(api, "create_mumaren_book", fake_create)
    result = await api.create_book_endpoint(
        api.BookCreateInput(book_code="API2026", book_name="接口账簿", company_name="华邦", status="active"),
        current_user=type("User", (), {"id": 7})(), db=object(),
    )

    assert result.data == {
        "id": 99, "book_code": "API2026", "book_name": "接口账簿",
        "company_name": "华邦", "status": "active",
    }
