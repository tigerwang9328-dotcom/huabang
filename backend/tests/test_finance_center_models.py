from pathlib import Path

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Numeric, UniqueConstraint

from app.models.finance_core import (
    FinAccount,
    FinAuxCategory,
    FinAuxItem,
    FinBook,
    FinLedgerBalance,
    FinOperationLog,
    FinPeriod,
    FinSourceLink,
    FinStatementLine,
    FinStatementMapping,
    FinVoucher,
    FinVoucherEntry,
    FinVoucherVersion,
)
from app.models.finance_operations import (
    FinAutoEntryRule,
    FinAutoEntryRun,
    FinBankTransaction,
    FinCashAccount,
    FinDepreciation,
    FinFixedAsset,
    FinInvoice,
    FinPayable,
    FinPayroll,
    FinReceivable,
    FinReconciliation,
    FinSettlement,
    FinTaxRecord,
)


CORE_MODELS = (
    FinBook,
    FinPeriod,
    FinAccount,
    FinAuxCategory,
    FinAuxItem,
    FinVoucher,
    FinVoucherEntry,
    FinVoucherVersion,
    FinLedgerBalance,
    FinStatementLine,
    FinStatementMapping,
    FinOperationLog,
    FinSourceLink,
)

OPERATION_MODELS = (
    FinReceivable,
    FinPayable,
    FinSettlement,
    FinCashAccount,
    FinBankTransaction,
    FinReconciliation,
    FinFixedAsset,
    FinDepreciation,
    FinInvoice,
    FinPayroll,
    FinTaxRecord,
    FinAutoEntryRule,
    FinAutoEntryRun,
)


def _unique_column_sets(model):
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _foreign_key_targets(model):
    return {
        foreign_key.target_fullname
        for column in model.__table__.columns
        for foreign_key in column.foreign_keys
    }


def _composite_foreign_keys(model):
    return {
        (tuple(element.parent.name for element in constraint.elements), tuple(element.target_fullname for element in constraint.elements))
        for constraint in model.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint) and len(constraint.elements) > 1
    }


def _partial_unique_source_indexes(model):
    return {
        index.name
        for index in model.__table__.indexes
        if index.unique and index.dialect_options["postgresql"]["where"] is not None
    }


def test_all_formal_finance_models_live_in_fin_schema():
    for model in CORE_MODELS + OPERATION_MODELS:
        assert model.__table__.schema == "fin", model.__name__


def test_book_scoped_business_keys_are_idempotent():
    assert ("legal_entity_id",) in _unique_column_sets(FinBook)
    assert ("book_id", "period") in _unique_column_sets(FinPeriod)
    assert ("book_id", "account_code") in _unique_column_sets(FinAccount)
    assert ("book_id", "voucher_no") in _unique_column_sets(FinVoucher)
    assert ("voucher_id", "line_no") in _unique_column_sets(FinVoucherEntry)
    assert ("book_id", "account_id", "period") in _unique_column_sets(FinLedgerBalance)
    assert ("book_id", "source_system", "source_database", "source_pk") in _unique_column_sets(FinSourceLink)


def test_voucher_contract_supports_state_machine_audit_and_concurrency():
    columns = FinVoucher.__table__.columns
    assert {
        "status",
        "version",
        "origin_kind",
        "source_status",
        "reviewed_by",
        "reviewed_at",
        "posted_by",
        "posted_at",
        "reversal_of_id",
        "total_debit",
        "total_credit",
    }.issubset(columns.keys())
    assert columns.version.nullable is False
    assert "fin.voucher.id" in _foreign_key_targets(FinVoucherEntry)
    assert "fin.account.id" in _foreign_key_targets(FinVoucherEntry)
    assert "fin.voucher.id" in _foreign_key_targets(FinVoucherVersion)
    assert (("book_id", "period_id"), ("fin.period.book_id", "fin.period.id")) in _composite_foreign_keys(FinVoucher)
    assert (("book_id", "voucher_id"), ("fin.voucher.book_id", "fin.voucher.id")) in _composite_foreign_keys(FinVoucherEntry)
    assert (("book_id", "account_id"), ("fin.account.book_id", "fin.account.id")) in _composite_foreign_keys(FinVoucherEntry)
    assert (("book_id", "parent_id"), ("fin.account.book_id", "fin.account.id")) in _composite_foreign_keys(FinAccount)
    assert (("book_id", "reversal_of_id"), ("fin.voucher.book_id", "fin.voucher.id")) in _composite_foreign_keys(FinVoucher)
    assert (("book_id", "reversed_by_id"), ("fin.voucher.book_id", "fin.voucher.id")) in _composite_foreign_keys(FinVoucher)


