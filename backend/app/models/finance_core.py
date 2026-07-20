"""Writable accounting models for the Huabang finance center."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


AMOUNT = Numeric(18, 4)
RATE = Numeric(18, 8)


class _TimestampMixin:
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class _LineageMixin:
    source_system = Column(String(32), nullable=False, server_default="manual")
    source_database = Column(String(128), nullable=False, server_default="")
    source_pk = Column(String(256))
    import_batch_id = Column(String(64))
    source_updated_at = Column(DateTime(timezone=True))


class FinBook(_LineageMixin, _TimestampMixin, Base):
    __tablename__ = "book"
    __table_args__ = (
        UniqueConstraint("legal_entity_id", name="uq_fin_book_legal_entity"),
        UniqueConstraint("book_code", name="uq_fin_book_code"),
        Index(
            "uq_fin_book_source",
            "source_system",
            "source_database",
            "source_pk",
            unique=True,
            postgresql_where=text("source_pk IS NOT NULL"),
        ),
        {"schema": "fin"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    legal_entity_id = Column(BigInteger, ForeignKey("dim.dim_legal_entity.id"), nullable=False)
    book_code = Column(String(64), nullable=False)
    book_name = Column(String(256), nullable=False)
    short_name = Column(String(128))
    base_currency = Column(String(16), nullable=False, server_default="CNY")
    accounting_standard = Column(String(32), nullable=False, server_default="small_enterprise")
    start_period = Column(String(7), nullable=False)
    current_period = Column(String(7), nullable=False)
    status = Column(String(24), nullable=False, server_default="active")
    version = Column(Integer, nullable=False, server_default="1")


class FinPeriod(_TimestampMixin, Base):
    __tablename__ = "period"
    __table_args__ = (
        UniqueConstraint("book_id", "period", name="uq_fin_period_book_period"),
        UniqueConstraint("book_id", "id", name="uq_fin_period_book_id"),
        CheckConstraint("status IN ('open','closed','locked')", name="ck_fin_period_status"),
        Index("ix_fin_period_book_status", "book_id", "status"),
        {"schema": "fin"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin.book.id"), nullable=False)
    period = Column(String(7), nullable=False)
    fiscal_year = Column(Integer, nullable=False)
    fiscal_period = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(16), nullable=False, server_default="open")
    closed_by = Column(BigInteger, ForeignKey("sys.sys_user.id"))
    closed_at = Column(DateTime(timezone=True))
    close_reason = Column(Text)
    version = Column(Integer, nullable=False, server_default="1")


class FinAccount(_LineageMixin, _TimestampMixin, Base):
    __tablename__ = "account"
    __table_args__ = (
        UniqueConstraint("book_id", "account_code", name="uq_fin_account_book_code"),
        UniqueConstraint("book_id", "id", name="uq_fin_account_book_id"),
        ForeignKeyConstraint(
            ["book_id", "parent_id"],
            ["fin.account.book_id", "fin.account.id"],
            name="fk_fin_account_book_parent",
        ),
        CheckConstraint("balance_direction IN ('debit','credit')", name="ck_fin_account_direction"),
        Index(
            "uq_fin_account_source",
            "book_id",
            "source_system",
            "source_database",
            "source_pk",
            unique=True,
            postgresql_where=text("source_pk IS NOT NULL"),
        ),
        Index("ix_fin_account_book_parent", "book_id", "parent_id"),
        {"schema": "fin"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin.book.id"), nullable=False)
    account_code = Column(String(64), nullable=False)
    account_name = Column(String(256), nullable=False)
    parent_id = Column(BigInteger)
    account_level = Column(Integer, nullable=False, server_default="1")
    account_type = Column(String(32), nullable=False)
    balance_direction = Column(String(8), nullable=False)
    is_detail = Column(Boolean, nullable=False, server_default="true")
    is_cash = Column(Boolean, nullable=False, server_default="false")
    is_bank = Column(Boolean, nullable=False, server_default="false")
    has_quantity = Column(Boolean, nullable=False, server_default="false")
    has_foreign_currency = Column(Boolean, nullable=False, server_default="false")
    requires_auxiliary = Column(Boolean, nullable=False, server_default="false")
    is_active = Column(Boolean, nullable=False, server_default="true")
    version = Column(Integer, nullable=False, server_default="1")


class FinAuxCategory(_TimestampMixin, Base):
    __tablename__ = "aux_category"
    __table_args__ = (
        UniqueConstraint("book_id", "category_code", name="uq_fin_aux_category_book_code"),
        UniqueConstraint("book_id", "id", name="uq_fin_aux_category_book_id"),
        {"schema": "fin"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin.book.id"), nullable=False)
    category_code = Column(String(64), nullable=False)
    category_name = Column(String(128), nullable=False)
    status = Column(String(16), nullable=False, server_default="active")


class FinAuxItem(_LineageMixin, _TimestampMixin, Base):
    __tablename__ = "aux_item"
    __table_args__ = (
        UniqueConstraint("book_id", "category_id", "item_code", name="uq_fin_aux_item_book_category_code"),
        UniqueConstraint("book_id", "id", name="uq_fin_aux_item_book_id"),
        ForeignKeyConstraint(
            ["book_id", "category_id"],
            ["fin.aux_category.book_id", "fin.aux_category.id"],
            name="fk_fin_aux_item_book_category",
        ),
        Index(
            "uq_fin_aux_item_source",
            "book_id",
            "source_system",
            "source_database",
            "source_pk",
            unique=True,
            postgresql_where=text("source_pk IS NOT NULL"),
        ),
        {"schema": "fin"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin.book.id"), nullable=False)
    category_id = Column(BigInteger, nullable=False)
    item_code = Column(String(128), nullable=False)
    item_name = Column(String(256), nullable=False)
    target_type = Column(String(32))
    target_code = Column(String(128))
    status = Column(String(16), nullable=False, server_default="active")
    version = Column(Integer, nullable=False, server_default="1")


class FinVoucher(_LineageMixin, _TimestampMixin, Base):
    __tablename__ = "voucher"
    __table_args__ = (
        UniqueConstraint(
            "book_id",
            "period_id",
            "voucher_group",
            "voucher_no",
            name="uq_fin_voucher_book_period_group_no",
        ),
        UniqueConstraint("book_id", "id", name="uq_fin_voucher_book_id"),
        ForeignKeyConstraint(
            ["book_id", "period_id"],
            ["fin.period.book_id", "fin.period.id"],
            name="fk_fin_voucher_book_period",
        ),
        ForeignKeyConstraint(
            ["book_id", "reversal_of_id"],
            ["fin.voucher.book_id", "fin.voucher.id"],
            name="fk_fin_voucher_book_reversal_of",
        ),
        ForeignKeyConstraint(
            ["book_id", "reversed_by_id"],
            ["fin.voucher.book_id", "fin.voucher.id"],
            name="fk_fin_voucher_book_reversed_by",
        ),
        CheckConstraint(
            "status IN ('draft','reviewed','posted','reversed')",
            name="ck_fin_voucher_status",
        ),
        CheckConstraint(
            "total_debit >= 0 AND total_credit >= 0",
            name="ck_fin_voucher_nonnegative",
        ),
        CheckConstraint(
            "status = 'draft' OR total_debit = total_credit",
            name="ck_fin_voucher_balanced_state",
        ),
        Index(
            "uq_fin_voucher_source",
            "book_id",
            "source_system",
            "source_database",
            "source_pk",
            unique=True,
            postgresql_where=text("source_pk IS NOT NULL"),
        ),
        Index("ix_fin_voucher_book_period_status", "book_id", "period", "status"),
        Index("ix_fin_voucher_book_period_id", "book_id", "period_id"),
        Index("ix_fin_voucher_reversal_of", "reversal_of_id"),
        Index("ix_fin_voucher_reversed_by", "reversed_by_id"),
        {"schema": "fin"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin.book.id"), nullable=False)
    period_id = Column(BigInteger, nullable=False)
    voucher_no = Column(String(64), nullable=False)
    voucher_group = Column(String(32), nullable=False, server_default="记")
    voucher_date = Column(Date, nullable=False)
    period = Column(String(7), nullable=False)
    status = Column(String(16), nullable=False, server_default="draft")
    origin_kind = Column(String(32), nullable=False, server_default="manual")
    source_status = Column(String(32))
    summary = Column(String(512))
    attachment_count = Column(Integer, nullable=False, server_default="0")
    total_debit = Column(AMOUNT, nullable=False, server_default="0")
    total_credit = Column(AMOUNT, nullable=False, server_default="0")
    prepared_by = Column(BigInteger, ForeignKey("sys.sys_user.id"))
    prepared_name = Column(String(128))
    reviewed_by = Column(BigInteger, ForeignKey("sys.sys_user.id"))
    reviewed_at = Column(DateTime(timezone=True))
    posted_by = Column(BigInteger, ForeignKey("sys.sys_user.id"))
    posted_at = Column(DateTime(timezone=True))
    reversal_of_id = Column(BigInteger)
    reversed_by_id = Column(BigInteger)
    version = Column(Integer, nullable=False, server_default="1")


class FinVoucherEntry(_TimestampMixin, Base):
    __tablename__ = "voucher_entry"
    __table_args__ = (
        UniqueConstraint("voucher_id", "line_no", name="uq_fin_voucher_entry_line"),
        ForeignKeyConstraint(
            ["book_id", "voucher_id"],
            ["fin.voucher.book_id", "fin.voucher.id"],
            name="fk_fin_voucher_entry_book_voucher",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["book_id", "account_id"],
            ["fin.account.book_id", "fin.account.id"],
            name="fk_fin_voucher_entry_book_account",
        ),
        CheckConstraint(
            "(debit_amount > 0 AND credit_amount = 0) OR "
            "(credit_amount > 0 AND debit_amount = 0)",
            name="ck_fin_voucher_entry_side",
        ),
        Index("ix_fin_voucher_entry_account", "book_id", "account_id"),
        Index("ix_fin_voucher_entry_book_voucher", "book_id", "voucher_id"),
        {"schema": "fin"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin.book.id"), nullable=False)
    voucher_id = Column(BigInteger, nullable=False)
    line_no = Column(Integer, nullable=False)
    account_id = Column(BigInteger, nullable=False)
    summary = Column(String(512), nullable=False)
    debit_amount = Column(AMOUNT, nullable=False, server_default="0")
    credit_amount = Column(AMOUNT, nullable=False, server_default="0")
    currency_code = Column(String(16), nullable=False, server_default="CNY")
    exchange_rate = Column(RATE, nullable=False, server_default="1")
    original_amount = Column(AMOUNT)
    quantity = Column(Numeric(18, 6))
    unit_price = Column(Numeric(18, 6))
    aux_items = Column(JSONB, nullable=False, server_default="{}")
    cash_flow_item = Column(String(64))


class FinVoucherVersion(Base):
    __tablename__ = "voucher_version"
    __table_args__ = (
        UniqueConstraint("voucher_id", "version", name="uq_fin_voucher_version"),
        ForeignKeyConstraint(
            ["book_id", "voucher_id"],
            ["fin.voucher.book_id", "fin.voucher.id"],
            name="fk_fin_voucher_version_book_voucher",
            ondelete="CASCADE",
        ),
        Index("ix_fin_voucher_version_book_voucher", "book_id", "voucher_id"),
        {"schema": "fin"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin.book.id"), nullable=False)
    voucher_id = Column(BigInteger, nullable=False)
    version = Column(Integer, nullable=False)
    action = Column(String(32), nullable=False)
    before_snapshot = Column(JSONB)
    after_snapshot = Column(JSONB)
    actor_id = Column(BigInteger, ForeignKey("sys.sys_user.id"))
    actor_name = Column(String(128))
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinLedgerBalance(_TimestampMixin, Base):
    __tablename__ = "ledger_balance"
    __table_args__ = (
        UniqueConstraint("book_id", "account_id", "period", name="uq_fin_ledger_balance_scope"),
        ForeignKeyConstraint(
            ["book_id", "account_id"],
            ["fin.account.book_id", "fin.account.id"],
            name="fk_fin_ledger_balance_book_account",
        ),
        ForeignKeyConstraint(
            ["book_id", "period_id"],
            ["fin.period.book_id", "fin.period.id"],
            name="fk_fin_ledger_balance_book_period",
        ),
        CheckConstraint(
            "balance_direction IN ('debit','credit')",
            name="ck_fin_ledger_direction",
        ),
        CheckConstraint(
            "period_debit >= 0 AND period_credit >= 0",
            name="ck_fin_ledger_nonnegative",
        ),
        CheckConstraint(
            "(balance_direction = 'debit' AND closing_amount = opening_amount + period_debit - period_credit) OR "
            "(balance_direction = 'credit' AND closing_amount = opening_amount + period_credit - period_debit)",
            name="ck_fin_ledger_equation",
        ),
        Index("ix_fin_ledger_balance_book_period", "book_id", "period_id"),
        {"schema": "fin"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin.book.id"), nullable=False)
    account_id = Column(BigInteger, nullable=False)
    period_id = Column(BigInteger, nullable=False)
    period = Column(String(7), nullable=False)
    balance_direction = Column(String(8), nullable=False)
    opening_amount = Column(AMOUNT, nullable=False, server_default="0")
    period_debit = Column(AMOUNT, nullable=False, server_default="0")
    period_credit = Column(AMOUNT, nullable=False, server_default="0")
    closing_amount = Column(AMOUNT, nullable=False, server_default="0")
    version = Column(Integer, nullable=False, server_default="1")


class FinStatementLine(_TimestampMixin, Base):
    __tablename__ = "statement_line"
    __table_args__ = (
        UniqueConstraint(
            "template_code",
            "template_version",
            "statement_type",
            "line_code",
            name="uq_fin_statement_line_template",
        ),
        {"schema": "fin"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    template_code = Column(String(64), nullable=False)
    template_version = Column(Integer, nullable=False, server_default="1")
    statement_type = Column(String(32), nullable=False)
    line_code = Column(String(64), nullable=False)
    line_name = Column(String(128), nullable=False)
    parent_line_id = Column(BigInteger, ForeignKey("fin.statement_line.id"))
    display_order = Column(Integer, nullable=False, server_default="0")
    formula_kind = Column(String(24), nullable=False, server_default="mapping")
    formula = Column(JSONB, nullable=False, server_default="{}")


class FinStatementMapping(_TimestampMixin, Base):
    __tablename__ = "statement_mapping"
    __table_args__ = (
        UniqueConstraint("book_id", "account_id", "statement_line_id", name="uq_fin_statement_mapping"),
        ForeignKeyConstraint(
            ["book_id", "account_id"],
            ["fin.account.book_id", "fin.account.id"],
            name="fk_fin_statement_mapping_book_account",
        ),
        Index("ix_fin_statement_mapping_book_account", "book_id", "account_id"),
        {"schema": "fin"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin.book.id"), nullable=False)
    account_id = Column(BigInteger, nullable=False)
    statement_line_id = Column(BigInteger, ForeignKey("fin.statement_line.id"), nullable=False)
    statement_type = Column(String(32), nullable=False)
    amount_sign = Column(Integer, nullable=False, server_default="1")
    status = Column(String(24), nullable=False, server_default="suggested")
    mapping_source = Column(String(24), nullable=False, server_default="account_code")
    confirmed_by = Column(BigInteger, ForeignKey("sys.sys_user.id"))
    confirmed_at = Column(DateTime(timezone=True))
    version = Column(Integer, nullable=False, server_default="1")


class FinOperationLog(Base):
    __tablename__ = "operation_log"
    __table_args__ = (Index("ix_fin_operation_log_target", "book_id", "target_type", "target_id"), {"schema": "fin"})

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin.book.id"), nullable=False)
    actor_id = Column(BigInteger, ForeignKey("sys.sys_user.id"))
    actor_name = Column(String(128))
    action = Column(String(64), nullable=False)
    target_type = Column(String(64), nullable=False)
    target_id = Column(String(128), nullable=False)
    reason = Column(Text, nullable=False)
    before_data = Column(JSONB)
    after_data = Column(JSONB)
    request_id = Column(String(64))
    client_ip = Column(String(64))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinSourceLink(_TimestampMixin, Base):
    __tablename__ = "source_link"
    __table_args__ = (
        UniqueConstraint(
            "book_id",
            "source_system",
            "source_database",
            "source_pk",
            name="uq_fin_source_link_source",
        ),
        Index("ix_fin_source_link_target", "book_id", "target_type", "target_id"),
        {"schema": "fin"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin.book.id"), nullable=False)
    target_type = Column(String(64), nullable=False)
    target_id = Column(BigInteger, nullable=False)
    source_system = Column(String(32), nullable=False)
    source_database = Column(String(128), nullable=False, server_default="")
    source_pk = Column(String(256), nullable=False)
    import_batch_id = Column(String(64), nullable=False, server_default="manual")
    source_updated_at = Column(DateTime(timezone=True))
    source_hash = Column(String(64))
    metadata_json = Column(JSONB, nullable=False, server_default="{}")
