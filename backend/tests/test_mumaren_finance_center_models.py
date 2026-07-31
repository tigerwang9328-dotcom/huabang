import os


# 模型导入会加载华邦配置；这些仅是单测导入所需的无效占位值。
os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("DB_PASSWORD", "test-only-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")

from app.models.mumaren_finance_center import (
    FinanceCenterMumarenAccount,
    FinanceCenterMumarenAuditLog,
    FinanceCenterMumarenBook,
    FinanceCenterMumarenFiscalPeriod,
    FinanceCenterMumarenHistoryImportBatch,
    FinanceCenterMumarenHistoryVoucher,
    FinanceCenterMumarenVoucher,
    FinanceCenterMumarenVoucherLine,
)
from pathlib import Path


def test_all_mumaren_finance_models_use_an_isolated_schema_and_table_prefix():
    models = (
        FinanceCenterMumarenBook,
        FinanceCenterMumarenAccount,
        FinanceCenterMumarenFiscalPeriod,
        FinanceCenterMumarenVoucher,
        FinanceCenterMumarenVoucherLine,
        FinanceCenterMumarenAuditLog,
        FinanceCenterMumarenHistoryImportBatch,
        FinanceCenterMumarenHistoryVoucher,
    )

    for model in models:
        assert model.__table__.schema == "finance_center_mumaren"
        assert model.__tablename__.startswith("finance_center_mumaren_")


def test_mumaren_finance_models_are_registered_for_alembic_metadata():
    models_init = Path(__file__).parents[1] / "app" / "models" / "__init__.py"
    assert "from app.models.mumaren_finance_center import" in models_init.read_text(encoding="utf-8")


def test_history_voucher_is_explicitly_read_only_and_marked_historical():
    voucher = FinanceCenterMumarenHistoryVoucher(
        source_system="kingdee",
        source_key="KD-2024-0001",
        voucher_no="记-2024-0001",
        voucher_date="2024-01-31",
        summary="历史期初",
    )

    assert voucher.is_readonly is True
    assert voucher.record_type == "historical"


def test_history_voucher_line_uses_the_same_isolated_read_only_history_schema():
    from app.models import mumaren_finance_center

    history_line = getattr(mumaren_finance_center, "FinanceCenterMumarenHistoryVoucherLine", None)
    assert history_line is not None
    assert history_line.__table__.schema == "finance_center_mumaren"
    assert history_line.__tablename__ == "finance_center_mumaren_history_voucher_lines"


def test_orm_required_columns_match_the_current_and_history_migration_contract():
    assert FinanceCenterMumarenVoucher.__table__.c.book_id.nullable is False
    assert FinanceCenterMumarenVoucher.__table__.c.voucher_no.nullable is False
    assert FinanceCenterMumarenVoucher.__table__.c.voucher_date.nullable is False
    assert FinanceCenterMumarenHistoryVoucher.__table__.c.import_batch_id.nullable is False
