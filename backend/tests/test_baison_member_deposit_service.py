from datetime import date

import pytest

from app.integrations.baison.services.member_deposit_service import (
    BaisonMemberDepositService,
    normalize_deposit_log,
    sync_member_deposits,
)


def test_normalize_deposit_log_maps_baison_fields_and_business_type():
    raw = {
        "customer_deposit_log_id": 61794,
        "vip_code": "185805_GK00000012",
        "customer_code": "GK185805000012",
        "customer_tel": "13800000000",
        "change_type": "0",
        "shop_code": "185805",
        "shop_name": "六盘水百盛店",
        "money_before": 100,
        "money_change": 5000,
        "money_after": 5100,
        "record_code": "CZ001",
        "init_time": "2026-07-11 20:02:14",
        "remark": "IPOS+充值生成",
    }

    log = normalize_deposit_log(raw)

    assert log["source_log_id"] == "61794"
    assert log["member_no"] == "185805_GK00000012"
    assert log["store_code"] == "185805"
    assert log["change_type"] == "0"
    assert log["business_type"] == "recharge"
    assert log["biz_date"] == date(2026, 7, 11)
    assert log["money_change"] == 5000
    assert len(log["line_key"]) == 64


@pytest.mark.parametrize(("change_type", "expected"), [("0", "recharge"), ("2", "consume"), ("8", "adjustment")])
def test_normalize_deposit_log_classifies_change_types(change_type, expected):
    log = normalize_deposit_log({
        "customer_deposit_log_id": f"ID-{change_type}",
        "vip_code": "VIP1",
        "change_type": change_type,
        "shop_code": "285204",
        "money_change": 100,
        "init_time": "2026-07-01 08:00:00",
    })

    assert log["business_type"] == expected


class FakeResponse:
    def __init__(self, data):
        self.status_code = 200
        self.data = data


class FakeClient:
    def __init__(self):
        self.calls = []

    def request(self, method, params, timeout=30):
        self.calls.append((method, params.copy()))
        page = int(params["pageNum"])
        rows = [
            {"customer_deposit_log_id": "A", "vip_code": "V1", "change_type": "0", "shop_code": "185805", "money_change": 500, "init_time": "2026-07-01 10:00:00", "tCount": 3},
            {"customer_deposit_log_id": "B", "vip_code": "V2", "change_type": "2", "shop_code": "IGNORED", "money_change": -100, "init_time": "2026-07-01 11:00:00", "tCount": 3},
        ] if page == 1 else [
            {"customer_deposit_log_id": "C", "vip_code": "V3", "change_type": "8", "shop_code": "285204", "money_change": 20, "init_time": "2026-07-02 10:00:00", "tCount": 3},
        ]
        return FakeResponse({"code": "1", "flag": "success", "data": {"data": rows}})


def test_fetch_logs_pages_and_filters_to_sales_store_whitelist():
    client = FakeClient()
    service = BaisonMemberDepositService(client=client, page_size=2)

    logs = service.fetch_logs(date(2026, 7, 1), date(2026, 7, 2))

    assert [log["source_log_id"] for log in logs] == ["A", "C"]
    assert [params["pageNum"] for _, params in client.calls] == ["1", "2"]
    assert all(method == "crm.vip.get_deposit_list" for method, _ in client.calls)


class FakeDb:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params))

    async def flush(self):
        pass


@pytest.mark.asyncio
async def test_sync_writes_detail_then_rebuilds_daily_summary():
    db = FakeDb()
    logs = [normalize_deposit_log({
        "customer_deposit_log_id": "A", "vip_code": "V1", "change_type": "0",
        "shop_code": "185805", "money_change": 500, "init_time": "2026-07-01 10:00:00",
    })]

    result = await sync_member_deposits(db, date(2026, 7, 1), date(2026, 7, 2), logs=logs)

    assert result["ok"] is True
    assert result["log_count"] == 1
    sql = "\n".join(statement for statement, _ in db.calls)
    assert "INSERT INTO dwd.dwd_baison_member_deposit_log" in sql
    assert "INSERT INTO dws.dws_member_deposit_daily" in sql


@pytest.mark.asyncio
async def test_sync_does_not_touch_database_when_api_fails(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(
        BaisonMemberDepositService,
        "fetch_logs",
        lambda self, start_date, end_date: (_ for _ in ()).throw(RuntimeError("Baison unavailable")),
    )

    with pytest.raises(RuntimeError, match="unavailable"):
        await sync_member_deposits(db, date(2026, 7, 1), date(2026, 7, 2))

    assert db.calls == []
