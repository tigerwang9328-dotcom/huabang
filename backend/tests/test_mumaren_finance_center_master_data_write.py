"""当前账科目和税种维护的领域回归测试。"""
import os

import pytest

os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("DB_PASSWORD", "test-only-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")

from app.models.mumaren_finance_center import FinanceCenterMumarenBook


class _Result:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Db:
    def __init__(self, book):
        self.book = book
        self.added = []

    async def get(self, model, primary_id):
        return self.book if model is FinanceCenterMumarenBook and primary_id == self.book.id else None

    async def execute(self, statement):
        return _Result()

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        pass


class _AccountsResult:
    def __init__(self, accounts):
        self.accounts = accounts

    def scalars(self):
        return self

    def all(self):
        return self.accounts


class _BookMaintenanceDb(_Db):
    def __init__(self, book, accounts):
        super().__init__(book)
        self.accounts = accounts
        self.inserted = 0

    async def execute(self, statement):
        if statement.is_insert:
            self.inserted += 1
            return _Result(1)
        return _AccountsResult(self.accounts)


@pytest.mark.asyncio
async def test_current_book_can_create_account_but_historical_book_is_rejected():
    from app.services.mumaren_finance_center.workflow import HistoricalRecordReadonlyError, create_account

    writable = FinanceCenterMumarenBook(id=1, book_code="CURRENT", book_name="当前账", status="active", is_readonly=False)
    account = await create_account(
        _Db(writable), book_id=1, account_code="1003", account_name="其他货币资金",
        account_type="asset", direction="debit", level=1, operator_id=7,
    )
    assert account.book_id == 1
    assert account.account_code == "1003"

    historical = FinanceCenterMumarenBook(id=2, book_code="K3", book_name="金蝶账", status="active", is_readonly=True)
    with pytest.raises(HistoricalRecordReadonlyError, match="历史迁移账簿只读"):
        await create_account(
            _Db(historical), book_id=2, account_code="1003", account_name="其他货币资金",
            account_type="asset", direction="debit", level=1, operator_id=7,
        )


@pytest.mark.asyncio
async def test_missing_book_is_distinguished_from_a_readonly_book():
    from app.services.mumaren_finance_center.workflow import assert_book_writable

    with pytest.raises(LookupError, match="账簿不存在"):
        await assert_book_writable(
            _Db(FinanceCenterMumarenBook(id=1, book_code="CURRENT", book_name="当前账", status="active", is_readonly=False)),
            book_id=999,
        )


@pytest.mark.asyncio
async def test_current_book_can_create_tax_type_but_historical_book_is_rejected():
    from app.services.mumaren_finance_center.tax import create_tax_type
    from app.services.mumaren_finance_center.workflow import HistoricalRecordReadonlyError

    writable = FinanceCenterMumarenBook(id=1, book_code="CURRENT", book_name="当前账", status="active", is_readonly=False)
    tax_type = await create_tax_type(
        _Db(writable), book_id=1, tax_code="VAT", tax_name="增值税", default_rate="0.13", operator_id=7,
    )
    assert tax_type.book_id == 1
    assert tax_type.tax_code == "VAT"

    historical = FinanceCenterMumarenBook(id=2, book_code="K3", book_name="金蝶账", status="active", is_readonly=True)
    with pytest.raises(HistoricalRecordReadonlyError, match="历史迁移账簿只读"):
        await create_tax_type(
            _Db(historical), book_id=2, tax_code="VAT", tax_name="增值税", default_rate="0.13", operator_id=7,
        )


@pytest.mark.asyncio
async def test_current_book_metadata_can_change_but_history_book_is_rejected():
    from app.services.mumaren_finance_center.workflow import HistoricalRecordReadonlyError, update_book

    writable = FinanceCenterMumarenBook(id=1, book_code="CURRENT", book_name="旧名称", company_name="旧主体", status="active", is_readonly=False)
    updated = await update_book(
        _Db(writable), book_id=1, book_name="新名称", company_name="新主体", operator_id=7,
    )
    assert updated.book_name == "新名称"
    assert updated.company_name == "新主体"
    assert updated.status == "active"

    historical = FinanceCenterMumarenBook(id=2, book_code="K3", book_name="金蝶账", status="active", is_readonly=True)
    with pytest.raises(HistoricalRecordReadonlyError, match="历史迁移账簿只读"):
        await update_book(
            _Db(historical), book_id=2, book_name="不得修改", company_name=None, operator_id=7,
        )


@pytest.mark.asyncio
async def test_replenish_starter_accounts_adds_only_missing_current_book_accounts():
    from app.models.mumaren_finance_center import FinanceCenterMumarenAccount
    from app.services.mumaren_finance_center.workflow import HistoricalRecordReadonlyError, replenish_starter_accounts

    writable = FinanceCenterMumarenBook(id=1, book_code="CURRENT", book_name="当前账", status="active", is_readonly=False)
    existing = FinanceCenterMumarenAccount(book_id=1, account_code="1001", account_name="库存现金", account_type="asset", direction="debit", level=1)
    db = _BookMaintenanceDb(writable, [existing])
    added = await replenish_starter_accounts(db, book_id=1, operator_id=7)
    assert added == 14
    assert db.inserted == 14

    historical = FinanceCenterMumarenBook(id=2, book_code="K3", book_name="金蝶账", status="active", is_readonly=True)
    with pytest.raises(HistoricalRecordReadonlyError, match="历史迁移账簿只读"):
        await replenish_starter_accounts(_BookMaintenanceDb(historical, []), book_id=2, operator_id=7)


def test_replenish_uses_database_conflict_handling_for_concurrent_requests():
    from app.services.mumaren_finance_center import workflow

    source = open(workflow.__file__, encoding="utf-8").read()
    assert "postgresql import insert as pg_insert" in source
    assert "on_conflict_do_nothing" in source
