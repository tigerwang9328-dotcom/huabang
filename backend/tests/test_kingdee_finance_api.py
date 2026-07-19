from types import SimpleNamespace

import pytest

from app.api.v1 import kingdee_finance


class FakeService:
    def __init__(self, db):
        self.db = db

    async def account_sets(self):
        return [{"account_set_code": "AIS1", "company_name": "测试公司"}]

    async def periods(self, account_set_code):
        return [{"period": "2026-01", "status": "source_closed", "account_set_code": account_set_code}]

    async def statements(self, **filters):
        return {"status": "pending_mapping", "items": [], "filters": filters}

    async def account_balances(self, **filters):
        return {"items": [], "total": 0, "filters": filters}

    async def vouchers(self, **filters):
        return {"items": [], "total": 0, "filters": filters}

    async def voucher_detail(self, voucher_id):
        return {"id": voucher_id, "read_only": True, "entries": []}

    async def import_batches(self):
        return []

    async def data_quality(self, account_set_code=None):
        return {"status": "pending_mapping", "account_set_code": account_set_code, "issues": []}


@pytest.fixture(autouse=True)
def fake_service(monkeypatch):
    monkeypatch.setattr(kingdee_finance, "KingdeeFinanceQueryService", FakeService)


@pytest.mark.asyncio
async def test_account_sets_endpoint_is_read_only_and_returns_source_identity():
    response = await kingdee_finance.list_account_sets(
        _current_user=SimpleNamespace(id=1), db=object()
    )

    assert response.data[0]["account_set_code"] == "AIS1"


@pytest.mark.asyncio
async def test_statement_endpoint_preserves_pending_mapping_status():
    response = await kingdee_finance.get_statements(
        account_set_code="AIS1",
        period="2026-01",
        statement_type="profit",
        _current_user=SimpleNamespace(id=1),
        db=object(),
    )

    assert response.data["status"] == "pending_mapping"


@pytest.mark.asyncio
async def test_voucher_detail_is_explicitly_read_only():
    response = await kingdee_finance.get_voucher(
        voucher_id=7, _current_user=SimpleNamespace(id=1), db=object()
    )

    assert response.data["read_only"] is True


@pytest.mark.asyncio
async def test_balance_endpoint_passes_statement_drilldown_filters():
    response = await kingdee_finance.get_account_balances(
        account_set_code="AIS1",
        period="2026-01",
        keyword=None,
        statement_type="profit",
        statement_line_code="P10",
        page=1,
        page_size=50,
        _current_user=SimpleNamespace(id=1),
        db=object(),
    )

    assert response.data["filters"]["statement_line_code"] == "P10"


@pytest.mark.asyncio
async def test_voucher_endpoint_passes_account_drilldown_filter():
    response = await kingdee_finance.list_vouchers(
        account_set_code="AIS1",
        period="2026-01",
        keyword=None,
        account_code="6601",
        page=1,
        page_size=50,
        _current_user=SimpleNamespace(id=1),
        db=object(),
    )

    assert response.data["filters"]["account_code"] == "6601"
