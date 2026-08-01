"""Add the read-only Kingdee historical finance warehouse.

Revision ID: 2c1f6a7b8c95
Revises: 2b0f6a7b8c94
"""

from alembic import op


revision = "2c1f6a7b8c95"
down_revision = "2b0f6a7b8c94"
branch_labels = None
depends_on = None


TABLES = {
    "ods": [
        "kingdee_import_batch", "kingdee_account", "kingdee_voucher",
        "kingdee_voucher_entry", "kingdee_balance", "kingdee_department",
        "kingdee_employee", "kingdee_supplier", "kingdee_currency",
        "kingdee_aux_item",
    ],
    "dim": [
        "dim_legal_entity", "dim_finance_account",
        "dim_finance_statement_mapping", "dim_source_org_mapping",
    ],
    "dwd": ["dwd_gl_voucher", "dwd_gl_voucher_entry", "dwd_gl_balance_monthly"],
    "dm": ["dm_finance_statement_monthly"],
}


def upgrade() -> None:
    bind = op.get_bind()
    from app.models.kingdee_finance import (
        DimFinanceAccount, DimFinanceStatementMapping, DimLegalEntity,
        DimSourceOrgMapping, DmFinanceStatementMonthly, DwdGlBalanceMonthly,
        DwdGlVoucher, DwdGlVoucherEntry, KingdeeAccount, KingdeeAuxItem,
        KingdeeBalance, KingdeeCurrency, KingdeeDepartment, KingdeeEmployee,
        KingdeeImportBatch, KingdeeSupplier, KingdeeVoucher, KingdeeVoucherEntry,
    )
    models = (
        KingdeeImportBatch, KingdeeAccount, KingdeeVoucher, KingdeeVoucherEntry,
        KingdeeBalance, KingdeeDepartment, KingdeeEmployee, KingdeeSupplier,
        KingdeeCurrency, KingdeeAuxItem, DimLegalEntity, DimFinanceAccount,
        DimFinanceStatementMapping, DimSourceOrgMapping, DwdGlVoucher,
        DwdGlVoucherEntry, DwdGlBalanceMonthly, DmFinanceStatementMonthly,
    )
    for model in models:
        model.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    for schema in ("dm", "dwd", "dim", "ods"):
        for table in reversed(TABLES[schema]):
            op.execute(f'DROP TABLE IF EXISTS "{schema}"."{table}" CASCADE')
