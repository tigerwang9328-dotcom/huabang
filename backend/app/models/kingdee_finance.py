"""Read-only Kingdee K/3 historical finance warehouse models."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


LINEAGE_COLUMNS = {
    "source_system": lambda: Column(String(32), nullable=False, server_default="kingdee"),
    "source_database": lambda: Column(String(128), nullable=False),
    "source_pk": lambda: Column(String(256), nullable=False),
    "import_batch_id": lambda: Column(String(64), nullable=False, index=True),
    "source_updated_at": lambda: Column(DateTime(timezone=True)),
}


class KingdeeImportBatch(Base):
    __tablename__ = "kingdee_import_batch"
    __table_args__ = {"schema": "ods"}

    batch_id = Column(String(64), primary_key=True)
    run_id = Column(String(64), nullable=False)
    source_database = Column(String(128), nullable=False)
    restored_database = Column(String(128))
    backup_file = Column(String(512), nullable=False)
    backup_sha256 = Column(String(64), nullable=False)
    manifest_sha256 = Column(String(64))
    status = Column(String(24), nullable=False, server_default="pending")
    expected_counts = Column(JSONB, nullable=False, server_default="{}")
    actual_counts = Column(JSONB, nullable=False, server_default="{}")
    validation_result = Column(JSONB, nullable=False, server_default="{}")
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class _KingdeeSourceMixin:
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_system = LINEAGE_COLUMNS["source_system"]()
    source_database = LINEAGE_COLUMNS["source_database"]()
    source_pk = LINEAGE_COLUMNS["source_pk"]()
    import_batch_id = LINEAGE_COLUMNS["import_batch_id"]()
    source_updated_at = LINEAGE_COLUMNS["source_updated_at"]()
    raw_data = Column(JSONB, nullable=False, server_default="{}")
    imported_at = Column(DateTime(timezone=True), server_default=func.now())


class KingdeeAccount(_KingdeeSourceMixin, Base):
    __tablename__ = "kingdee_account"
    __table_args__ = (
        UniqueConstraint("source_database", "source_pk", name="uq_kingdee_account_source"),
        {"schema": "ods"},
    )
    account_id = Column(String(64), nullable=False)
    account_code = Column(String(64), nullable=False)
    account_name = Column(String(256), nullable=False)
    parent_account_id = Column(String(64))
    account_level = Column(Integer)
    account_class = Column(String(64))
    balance_direction = Column(String(8))
    is_detail = Column(Boolean)
    is_cash = Column(Boolean)
    is_bank = Column(Boolean)
    is_contact = Column(Boolean)
    is_cash_flow = Column(Boolean)


class KingdeeVoucher(_KingdeeSourceMixin, Base):
    __tablename__ = "kingdee_voucher"
    __table_args__ = (
        UniqueConstraint("source_database", "source_pk", name="uq_kingdee_voucher_source"),
        {"schema": "ods"},
    )
    voucher_id = Column(String(64), nullable=False)
    voucher_no = Column(String(64))
    voucher_group = Column(String(32))
    voucher_date = Column(Date, nullable=False)
    fiscal_year = Column(Integer, nullable=False)
    fiscal_period = Column(Integer, nullable=False)
    source_status = Column(String(32))
    is_checked = Column(Boolean)
    is_posted = Column(Boolean)
    preparer_name = Column(String(128))
    checker_name = Column(String(128))
    poster_name = Column(String(128))
    total_debit = Column(Numeric(20, 4), nullable=False, server_default="0")
    total_credit = Column(Numeric(20, 4), nullable=False, server_default="0")


class KingdeeVoucherEntry(_KingdeeSourceMixin, Base):
    __tablename__ = "kingdee_voucher_entry"
    __table_args__ = (
        UniqueConstraint("source_database", "source_pk", name="uq_kingdee_voucher_entry_source"),
        {"schema": "ods"},
    )
    voucher_id = Column(String(64), nullable=False)
    entry_id = Column(String(64), nullable=False)
    line_no = Column(Integer)
    account_id = Column(String(64), nullable=False)
    account_code = Column(String(64))
    summary = Column(String(512))
    currency_id = Column(String(64))
    exchange_rate = Column(Numeric(20, 8))
    debit_amount = Column(Numeric(20, 4), nullable=False, server_default="0")
    credit_amount = Column(Numeric(20, 4), nullable=False, server_default="0")
    quantity = Column(Numeric(20, 6))
    detail_id = Column(String(128))
    settlement_no = Column(String(128))


class KingdeeBalance(_KingdeeSourceMixin, Base):
    __tablename__ = "kingdee_balance"
    __table_args__ = (
        UniqueConstraint("source_database", "source_pk", name="uq_kingdee_balance_source"),
        {"schema": "ods"},
    )
    fiscal_year = Column(Integer, nullable=False)
    fiscal_period = Column(Integer, nullable=False)
    account_id = Column(String(64), nullable=False)
    detail_id = Column(String(128), nullable=False, server_default="")
    currency_id = Column(String(64), nullable=False, server_default="")
    framework_id = Column(String(64), nullable=False, server_default="")
    is_adjust_period = Column(Boolean, nullable=False, server_default="false")
    opening_debit = Column(Numeric(20, 4), nullable=False, server_default="0")
    opening_credit = Column(Numeric(20, 4), nullable=False, server_default="0")
    period_debit = Column(Numeric(20, 4), nullable=False, server_default="0")
    period_credit = Column(Numeric(20, 4), nullable=False, server_default="0")
    ytd_debit = Column(Numeric(20, 4), nullable=False, server_default="0")
    ytd_credit = Column(Numeric(20, 4), nullable=False, server_default="0")
    closing_debit = Column(Numeric(20, 4), nullable=False, server_default="0")
    closing_credit = Column(Numeric(20, 4), nullable=False, server_default="0")


class KingdeeDepartment(_KingdeeSourceMixin, Base):
    __tablename__ = "kingdee_department"
    __table_args__ = (UniqueConstraint("source_database", "source_pk", name="uq_kingdee_department_source"), {"schema": "ods"})
    department_id = Column(String(64), nullable=False)
    department_code = Column(String(64))
    department_name = Column(String(256))
    parent_department_id = Column(String(64))


class KingdeeEmployee(_KingdeeSourceMixin, Base):
    __tablename__ = "kingdee_employee"
    __table_args__ = (UniqueConstraint("source_database", "source_pk", name="uq_kingdee_employee_source"), {"schema": "ods"})
    employee_id = Column(String(64), nullable=False)
    employee_code = Column(String(64))
    employee_name = Column(String(128))
    department_id = Column(String(64))
    employment_status = Column(String(32))


class KingdeeSupplier(_KingdeeSourceMixin, Base):
    __tablename__ = "kingdee_supplier"
    __table_args__ = (UniqueConstraint("source_database", "source_pk", name="uq_kingdee_supplier_source"), {"schema": "ods"})
    supplier_id = Column(String(64), nullable=False)
    supplier_code = Column(String(64))
    supplier_name = Column(String(256))
    contact_name = Column(String(128))


class KingdeeCurrency(_KingdeeSourceMixin, Base):
    __tablename__ = "kingdee_currency"
    __table_args__ = (UniqueConstraint("source_database", "source_pk", name="uq_kingdee_currency_source"), {"schema": "ods"})
    currency_id = Column(String(64), nullable=False)
    currency_code = Column(String(32))
    currency_name = Column(String(64))
    precision = Column(Integer)


class KingdeeAuxItem(_KingdeeSourceMixin, Base):
    __tablename__ = "kingdee_aux_item"
    __table_args__ = (UniqueConstraint("source_database", "source_pk", name="uq_kingdee_aux_item_source"), {"schema": "ods"})
    item_id = Column(String(128), nullable=False)
    item_class = Column(String(64))
    item_code = Column(String(64))
    item_name = Column(String(256))


class DimLegalEntity(Base):
    __tablename__ = "dim_legal_entity"
    __table_args__ = (UniqueConstraint("source_system", "account_set_code", name="uq_legal_entity_source_account_set"), {"schema": "dim"})
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    entity_code = Column(String(64), nullable=False, unique=True)
    entity_name = Column(String(256), nullable=False)
    short_name = Column(String(128))
    source_system = Column(String(32), nullable=False, server_default="kingdee")
    source_database = Column(String(128), nullable=False)
    source_pk = Column(String(256), nullable=False)
    import_batch_id = Column(String(64), nullable=False, index=True)
    source_updated_at = Column(DateTime(timezone=True))
    account_set_code = Column(String(128), nullable=False)
    start_period = Column(String(7))
    current_period = Column(String(7))
    status = Column(String(24), nullable=False, server_default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DimFinanceAccount(Base):
    __tablename__ = "dim_finance_account"
    __table_args__ = (UniqueConstraint("legal_entity_id", "source_account_id", name="uq_finance_account_entity_source"), {"schema": "dim"})
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    legal_entity_id = Column(BigInteger, nullable=False, index=True)
    source_account_id = Column(String(64), nullable=False)
    account_code = Column(String(64), nullable=False)
    account_name = Column(String(256), nullable=False)
    parent_account_id = Column(BigInteger)
    account_level = Column(Integer)
    account_type = Column(String(32))
    balance_direction = Column(String(8))
    is_cash = Column(Boolean, nullable=False, server_default="false")
    is_bank = Column(Boolean, nullable=False, server_default="false")
    is_active = Column(Boolean, nullable=False, server_default="true")
    source_system = Column(String(32), nullable=False, server_default="kingdee")
    source_database = Column(String(128), nullable=False)
    source_pk = Column(String(256), nullable=False)
    import_batch_id = Column(String(64), nullable=False)
    source_updated_at = Column(DateTime(timezone=True))


class DimFinanceStatementMapping(Base):
    __tablename__ = "dim_finance_statement_mapping"
    __table_args__ = (UniqueConstraint("legal_entity_id", "finance_account_id", "statement_type", name="uq_finance_statement_mapping"), {"schema": "dim"})
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    legal_entity_id = Column(BigInteger, nullable=False, index=True)
    finance_account_id = Column(BigInteger, nullable=False, index=True)
    statement_type = Column(String(32), nullable=False)
    line_code = Column(String(64), nullable=False)
    line_name = Column(String(128), nullable=False)
    display_order = Column(Integer, nullable=False, server_default="0")
    amount_sign = Column(Integer, nullable=False, server_default="1")
    mapping_status = Column(String(24), nullable=False, server_default="pending_confirmation")
    confirmed_by = Column(BigInteger)
    confirmed_at = Column(DateTime(timezone=True))
    source_system = Column(String(32), nullable=False, server_default="manual")
    source_database = Column(String(128), nullable=False, server_default="")
    source_pk = Column(String(256), nullable=False)
    import_batch_id = Column(String(64), nullable=False, server_default="manual")
    source_updated_at = Column(DateTime(timezone=True))


class DimSourceOrgMapping(Base):
    __tablename__ = "dim_source_org_mapping"
    __table_args__ = (UniqueConstraint("source_system", "source_database", "source_type", "source_code", name="uq_source_org_mapping"), {"schema": "dim"})
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_system = Column(String(32), nullable=False, server_default="kingdee")
    source_database = Column(String(128), nullable=False)
    source_type = Column(String(32), nullable=False)
    source_code = Column(String(128), nullable=False)
    source_name = Column(String(256))
    target_type = Column(String(32))
    target_code = Column(String(128))
    mapping_status = Column(String(24), nullable=False, server_default="pending")
    confirmed_by = Column(BigInteger)
    confirmed_at = Column(DateTime(timezone=True))
    source_pk = Column(String(256), nullable=False)
    import_batch_id = Column(String(64), nullable=False, server_default="manual")
    source_updated_at = Column(DateTime(timezone=True))


class DwdGlVoucher(Base):
    __tablename__ = "dwd_gl_voucher"
    __table_args__ = (UniqueConstraint("source_database", "source_pk", name="uq_dwd_gl_voucher_source"), {"schema": "dwd"})
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    legal_entity_id = Column(BigInteger, nullable=False, index=True)
    voucher_no = Column(String(64))
    voucher_group = Column(String(32))
    voucher_date = Column(Date, nullable=False, index=True)
    fiscal_year = Column(Integer, nullable=False)
    fiscal_period = Column(Integer, nullable=False)
    source_status = Column(String(32))
    is_checked = Column(Boolean)
    is_posted = Column(Boolean)
    preparer_name = Column(String(128))
    total_debit = Column(Numeric(20, 4), nullable=False, server_default="0")
    total_credit = Column(Numeric(20, 4), nullable=False, server_default="0")
    source_system = Column(String(32), nullable=False, server_default="kingdee")
    source_database = Column(String(128), nullable=False)
    source_pk = Column(String(256), nullable=False)
    import_batch_id = Column(String(64), nullable=False, index=True)
    source_updated_at = Column(DateTime(timezone=True))
    imported_at = Column(DateTime(timezone=True), server_default=func.now())


class DwdGlVoucherEntry(Base):
    __tablename__ = "dwd_gl_voucher_entry"
    __table_args__ = (UniqueConstraint("source_database", "source_pk", name="uq_dwd_gl_voucher_entry_source"), {"schema": "dwd"})
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    voucher_id = Column(BigInteger, nullable=False, index=True)
    legal_entity_id = Column(BigInteger, nullable=False, index=True)
    line_no = Column(Integer)
    finance_account_id = Column(BigInteger, nullable=False, index=True)
    account_code = Column(String(64))
    summary = Column(String(512))
    debit_amount = Column(Numeric(20, 4), nullable=False, server_default="0")
    credit_amount = Column(Numeric(20, 4), nullable=False, server_default="0")
    currency_code = Column(String(32))
    exchange_rate = Column(Numeric(20, 8))
    quantity = Column(Numeric(20, 6))
    auxiliary_detail_id = Column(String(128))
    source_system = Column(String(32), nullable=False, server_default="kingdee")
    source_database = Column(String(128), nullable=False)
    source_pk = Column(String(256), nullable=False)
    import_batch_id = Column(String(64), nullable=False, index=True)
    source_updated_at = Column(DateTime(timezone=True))


class DwdGlBalanceMonthly(Base):
    __tablename__ = "dwd_gl_balance_monthly"
    __table_args__ = (UniqueConstraint("source_database", "source_pk", name="uq_dwd_gl_balance_source"), {"schema": "dwd"})
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    legal_entity_id = Column(BigInteger, nullable=False, index=True)
    finance_account_id = Column(BigInteger, nullable=False, index=True)
    period = Column(String(7), nullable=False, index=True)
    detail_id = Column(String(128), nullable=False, server_default="")
    currency_code = Column(String(32), nullable=False, server_default="CNY")
    opening_debit = Column(Numeric(20, 4), nullable=False, server_default="0")
    opening_credit = Column(Numeric(20, 4), nullable=False, server_default="0")
    period_debit = Column(Numeric(20, 4), nullable=False, server_default="0")
    period_credit = Column(Numeric(20, 4), nullable=False, server_default="0")
    closing_debit = Column(Numeric(20, 4), nullable=False, server_default="0")
    closing_credit = Column(Numeric(20, 4), nullable=False, server_default="0")
    source_system = Column(String(32), nullable=False, server_default="kingdee")
    source_database = Column(String(128), nullable=False)
    source_pk = Column(String(256), nullable=False)
    import_batch_id = Column(String(64), nullable=False, index=True)
    source_updated_at = Column(DateTime(timezone=True))


class DmFinanceStatementMonthly(Base):
    __tablename__ = "dm_finance_statement_monthly"
    __table_args__ = (UniqueConstraint("legal_entity_id", "period", "statement_type", "line_code", name="uq_finance_statement_monthly_line"), {"schema": "dm"})
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    legal_entity_id = Column(BigInteger, nullable=False, index=True)
    period = Column(String(7), nullable=False, index=True)
    statement_type = Column(String(32), nullable=False)
    line_code = Column(String(64), nullable=False)
    line_name = Column(String(128), nullable=False)
    display_order = Column(Integer, nullable=False, server_default="0")
    current_amount = Column(Numeric(20, 4))
    year_to_date_amount = Column(Numeric(20, 4))
    status = Column(String(24), nullable=False, server_default="pending_mapping")
    quality_issues = Column(JSONB, nullable=False, server_default="[]")
    import_batch_id = Column(String(64), nullable=False)
    source_system = Column(String(32), nullable=False, server_default="kingdee")
    source_database = Column(String(128), nullable=False)
    source_pk = Column(String(256), nullable=False)
    source_updated_at = Column(DateTime(timezone=True))
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
