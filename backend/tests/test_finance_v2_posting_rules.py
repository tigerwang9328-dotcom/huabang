from datetime import date
from decimal import Decimal

from app.services.finance_v2.source_preview_domain import PreviewRule, preview_source_event


def test_preview_uses_the_most_specific_published_effective_rule_without_creating_a_draft():
    preview = preview_source_event(
        {
            "source_key": "sale-1",
            "source_system": "huabang_dwd",
            "business_type": "sale",
            "business_date": date(2026, 7, 1),
            "legal_entity_code": "HB",
            "organization_code": "GY",
            "book_id": 8,
            "amount": Decimal("100"),
        },
        [
            PreviewRule("sale", "generic-v1", "1122", "6001", source_system="huabang_dwd"),
            PreviewRule(
                "sale", "book-v2", "1002", "6001", source_system="huabang_dwd", legal_entity_code="HB",
                organization_code="GY", book_id=8, effective_from=date(2026, 7, 1), priority=5,
            ),
        ],
    )

    assert preview.status == "preview_ready"
    assert preview.rule_version == "book-v2"
    assert preview.entries == [{"debit_account": "1002", "credit_account": "6001", "amount": Decimal("100")}]
    assert preview.creates_draft is False


def test_preview_rejects_equally_specific_effective_rules_as_an_mapping_exception():
    event = {
        "source_key": "sale-1", "source_system": "huabang_dwd", "business_type": "sale",
        "business_date": date(2026, 7, 1), "amount": Decimal("100"),
    }
    rules = [
        PreviewRule("sale", "rule-a", "1122", "6001", source_system="huabang_dwd", priority=1),
        PreviewRule("sale", "rule-b", "1002", "6001", source_system="huabang_dwd", priority=1),
    ]

    preview = preview_source_event(event, rules)

    assert preview.status == "pending_mapping"
    assert preview.exception_code == "ambiguous_rule"
    assert preview.creates_draft is False
