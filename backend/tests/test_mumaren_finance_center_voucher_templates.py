"""凭证模板的可套用分录与历史账簿只读契约测试。"""
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from mumaren_crud_helpers import _FakeUser, _MockDb


def _lines():
    return {
        "lines": [
            {"account_id": 11, "summary": "借方", "debit_amount": "100.00", "credit_amount": "0"},
            {"account_id": 12, "summary": "贷方", "debit_amount": "0", "credit_amount": "100.00"},
        ]
    }


def test_voucher_template_input_requires_balanced_usable_lines():
    from app.api.v1.mumaren_finance_center_crud import VoucherTemplateInput

    valid = VoucherTemplateInput(book_id=1, template_name="收款", lines_json=_lines())
    assert valid.lines_json.lines[0].debit_amount == Decimal("100.00")

    with pytest.raises(ValidationError, match="lines_json"):
        VoucherTemplateInput(book_id=1, template_name="空模板")

    with pytest.raises(ValidationError, match="借贷不平衡"):
        VoucherTemplateInput(
            book_id=1,
            template_name="不平衡",
            lines_json={"lines": [
                {"account_id": 11, "debit_amount": "100", "credit_amount": "0"},
                {"account_id": 12, "debit_amount": "0", "credit_amount": "90"},
            ]},
        )


@pytest.mark.asyncio
async def test_create_voucher_template_rejects_readonly_book():
    from app.api.v1.mumaren_finance_center_crud import VoucherTemplateInput, create_voucher_template
    from app.models.mumaren_finance_center import FinanceCenterMumarenBook

    readonly_book = FinanceCenterMumarenBook(
        id=1, book_code="KD-1", book_name="金蝶历史账簿", is_readonly=True,
    )
    db = _MockDb(get_map={FinanceCenterMumarenBook: {1: readonly_book}})

    with pytest.raises(HTTPException, match="只读") as exc:
        await create_voucher_template(
            VoucherTemplateInput(book_id=1, template_name="收款", lines_json=_lines()),
            _FakeUser(),
            db,
        )
    assert exc.value.status_code == 409
    assert db.added == []
