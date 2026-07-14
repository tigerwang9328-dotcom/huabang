from datetime import date

from app.integrations.baison.services.product_transfer_inbound_service import (
    BaisonProductTransferInboundService,
    normalize_transfer_inbound_line,
)


class FakeResponse:
    def __init__(self, data):
        self.status_code = 200
        self.data = data


class FakeClient:
    def __init__(self):
        self.calls = []

    def request(self, method, params):
        self.calls.append((method, params.copy()))
        if method == "drp.dbd.get_list":
            if params["ywlx"] != 3:
                return FakeResponse({
                    "code": "1", "flag": "success",
                    "data": {"filter": {"record_count": 0}, "data": []},
                })
            return FakeResponse({
                "code": "1", "flag": "success",
                "data": {
                    "filter": {"record_count": 2},
                    "data": [
                        {"djbh": "PA1", "rq": "2026-07-10", "in_ckdm": "285204", "in_ckmc": "测试门店"},
                        {"djbh": "PA2", "rq": "2026-07-10", "in_ckdm": "IGNORED"},
                    ],
                },
            })
        return FakeResponse({
            "code": "1", "flag": "success",
            "data": {
                "out": [{"goods_sn": "STYLE001", "goods_name": "休闲裤", "sl2": "3", "bzj": "80"}],
                "out_filter": {"record_count": 1},
            },
        })


def test_normalize_transfer_line_uses_destination_and_received_quantity():
    line = normalize_transfer_inbound_line(
        {"djbh": "PA1", "rq": "2026-07-10", "in_ckdm": "gz002", "in_ckmc": "中转仓"},
        {"goods_sn": "STYLE001", "goods_name": "休闲裤", "sl": "4", "sl2": "3", "bzj": "80"},
    )

    assert line["record_date"] == date(2026, 7, 10)
    assert line["warehouse_code"] == "GZ002"
    assert line["product_code"] == "STYLE001"
    assert line["quantity"] == 3
    assert line["cost_amount"] == 240


def test_fetch_transfer_lines_filters_destination_and_uses_business_dates():
    client = FakeClient()
    service = BaisonProductTransferInboundService(client=client, page_size=100)

    lines = service.fetch_inbound_lines(date(2026, 7, 1), date(2026, 7, 12))

    assert len(lines) == 1
    assert lines[0]["warehouse_code"] == "285204"
    header_call = client.calls[0]
    assert header_call[1]["rq_start"] == "2026-07-01 00:00:00"
    assert header_call[1]["rq_end"] == "2026-07-12 23:59:59"
    detail_calls = [call for call in client.calls if call[0] == "drp.dbd.get_detail"]
    assert len(detail_calls) == 1
