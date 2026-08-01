from decimal import Decimal

from app.api.v1.mumaren_finance_center_crud import SalesMonthlyReportInput, SalesMonthlyReportUpdate


def test_sales_monthly_create_contract_preserves_store_code_and_return_amount():
    body = SalesMonthlyReportInput.model_validate({
        "book_id": 1, "period": "2026-08", "store_code": "285101", "store_name": "莱勒里沃",
        "sales_amount": "100.00", "return_amount": "20.00", "remark": "核对后补录",
    })
    assert body.store_code == "285101"
    assert body.return_amount == Decimal("20.00")


def test_sales_monthly_update_contract_requires_book_id_in_body_and_allows_return_amount():
    body = SalesMonthlyReportUpdate.model_validate({"book_id": 1, "return_amount": "12.50"})
    assert body.book_id == 1
    assert body.return_amount == Decimal("12.50")
