from app.services.finance_v2.source_inbox import SourceIdentity, classify_source_receipt


def test_source_inbox_treats_the_same_identity_and_hash_as_idempotent():
    result = classify_source_receipt(
        existing=SourceIdentity("huabang_dwd", "dwd_sales_detail:42", "a" * 64),
        incoming=SourceIdentity("huabang_dwd", "dwd_sales_detail:42", "a" * 64),
    )

    assert result.status == "already_imported"
    assert result.creates_inbox_item is False
    assert result.exception_code is None


def test_source_inbox_blocks_a_changed_hash_for_the_same_source_identity():
    result = classify_source_receipt(
        existing=SourceIdentity("huabang_dwd", "dwd_sales_detail:42", "a" * 64),
        incoming=SourceIdentity("huabang_dwd", "dwd_sales_detail:42", "b" * 64),
    )

    assert result.status == "conflicted"
    assert result.creates_inbox_item is False
    assert result.exception_code == "source_hash_changed"


def test_source_inbox_accepts_a_new_identity_only_as_a_preview_candidate():
    result = classify_source_receipt(
        existing=None,
        incoming=SourceIdentity("huabang_dwd", "dwd_sales_detail:42", "a" * 64),
    )

    assert result.status == "received"
    assert result.creates_inbox_item is True
    assert result.creates_draft is False
