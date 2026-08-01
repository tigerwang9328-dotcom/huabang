from decimal import Decimal

import pytest

from app.services.mumaren_finance_center.auto_voucher import (
    AutoVoucherRuleConfigurationError,
    build_auto_voucher_draft,
)


def test_auto_voucher_draft_is_balanced_and_never_posted():
    draft = build_auto_voucher_draft(
        rule={
            "id": 7,
            "book_id": 1,
            "trigger_event": "sales_monthly",
            "debit_account_id": 101,
            "credit_account_id": 201,
            "default_amount": Decimal("120.50"),
            "summary": "月度销售结转",
            "voucher_type": "记",
        },
        amount=None,
        source_key="2026-08",
    )

    assert draft["status"] == "draft"
    assert draft["source_key"] == "auto-rule:7:2026-08"
    assert draft["lines"] == [
        {"account_id": 101, "summary": "月度销售结转", "debit_amount": Decimal("120.50"), "credit_amount": Decimal("0")},
        {"account_id": 201, "summary": "月度销售结转", "debit_amount": Decimal("0"), "credit_amount": Decimal("120.50")},
    ]


def test_auto_voucher_requires_positive_explicit_or_default_amount_and_two_accounts():
    rule = {"id": 7, "debit_account_id": 101, "credit_account_id": 201, "default_amount": None, "summary": None}
    with pytest.raises(AutoVoucherRuleConfigurationError, match="金额"):
        build_auto_voucher_draft(rule=rule, amount=None, source_key="source-1")

    with pytest.raises(AutoVoucherRuleConfigurationError, match="借方和贷方"):
        build_auto_voucher_draft(rule={**rule, "credit_account_id": None}, amount=Decimal("1"), source_key="source-1")