def test_accounting_amounts_use_fixed_decimal_precision():
    amount_columns = (
        FinVoucher.total_debit,
        FinVoucher.total_credit,
        FinVoucherEntry.debit_amount,
        FinVoucherEntry.credit_amount,
        FinLedgerBalance.opening_amount,
        FinLedgerBalance.period_debit,
        FinLedgerBalance.period_credit,
        FinLedgerBalance.closing_amount,
        FinReceivable.original_amount,
        FinPayable.original_amount,
        FinBankTransaction.amount,
        FinFixedAsset.original_cost,
        FinInvoice.total_amount,
        FinPayroll.net_amount,
        FinTaxRecord.tax_amount,
    )
    for instrumented_column in amount_columns:
        column_type = instrumented_column.property.columns[0].type
        assert isinstance(column_type, Numeric)
        assert (column_type.precision, column_type.scale) == (18, 4)


def test_source_driven_records_keep_lineage_and_versions():
    lineage = {
        "source_system",
        "source_database",
        "source_pk",
        "import_batch_id",
        "source_updated_at",
    }
    for model in (
        FinBook,
        FinAccount,
        FinAuxItem,
        FinVoucher,
        FinReceivable,
        FinPayable,
        FinBankTransaction,
        FinInvoice,
        FinPayroll,
        FinTaxRecord,
    ):
        assert lineage.issubset(model.__table__.columns.keys()), model.__name__
    for model in (FinVoucher, FinReceivable, FinPayable, FinInvoice, FinPayroll):
        assert "version" in model.__table__.columns, model.__name__
    assert FinReceivable.__table__.columns.source_pk.nullable is True
    assert "uq_fin_book_source" in _partial_unique_source_indexes(FinBook)
    assert "uq_fin_account_source" in _partial_unique_source_indexes(FinAccount)
    assert "uq_fin_aux_item_source" in _partial_unique_source_indexes(FinAuxItem)
    assert "uq_fin_voucher_source" in _partial_unique_source_indexes(FinVoucher)
    assert "uq_fin_receivable_source" in _partial_unique_source_indexes(FinReceivable)
    assert "uq_fin_payable_source" in _partial_unique_source_indexes(FinPayable)
    assert "uq_fin_bank_transaction_source" in _partial_unique_source_indexes(FinBankTransaction)
    assert "uq_fin_invoice_source" in _partial_unique_source_indexes(FinInvoice)
    assert "uq_fin_payroll_source" in _partial_unique_source_indexes(FinPayroll)
    assert "uq_fin_tax_record_source" in _partial_unique_source_indexes(FinTaxRecord)


def test_statement_templates_are_versioned_and_financial_checks_are_declared():
    assert ("template_code", "template_version", "statement_type", "line_code") in _unique_column_sets(FinStatementLine)
    assert ("book_id", "account_id", "statement_line_id") in _unique_column_sets(FinStatementMapping)
    assert any(isinstance(item, CheckConstraint) for item in FinVoucher.__table__.constraints)
    assert any(isinstance(item, CheckConstraint) for item in FinReceivable.__table__.constraints)
    assert any(isinstance(item, CheckConstraint) for item in FinFixedAsset.__table__.constraints)


