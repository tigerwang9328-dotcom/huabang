from datetime import date
from decimal import Decimal

import pytest

from app.models.mumaren_finance_center_domains import (
    FinanceCenterMumarenCashFlow,
    FinanceCenterMumarenReceivableOrder,
    FinanceCenterMumarenTaxRecord,
    MUMAREN_FINANCE_DOMAIN_SCHEMA,
)
from app.services.mumaren_finance_center.ar_ap import (
    apply_settlement,
    build_aging,
    aging_bucket,
)
from app.services.mumaren_finance_center.business import depreciation_for_period
from app.services.mumaren_finance_center.tax import build_tax_alerts, tax_record_balance


def test_domain_models_stay_inside_mumaren_independent_schema():
    assert MUMAREN_FINANCE_DOMAIN_SCHEMA == "finance_center_mumaren"
    assert FinanceCenterMumarenReceivableOrder.__table__.schema == MUMAREN_FINANCE_DOMAIN_SCHEMA
    assert FinanceCenterMumarenCashFlow.__table__.schema == MUMAREN_FINANCE_DOMAIN_SCHEMA
    assert FinanceCenterMumarenTaxRecord.__table__.schema == MUMAREN_FINANCE_DOMAIN_SCHEMA
    assert FinanceCenterMumarenReceivableOrder.__tablename__.startswith("finance_center_mumaren_")


def test_receivable_settlement_rejects_overpayment_and_tracks_partial_status():
    assert apply_settlement(Decimal("100"), Decimal("30"), Decimal("20")) == {
        "settled_amount": Decimal("50"),
        "balance": Decimal("50"),
        "status": "partial",
    }
    with pytest.raises(ValueError, match="超过未结余额"):
        apply_settlement(Decimal("100"), Decimal("90"), Decimal("20"))


def test_aging_groups_open_documents_by_counterparty_and_age():
    result = build_aging(
        [
            {"counterparty_name": "客户甲", "order_no": "AR-1", "order_date": date(2026, 6, 1), "total_amount": "100", "settled_amount": "20"},
            {"counterparty_name": "客户乙", "order_no": "AR-2", "order_date": date(2026, 3, 1), "total_amount": "50", "settled_amount": "0"},
        ],
        as_of=date(2026, 7, 1),
    )
    assert aging_bucket(30) == "0-30天"
    assert aging_bucket(122) == "120天以上"
    assert result["total_balance"] == Decimal("130")
    assert result["buckets"]["0-30天"] == Decimal("80")
    assert result["buckets"]["120天以上"] == Decimal("50")


def test_aging_excludes_documents_after_the_selected_cutoff_date():
    result = build_aging(
        [
            {"counterparty_name": "客户甲", "order_no": "AR-before", "order_date": date(2026, 7, 1), "total_amount": "100", "settled_amount": "0"},
            {"counterparty_name": "客户甲", "order_no": "AR-after", "order_date": date(2026, 8, 1), "total_amount": "200", "settled_amount": "0"},
        ],
        as_of=date(2026, 7, 31),
    )

    assert result["total_balance"] == Decimal("100")
    assert [row["order_no"] for row in result["counterparties"][0]["orders"]] == ["AR-before"]


def test_business_depreciation_is_prorated_and_never_exceeds_original_value():
    assert depreciation_for_period(
        original_value=Decimal("12000"), residual_value=Decimal("1200"), useful_life_months=60,
        already_depreciated=Decimal("10600"),
    ) == Decimal("180")
    assert depreciation_for_period(
        original_value=Decimal("12000"), residual_value=Decimal("1200"), useful_life_months=60,
        already_depreciated=Decimal("10750"),
    ) == Decimal("50")


def test_tax_outstanding_and_alerts_only_include_unpaid_due_records():
    assert tax_record_balance(Decimal("100"), Decimal("40")) == Decimal("60")
    alerts = build_tax_alerts(
        [
            {"tax_name": "增值税", "period": "2026-06", "tax_amount": "100", "paid_amount": "40", "due_date": date(2026, 7, 1)},
            {"tax_name": "企业所得税", "period": "2026-06", "tax_amount": "20", "paid_amount": "20", "due_date": date(2026, 6, 1)},
        ],
        today=date(2026, 7, 2),
    )
    assert alerts == [{"tax_name": "增值税", "period": "2026-06", "outstanding": Decimal("60"), "due_date": date(2026, 7, 1), "level": "danger"}]
