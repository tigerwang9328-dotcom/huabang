import os
from types import SimpleNamespace

os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("DB_PASSWORD", "test-only-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")

from app.api.v1.mumaren_finance_center import resolve_ledger_line_summary
from app.models.mumaren_finance_center import FinanceCenterMumarenVoucherLine


def test_explicitly_cleared_summary_is_a_persisted_voucher_line_field():
    assert "summary_explicitly_cleared" in FinanceCenterMumarenVoucherLine.__table__.c
    assert FinanceCenterMumarenVoucherLine.__table__.c.summary_explicitly_cleared.default.arg is False


def test_explicitly_cleared_line_is_not_backfilled_in_ledger():
    cleared_line = SimpleNamespace(summary=None, summary_explicitly_cleared=True)
    legacy_blank_line = SimpleNamespace(summary=None, summary_explicitly_cleared=False)

    assert resolve_ledger_line_summary(cleared_line, inherited_summary="上行摘要", voucher_summary="总摘要") == ""
    assert resolve_ledger_line_summary(legacy_blank_line, inherited_summary="上行摘要", voucher_summary="总摘要") == "上行摘要"
