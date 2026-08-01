import os
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError


for _name, _value in {
    "APP_SECRET_KEY": "test-app-secret",
    "DB_PASSWORD": "test-db-password",
    "JWT_SECRET_KEY": "test-jwt-secret",
}.items():
    os.environ.setdefault(_name, _value)


def test_daily_parameter_batch_contract_only_accepts_known_finance_fields():
    from app.api.v1.mumaren_finance_center_domains import DailyOperatingParameterBatchInput

    body = DailyOperatingParameterBatchInput.model_validate({
        "book_id": 1,
        "period": "2026-08",
        "field": "express_unit_cost",
        "value": "5.50",
        "store_codes": ["285101", "285102"],
    })

    assert body.value == Decimal("5.50")
    assert body.store_codes == ["285101", "285102"]

    with pytest.raises(ValidationError):
        DailyOperatingParameterBatchInput.model_validate({
            "book_id": 1, "period": "2026-08", "field": "book_id", "value": "1", "store_codes": ["285101"],
        })


def test_daily_ad_cost_batch_contract_rejects_negative_costs():
    from app.api.v1.mumaren_finance_center_domains import DailyAdCostBatchInput

    with pytest.raises(ValidationError):
        DailyAdCostBatchInput.model_validate({
            "book_id": 1, "business_date": "2026-08-01", "store_codes": ["285101"], "ad_cost": "-0.01",
        })


@pytest.mark.parametrize("contract, payload", [
    ("parameter", {
        "book_id": 1, "period": "2026-08",
        "rows": [{"store_code": "285101"}, {"store_code": "285101"}],
    }),
    ("ad_cost", {
        "book_id": 1, "business_date": "2026-08-01",
        "rows": [{"store_code": "285101"}, {"store_code": "285101"}],
    }),
])
def test_daily_batch_save_rejects_duplicate_store_rows(contract, payload):
    from app.api.v1.mumaren_finance_center_domains import (
        DailyAdCostSaveInput,
        DailyOperatingParameterSaveInput,
    )

    input_type = DailyOperatingParameterSaveInput if contract == "parameter" else DailyAdCostSaveInput
    with pytest.raises(ValidationError, match="店铺编码不能重复"):
        input_type.model_validate(payload)


@pytest.mark.asyncio
async def test_daily_operating_write_rejects_readonly_or_missing_book():
    from fastapi import HTTPException
    from app.api.v1.mumaren_finance_center_domains import _require_writable_operating_book

    class Session:
        def __init__(self, book):
            self.book = book

        async def get(self, _, __):
            return self.book

    with pytest.raises(HTTPException, match="账簿不存在") as missing:
        await _require_writable_operating_book(Session(None), 1)
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException, match="金蝶迁移账簿只读") as readonly:
        await _require_writable_operating_book(Session(SimpleNamespace(is_readonly=True)), 1)
    assert readonly.value.status_code == 409