def test_operational_models_link_to_books_and_only_generate_draft_vouchers():
    for model in OPERATION_MODELS:
        assert "fin.book.id" in _foreign_key_targets(model), model.__name__
    for model in (
        FinReceivable,
        FinPayable,
        FinSettlement,
        FinBankTransaction,
        FinDepreciation,
        FinInvoice,
        FinPayroll,
        FinTaxRecord,
        FinAutoEntryRun,
    ):
        assert "draft_voucher_id" in model.__table__.columns, model.__name__
    assert "draft_voucher_id" not in FinCashAccount.__table__.columns
    assert "draft_voucher_id" not in FinAutoEntryRule.__table__.columns
    assert (("book_id", "receivable_id"), ("fin.receivable.book_id", "fin.receivable.id")) in _composite_foreign_keys(FinSettlement)
    assert (("book_id", "payable_id"), ("fin.payable.book_id", "fin.payable.id")) in _composite_foreign_keys(FinSettlement)
    assert any(
        constraint.name == "ck_fin_settlement_one_target"
        for constraint in FinSettlement.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    )


def test_migration_is_single_head_and_seeds_finance_permissions():
    migration = Path(__file__).parents[1] / "alembic/versions/3e1f6a7b8c97_full_finance_center.py"
    source = migration.read_text(encoding="utf-8")

    assert 'revision = "3e1f6a7b8c97"' in source
    assert 'down_revision = "2d1f6a7b8c96"' in source
    assert 'op.execute("CREATE SCHEMA IF NOT EXISTS fin")' in source
    for table_name in (
        "book",
        "period",
        "account",
        "voucher",
        "voucher_entry",
        "ledger_balance",
        "receivable",
        "payable",
        "cash_account",
        "fixed_asset",
        "invoice",
        "payroll",
        "tax_record",
        "auto_entry_rule",
    ):
        assert f'"{table_name}"' in source
    for permission in (
        "finance:center:view",
        "finance:voucher:write",
        "finance:voucher:post",
        "finance:period:close",
        "finance:settings:write",
        "finance:sensitive:view",
        "finance:export",
    ):
        assert permission in source
    assert "CREATE CONSTRAINT TRIGGER fin_validate_voucher" in source
    assert "fin_guard_voucher_entry_mutation" in source
    assert "guard_draft_voucher_reference" in source
    assert "fk_fin_settlement_book_receivable" in source
    assert "fk_fin_settlement_book_payable" in source
    assert "migration:3e1f6a7b8c97" in source
    assert "INSERT INTO sys.sys_role_permission" in source
    assert "finance_manager" in source
    assert "accountant" in source
    assert "cashier" in source
    assert "boss" in source
    assert "ceo" in source
    assert "finance_center_permission_grant_backup" in source
    assert "DELETE FROM sys.sys_permission permission" in source
    assert "permission.description" in source
    assert "DROP TABLE IF EXISTS fin." in source
    assert "CASCADE" not in source[source.index("def downgrade") :]
    for index_name in (
        "ix_fin_voucher_entry_book_voucher",
        "ix_fin_ledger_balance_book_period",
        "ix_fin_receivable_book_counterparty",
        "ix_fin_cash_account_book_account",
        "ix_fin_bank_transaction_book_cash",
        "ix_fin_fixed_asset_book_expense",
        "ix_fin_invoice_book_counterparty",
        "ix_fin_payroll_book_employee",
    ):
        assert index_name in source
    for index_name in (
        "uq_fin_book_source",
        "uq_fin_account_source",
        "uq_fin_aux_item_source",
        "uq_fin_voucher_source",
        "uq_fin_tax_record_source",
    ):
        assert index_name in source


def test_async_sqlalchemy_runtime_dependency_is_declared():
    requirements = (Path(__file__).parents[1] / "requirements.txt").read_text(encoding="utf-8")
    assert "greenlet==3.5.3" in requirements
