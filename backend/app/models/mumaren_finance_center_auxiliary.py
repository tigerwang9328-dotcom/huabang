"""Auxiliary-accounting relations for the independent finance centre."""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mumaren_finance_center import MUMAREN_FINANCE_SCHEMA


class FinanceCenterMumarenAccountAuxiliaryDimension(Base):
    __tablename__ = "finance_center_mumaren_account_auxiliary_dimensions"
    __table_args__ = (
        UniqueConstraint("account_id", "aux_type", name="uq_mumaren_account_auxiliary_dimension"),
        {"schema": MUMAREN_FINANCE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        ForeignKey(f"{MUMAREN_FINANCE_SCHEMA}.finance_center_mumaren_books.id"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey(f"{MUMAREN_FINANCE_SCHEMA}.finance_center_mumaren_accounts.id", ondelete="CASCADE"), nullable=False
    )
    aux_type: Mapped[str] = mapped_column(String(16), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FinanceCenterMumarenVoucherLineAuxiliary(Base):
    __tablename__ = "finance_center_mumaren_voucher_line_auxiliaries"
    __table_args__ = (
        UniqueConstraint("voucher_line_id", "aux_type", name="uq_mumaren_line_auxiliary_dimension"),
        {"schema": MUMAREN_FINANCE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        ForeignKey(f"{MUMAREN_FINANCE_SCHEMA}.finance_center_mumaren_books.id"), nullable=False
    )
    voucher_line_id: Mapped[int] = mapped_column(
        ForeignKey(f"{MUMAREN_FINANCE_SCHEMA}.finance_center_mumaren_voucher_lines.id", ondelete="CASCADE"), nullable=False
    )
    aux_type: Mapped[str] = mapped_column(String(16), nullable=False)
    auxiliary_id: Mapped[int] = mapped_column(
        ForeignKey(f"{MUMAREN_FINANCE_SCHEMA}.finance_center_mumaren_auxiliary_accountings.id"), nullable=False
    )
    auxiliary_code_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    auxiliary_name_snapshot: Mapped[str] = mapped_column(String(128), nullable=False)
