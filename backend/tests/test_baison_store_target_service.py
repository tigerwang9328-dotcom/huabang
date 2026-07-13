from datetime import date
from decimal import Decimal

import pytest

from app.integrations.baison.services.store_target_service import (
    BaisonStoreTargetService,
    normalize_store_target,
    sync_store_targets,
)


def test_normalize_store_target_maps_amounts_and_rate():
    row = normalize_store_target({"zddm": "285204", "zdmc": "遵义店", "ydzb": 160000, "ydxs": 34855, "dbl": "21.78%"}, date(2026, 7, 1))
    assert row["store_code"] == "285204"
    assert row["target_amount"] == 160000
    assert row["actual_amount"] == 34855
    assert row["achievement_rate"] == Decimal("0.2178")


class FakeResponse:
    def __init__(self, data): self.data = data


class FakeClient:
    def request(self, method, params):
        code = params["zddm"]
        return FakeResponse({"code": "1", "flag": "success", "data": [{"zddm": code, "ydzb": 100, "ydxs": 50, "dbl": "50%"}]})


def test_fetch_targets_requests_each_whitelisted_store():
    rows = BaisonStoreTargetService(client=FakeClient()).fetch_targets(2026, 7)
    assert len(rows) == 7
    assert {row["store_code"] for row in rows} == {"134681", "185805", "185808", "285101", "285102", "285204", "285702"}


class FakeDb:
    def __init__(self): self.calls = []
    async def execute(self, statement, params=None): self.calls.append((str(statement), params))
    async def flush(self): pass


@pytest.mark.asyncio
async def test_sync_upserts_monthly_targets():
    db = FakeDb()
    rows = [normalize_store_target({"zddm": "285204", "ydzb": 100, "ydxs": 50, "dbl": "50%"}, date(2026, 7, 1))]
    result = await sync_store_targets(db, 2026, 7, rows=rows)
    assert result["store_count"] == 1
    assert "INSERT INTO dws.dws_store_target_monthly" in db.calls[0][0]


@pytest.mark.asyncio
async def test_sync_does_not_write_when_api_fails(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(BaisonStoreTargetService, "fetch_targets", lambda self, year, month: (_ for _ in ()).throw(RuntimeError("down")))
    with pytest.raises(RuntimeError): await sync_store_targets(db, 2026, 7)
    assert db.calls == []
