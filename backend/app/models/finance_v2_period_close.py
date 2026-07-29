"""Auditable V2 period-close and controlled reopen records."""

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class FinanceV2PeriodCloseBatch(Base):
    __tablename__ = "period_close_batch"
    __table_args__ = (
        UniqueConstraint("period_id", "run_number", name="uq_fin_current_period_close_run"),
        UniqueConstraint("command_id", name="uq_fin_current_period_close_command"),
        CheckConstraint("run_number >= 1", name="ck_fin_current_period_close_run_number"),
        CheckConstraint("close_kind IN ('month','year')", name="ck_fin_current_period_close_kind"),
        CheckConstraint(
            "status IN ('running','closed','failed','reopen_requested','reopened')",
            name="ck_fin_current_period_close_status",
        ),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    book_id = Column(BigInteger, ForeignKey("fin_current.accounting_book.id"), nullable=False)
    period_id = Column(BigInteger, ForeignKey("fin_current.fiscal_period.id"), nullable=False)
    run_number = Column(Integer, nullable=False)
    close_kind = Column(String(16), nullable=False)
    status = Column(String(24), nullable=False, server_default="running")
    command_id = Column(String(128), nullable=False)
    check_report = Column(JSONB, nullable=False, server_default="{}")
    failure_reason = Column(Text)
    recovery_instructions = Column(Text)
    started_by = Column(String(128), nullable=False)
    closed_by = Column(String(128))
    reopen_requested_by = Column(String(128))
    reopen_reason = Column(Text)
    reopen_requested_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    closed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class FinanceV2PeriodCloseApproval(Base):
    __tablename__ = "period_close_approval"
    __table_args__ = (
        UniqueConstraint("batch_id", "approval_step", name="uq_fin_current_period_close_approval_step"),
        UniqueConstraint("batch_id", "actor_id", name="uq_fin_current_period_close_approval_actor"),
        UniqueConstraint("command_id", name="uq_fin_current_period_close_approval_command"),
        CheckConstraint("approval_step IN (1,2)", name="ck_fin_current_period_close_approval_step"),
        {"schema": "fin_current"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_id = Column(BigInteger, ForeignKey("fin_current.period_close_batch.id"), nullable=False)
    approval_step = Column(Integer, nullable=False)
    actor_id = Column(String(128), nullable=False)
    command_id = Column(String(128), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
