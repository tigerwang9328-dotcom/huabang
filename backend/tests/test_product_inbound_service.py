from datetime import date

import pytest

from app.integrations.baison.services.product_inbound_service import (
    BaisonProductInboundService,
    merge_inbound_lines,
    normalize_inbound_line,
    sync_product_inbound,
)


def test_normalize_inbound_line_maps_purchase_fields():
    header = {
        "record_code": "JH20260712001",
        "record_time": "07/12/2026 09:10:11",
        "store_code": "gz002",
        "store_name": "贵阳中转仓",
        "supplier_code": "SUP001",
        "supplier_name": "测试供应商",
    }
    detail = {
        "goods_code": "STYLE001",
        "goods_name": "测试商品",
        "spec1_code": "RED",
        "spec1_name": "红色",
        "spec2_code": "M",
        "spec2_name": "M码",
        "barcode": "690000000001",
        "sku": "STYLE001-RED-M",
        "num": "12",
        "price": "88.50",
        "money": "1062.00",
        "finish_num": "12",
    }

    line = normalize_inbound_line(header, detail)

    assert line["record_code"] == "JH20260712001"
    assert line["record_date"] == date(2026, 7, 12)
    assert line["warehouse_code"] == "GZ002"
    assert line["product_code"] == "STYLE001"
    assert line["sku_code"] == "STYLE001-RED-M"
    assert line["quantity"] == 12
    assert line["purchase_price"] == 88.5
    assert line["purchase_amount"] == 1062
    assert len(line["line_key"]) == 64


class FakeResponse:
    def __init__(self, data):
        self.status_code = 200
        self.data = data


class FakeClient:
    def __init__(self):
        self.calls = []

    def request(self, method, params):
        self.calls.append((method, params.copy()))
        if method == "pms.spjhd.get_list":
            return FakeResponse({
                "code": "1",
                "flag": "SUCCESS",
                "data": {"data": [
                    {"record_code": "A", "record_time": "2026-07-10", "store_code": "285204"},
                    {"record_code": "B", "record_time": "2026-07-10", "store_code": "IGNORED"},
                ], "total": 2},
            })
        record_code = params["record_code"]
        return FakeResponse({
            "code": "1",
            "flag": "SUCCESS",
            "data": {"data": [{"goods_code": f"P-{record_code}", "num": 2, "price": 10, "money": 20}]},
        })


def test_fetch_inbound_lines_filters_non_whitelist_warehouse():
    client = FakeClient()
    service = BaisonProductInboundService(client=client, page_size=100)

    lines = service.fetch_inbound_lines(date(2026, 7, 1), date(2026, 7, 12))

    assert [line["product_code"] for line in lines] == ["P-A"]
    detail_calls = [call for call in client.calls if call[0] == "pms.spjhd.mx_get_list"]
    assert len(detail_calls) == 1


def test_merge_inbound_lines_sums_repeated_receipt_sku_rows():
    first = normalize_inbound_line(
        {"record_code": "A", "record_time": "2026-07-10", "store_code": "GZ001"},
        {"goods_code": "P", "sku": "P-RED-M", "finish_num": 2, "price": 10, "money": 20},
    )
    second = {**first, "quantity": 3, "purchase_amount": 30}

    merged = merge_inbound_lines([first, second])

    assert len(merged) == 1
    assert merged[0]["quantity"] == 5
    assert merged[0]["purchase_amount"] == 50
    assert merged[0]["purchase_price"] == 10


class FakeDb:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params))

    async def flush(self):
        pass


@pytest.mark.asyncio
async def test_sync_writes_detail_then_rebuilds_product_summary():
    db = FakeDb()
    lines = [normalize_inbound_line(
        {"record_code": "A", "record_time": "2026-07-10", "store_code": "285204"},
        {"goods_code": "P-A", "num": 2, "price": 10, "money": 20},
    )]

    result = await sync_product_inbound(db, lines=lines, history_start_date=date(2024, 7, 12))

    assert result["ok"] is True
    assert result["line_count"] == 1
    sql = "\n".join(statement for statement, _ in db.calls)
    assert "INSERT INTO dwd.dwd_baison_purchase_inbound" in sql
    assert "INSERT INTO dws.dws_product_inbound_summary" in sql


@pytest.mark.asyncio
async def test_sync_does_not_touch_database_when_api_fetch_fails(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(
        BaisonProductInboundService,
        "fetch_inbound_lines",
        lambda self, start_date, end_date: (_ for _ in ()).throw(RuntimeError("Baison unavailable")),
    )

    with pytest.raises(RuntimeError, match="unavailable"):
        await sync_product_inbound(db, start_date=date(2026, 7, 1), end_date=date(2026, 7, 12))

    assert db.calls == []
