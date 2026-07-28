from decimal import Decimal

import pytest

from app.services.finance_v2.domain import (
    FinanceV2DomainError,
    VoucherCommand,
    VoucherDraft,
    VoucherLineDraft,
    apply_voucher_command,
    canonical_dimension_hash,
    validate_voucher_lines,
)


def _draft(status: str = "draft", version: int = 1) -> VoucherDraft:
    return VoucherDraft(
        voucher_id="voucher-1",
        status=status,
        version=version,
        prepared_by="maker-1",
        reviewer_id=None,
    )


def _balanced_lines() -> list[VoucherLineDraft]:
    return [
        VoucherLineDraft(account_version_id="1001", summary="收款", debit=Decimal("100.00")),
        VoucherLineDraft(account_version_id="6001", summary="收入", credit=Decimal("100.00")),
    ]


def test_draft_can_only_reach_posted_through_review_and_approval():
    voucher = _draft()

    submitted = apply_voucher_command(voucher, VoucherCommand("submit", "maker-1", 1), _balanced_lines())
    reviewing = apply_voucher_command(submitted, VoucherCommand("start_review", "reviewer-1", 2), _balanced_lines())
    approved = apply_voucher_command(reviewing, VoucherCommand("approve", "reviewer-1", 3), _balanced_lines())
    posted = apply_voucher_command(approved, VoucherCommand("post", "poster-1", 4, reason="人工过账"), _balanced_lines())

    assert [submitted.status, reviewing.status, approved.status, posted.status] == [
        "submitted",
        "reviewing",
        "approved",
        "posted",
    ]
    assert posted.version == 5
    assert posted.reviewer_id == "reviewer-1"
    assert posted.posted_by == "poster-1"


def test_posting_a_draft_is_rejected_and_does_not_skip_review():
    with pytest.raises(FinanceV2DomainError, match="draft -> post"):
        apply_voucher_command(_draft(), VoucherCommand("post", "poster-1", 1, reason="人工过账"), _balanced_lines())


def test_stale_expected_version_is_a_conflict():
    with pytest.raises(FinanceV2DomainError, match="version conflict"):
        apply_voucher_command(_draft(version=3), VoucherCommand("submit", "maker-1", 2), _balanced_lines())


def test_submit_rejects_unbalanced_or_double_sided_lines():
    with pytest.raises(FinanceV2DomainError, match="not balanced"):
        validate_voucher_lines([VoucherLineDraft(account_version_id="1001", summary="x", debit=Decimal("1"))])
    with pytest.raises(FinanceV2DomainError, match="exactly one"):
        validate_voucher_lines(
            [
                VoucherLineDraft(
                    account_version_id="1001",
                    summary="x",
                    debit=Decimal("1"),
                    credit=Decimal("1"),
                ),
                VoucherLineDraft(account_version_id="6001", summary="y", debit=Decimal("1")),
            ]
        )


def test_rejected_voucher_requires_reason_to_reopen_and_cancel_is_terminal():
    rejected = VoucherDraft("voucher-1", "rejected", 7, "maker-1", "reviewer-1")
    with pytest.raises(FinanceV2DomainError, match="reason"):
        apply_voucher_command(rejected, VoucherCommand("reopen", "maker-1", 7), _balanced_lines())

    cancelled = apply_voucher_command(_draft(), VoucherCommand("cancel", "maker-1", 1, reason="重复制单"), _balanced_lines())
    with pytest.raises(FinanceV2DomainError, match="cancelled -> submit"):
        apply_voucher_command(cancelled, VoucherCommand("submit", "maker-1", 2), _balanced_lines())


def test_dimension_hash_is_stable_regardless_of_input_order():
    first = canonical_dimension_hash({"store": "GZ002", "department": "finance"})
    second = canonical_dimension_hash({"department": "finance", "store": "GZ002"})

    assert first == second
    assert len(first) == 64
