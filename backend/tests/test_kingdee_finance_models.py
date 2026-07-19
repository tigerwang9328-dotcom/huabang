from sqlalchemy import UniqueConstraint
from pathlib import Path

from app.models.kingdee_finance import (
    DimFinanceAccount,
    DimFinanceStatementMapping,
    DimLegalEntity,
    DimSourceOrgMapping,
    DmFinanceStatementMonthly,
    DwdGlBalanceMonthly,
    DwdGlVoucher,
    DwdGlVoucherEntry,
    KingdeeAccount,
    KingdeeBalance,
    KingdeeImportBatch,
    KingdeeVoucher,
    KingdeeVoucherEntry,
)


def test_kingdee_models_follow_existing_warehouse_layers():
    assert KingdeeImportBatch.__table__.schema == "ods"
    assert KingdeeAccount.__table__.schema == "ods"
    assert KingdeeVoucher.__table__.schema == "ods"
    assert KingdeeVoucherEntry.__table__.schema == "ods"
    assert KingdeeBalance.__table__.schema == "ods"
    assert DimLegalEntity.__table__.schema == "dim"
    assert DimFinanceAccount.__table__.schema == "dim"
    assert DimFinanceStatementMapping.__table__.schema == "dim"
    assert DwdGlVoucher.__table__.schema == "dwd"
    assert DwdGlVoucherEntry.__table__.schema == "dwd"
    assert DwdGlBalanceMonthly.__table__.schema == "dwd"
    assert DmFinanceStatementMonthly.__table__.schema == "dm"


def test_source_keys_are_idempotent_and_account_set_scoped():
    expected = {
        "uq_kingdee_account_source",
        "uq_kingdee_voucher_source",
        "uq_kingdee_voucher_entry_source",
        "uq_kingdee_balance_source",
        "uq_dwd_gl_voucher_source",
        "uq_dwd_gl_voucher_entry_source",
        "uq_dwd_gl_balance_source",
    }
    models = (
        KingdeeAccount,
        KingdeeVoucher,
        KingdeeVoucherEntry,
        KingdeeBalance,
        DwdGlVoucher,
        DwdGlVoucherEntry,
        DwdGlBalanceMonthly,
    )
    actual = {
        constraint.name
        for model in models
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert expected.issubset(actual)


def test_historical_vouchers_expose_source_status_without_mutation_status():
    columns = DwdGlVoucher.__table__.columns
    assert "source_status" in columns
    assert "is_posted" in columns
    assert "reviewed_by" not in columns
    assert "posted_by" not in columns


def test_imported_and_derived_finance_records_keep_full_source_lineage():
    lineage = {"source_system", "source_database", "source_pk", "import_batch_id", "source_updated_at"}
    for model in (
        KingdeeAccount, KingdeeVoucher, KingdeeVoucherEntry, KingdeeBalance,
        DimLegalEntity, DimFinanceAccount, DimFinanceStatementMapping,
        DimSourceOrgMapping, DwdGlVoucher, DwdGlVoucherEntry,
        DwdGlBalanceMonthly, DmFinanceStatementMonthly,
    ):
        assert lineage.issubset(model.__table__.columns.keys()), model.__name__


def test_alembic_uses_environment_database_url_instead_of_hardcoded_production_url():
    env_source = (Path(__file__).parents[1] / "alembic" / "env.py").read_text(encoding="utf-8")

    assert "settings.DATABASE_URL_SYNC" in env_source
    assert 'config.set_main_option("sqlalchemy.url"' in env_source
