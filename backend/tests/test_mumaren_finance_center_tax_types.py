import os

import pytest


os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("DB_PASSWORD", "test-only-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")

from app.models.mumaren_finance_center_domains import FinanceCenterMumarenTaxType


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Db:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _Rows([
            FinanceCenterMumarenTaxType(id=11, book_id=1, tax_code="VAT", tax_name="增值税", default_rate=0.13, is_active=True),
        ])


@pytest.mark.asyncio
async def test_list_tax_types_returns_only_active_types_for_selected_book():
    from app.api.v1.mumaren_finance_center_domains import list_tax_types

    db = _Db()
    response = await list_tax_types(book_id=1, _=None, db=db)

    assert response.data == [{"id": 11, "tax_code": "VAT", "tax_name": "增值税", "default_rate": 0.13}]
    assert "is_active IS true" in str(db.statement)
    assert "book_id" in str(db.statement)
