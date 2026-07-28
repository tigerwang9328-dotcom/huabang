from decimal import Decimal

from app.services.finance_v2.source_preview_domain import PreviewRule, preview_source_event


def test_source_preview_returns_suggestion_without_creating_a_draft():
    preview = preview_source_event(
        {"source_key": "sale-1", "business_type": "sale", "amount": Decimal("100")},
        [PreviewRule("sale", "sales-v1", "1122", "6001")],
    )

    assert preview.status == "preview_ready"
    assert preview.rule_version == "sales-v1"
    assert preview.creates_draft is False
    assert preview.entries[0]["debit_account"] == "1122"


def test_source_preview_routes_missing_rule_to_exception_without_side_effects():
    preview = preview_source_event({"source_key": "sale-1", "business_type": "sale", "amount": Decimal("100")}, [])

    assert preview.status == "pending_mapping"
    assert preview.creates_draft is False
    assert preview.exception_code == "missing_rule"
