from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.api.v1.mumaren_finance_center_domains import ArApOrderInput


def _order_payload(**overrides):
    payload = {
        "book_id": 1,
        "order_type": "receivable",
        "order_no": "AR-LINE-001",
        "order_date": date(2026, 8, 1),
        "counterparty_name": "测试客户",
        "total_amount": "150.00",
        "lines": [
            {"item_name": "货品 A", "quantity": "2", "unit_price": "50", "amount": "100.00"},
            {"item_name": "货品 B", "quantity": "1", "unit_price": "50", "amount": "50.00"},
        ],
    }
    payload.update(overrides)
    return payload


def test_ar_ap_create_contract_accepts_numbered_detail_lines():
    body = ArApOrderInput.model_validate(_order_payload())

    assert len(body.lines) == 2
    assert body.lines[0].item_name == "货品 A"
    assert body.lines[1].amount == Decimal("50.00")


def test_ar_ap_create_contract_rejects_total_not_equal_to_detail_lines():
    with pytest.raises(ValidationError, match="明细金额合计"):
        ArApOrderInput.model_validate(_order_payload(total_amount="149.99"))
