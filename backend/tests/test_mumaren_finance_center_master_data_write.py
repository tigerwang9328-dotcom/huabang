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
